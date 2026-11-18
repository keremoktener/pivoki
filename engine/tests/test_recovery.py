import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from PIL import Image
import pytest

from test_acceptance import DEFAULT, cli, digest, isolated, picture, plan, rpc


def child(script, pid, *args):
    return subprocess.Popen([sys.executable, "-c", script, pid, *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")


def test_changed_source_even_with_same_inode_size_and_mtime(tmp_path):
    src = picture(tmp_path / "photo.bmp")
    preview = plan([src], tmp_path / "out")
    st = src.stat()
    data = bytearray(src.read_bytes())
    data[-7] ^= 1
    src.write_bytes(data)
    os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns))
    result = rpc("run", code=1, planId=preview["planId"])
    assert result["code"] == "source_changed"
    assert not Path(preview["directory"]).exists()
    assert rpc("history")["jobs"] == []


@pytest.mark.parametrize("checkpoint", ["encoding", "immediately_after_publish", "before_history"])
def test_killed_process_is_reconciled_on_next_request(tmp_path, checkpoint):
    src = picture(tmp_path / "source.png")
    before = digest(src)
    out = tmp_path / "out"
    preview = plan([src], out)
    proc = child("""
import os,sys
from pivoki_engine import jobs
from pivoki_engine.filesystem import Directory
from pivoki_engine.service import dispatch
if sys.argv[2] == "encoding":
    jobs.encode = lambda *a: os._exit(78)
elif sys.argv[2] == "before_history":
    jobs.record_success = lambda *a: os._exit(78)
else:
    publish = Directory.publish
    def die(self, source, target):
        publish(self, source, target)
        os._exit(78)
    Directory.publish = die
dispatch({"action":"run","planId":sys.argv[1]})
""", preview["planId"], checkpoint)
    _, err = proc.communicate(timeout=20)
    assert proc.returncode == 78, err
    reopened = rpc("history")["jobs"]
    assert not list(out.glob(".pivoki-stage-*"))
    assert digest(src) == before
    if checkpoint == "encoding":
        assert reopened == []
        assert not Path(preview["directory"]).exists()
        assert rpc("run", code=1, planId=preview["planId"])["code"] == "interrupted"
    else:
        assert len(reopened) == 1
        result = rpc("run", planId=preview["planId"])
        assert result["jobId"] == reopened[0]["jobId"]
        assert sorted(map(str, Path(preview["directory"]).rglob("*.*"))) == sorted(result["paths"])
        assert rpc("history")["jobs"] == reopened


def test_write_error_does_not_publish_an_incomplete_bundle(tmp_path):
    src = picture(tmp_path / "a.png")
    preview = plan([src], tmp_path / "out")
    proc = child("""
import json,sys
from pivoki_engine import jobs
from pivoki_engine.service import dispatch
encode = jobs.encode
def write(img,spec,stream):
    if spec["format"] == "jpg":
        stream.write(b"partial")
        raise OSError("disk full")
    return encode(img,spec,stream)
jobs.encode = write
print(json.dumps(dispatch({"action":"run","planId":sys.argv[1]})))
""", preview["planId"])
    stdout, err = proc.communicate(timeout=20)
    assert proc.returncode == 0, err
    assert json.loads(stdout)["status"] == "failed"
    assert "disk full" in json.loads(stdout)["error"]
    assert not list((tmp_path / "out").iterdir())
    assert rpc("history")["jobs"] == []


def test_cancel_file_preserves_successful_jobs(tmp_path):
    source = picture(tmp_path / "photo.png")
    out = tmp_path / "out"
    prior = rpc("run", planId=plan([source], out)["planId"])
    preview = plan([source], out)
    token = tmp_path / "caller-owned.cancel"
    token.touch()
    result = rpc("run", planId=preview["planId"], cancelFile=str(token), code=130)
    assert result["status"] == "cancelled"
    assert token.exists() and not Path(preview["directory"]).exists()
    assert [j["jobId"] for j in rpc("history")["jobs"]] == [prior["jobId"]]


def test_live_worker_is_not_recovered_by_another_client(tmp_path):
    image = picture(tmp_path / "source.png")
    out = tmp_path / "out"
    preview = plan([image], out)
    ready = tmp_path / "ready"
    release = tmp_path / "go"
    proc = child("""
import json,signal,sys,time
from pathlib import Path
from pivoki_engine import jobs
from pivoki_engine.cli import main
encode = jobs.encode
def hold(*args):
    Path(sys.argv[2]).touch()
    for _ in range(500):
        if Path(sys.argv[3]).exists(): break
        time.sleep(.02)
    return encode(*args)
jobs.encode = hold
import io
sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps({"action":"run","planId":sys.argv[1]}).encode()))
raise SystemExit(main(["rpc"]))
""", preview["planId"], ready, release)
    try:
        for _ in range(300):
            if ready.exists() or proc.poll() is not None:
                break
            time.sleep(.02)
        assert ready.exists()
        assert rpc("history")["jobs"] == []
        assert rpc("run", code=1, planId=preview["planId"])["code"] == "job_busy"
        if os.name == "nt":
            assert rpc("cancel", planId=preview["planId"])["requested"]
        else:
            proc.send_signal(signal.SIGTERM)
        release.touch()
        stdout, err = proc.communicate(timeout=20)
        assert proc.returncode == 130, (stdout, err)
        assert json.loads(stdout)["status"] == "cancelled"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert not list(out.iterdir())


def test_atomic_commit_cannot_replace_even_an_empty_competing_directory(tmp_path):
    src = picture(tmp_path / "input.png")
    preview = plan([src], tmp_path / "out")
    proc = child("""
import json,sys
from pathlib import Path
from pivoki_engine.filesystem import Directory
from pivoki_engine.service import dispatch
original = Directory.publish
def race(self, source, dest):
    (self.path / dest).mkdir()
    return original(self, source, dest)
Directory.publish = race
print(json.dumps(dispatch({"action":"run","planId":sys.argv[1]})))
""", preview["planId"])
    stdout, err = proc.communicate(timeout=20)
    assert proc.returncode == 0, err
    assert json.loads(stdout)["code"] == "replan_required"
    assert not list(Path(preview["directory"]).iterdir())
    assert rpc("history")["jobs"] == []


def test_unsafe_relative_directories_and_late_destination_symlink(tmp_path):
    for subdir in ["../other", "/tmp", "C:/Temp", "dir/..", "a\\b", "a//b", "NUL"]:
        bad = rpc("savePackage", code=1, package={"name": "Example", "outputs": [
            {"format": "png", "maxEdge": 8, "relativeDir": subdir}]})
        assert bad["status"] == "failed", subdir
    src = picture(tmp_path / "safe.png")
    out = tmp_path / "out"
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    preview = plan([src], out)
    try:
        out.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Creating a symlink is unavailable: {exc}")
    result = rpc("run", code=1, planId=preview["planId"])
    assert result["status"] == "failed"
    assert not list(outside.iterdir())


def test_revisions_transpose_alpha_dpi_and_small_source(tmp_path):
    package = rpc("savePackage", package={"name":"Çıktılar", "outputs":[
        {"format":fmt, "maxEdge":200, "relativeDir":fmt} for fmt in ("jpg","webp","png")]})["package"]
    edited = rpc("savePackage", package={**package, "name":"v2"})["package"]
    assert edited["packageId"] == package["packageId"] and edited["revision"] == 2
    assert rpc("savePackage", package=package, code=1)["code"] == "stale_revision"
    path = tmp_path / "alpha.png"
    img = Image.new("RGBA", (31,11), (0,0,0,0))
    exif = Image.Exif()
    exif[274] = 6
    img.save(path, exif=exif, dpi=(144,144))
    preview = rpc("plan", inputs=[str(path)], outputRoot=str(tmp_path/"out"),
                  packageId=package["packageId"], revision=1)
    assert preview["name"] == package["name"]
    result = rpc("run", planId=preview["planId"])
    for path in map(Path, result["paths"]):
        with Image.open(path) as output:
            assert output.size == (11,31)
            if path.suffix == ".jpg":
                assert output.getpixel((0,0)) == (255,255,255)
            else:
                assert output.convert("RGBA").getpixel((0,0))[3] == 0
            if path.suffix != ".webp":
                assert tuple(round(v) for v in output.info["dpi"]) == (144,144)
    rpc("deletePackage", packageId=package["packageId"])
    assert package["packageId"] not in [p["packageId"] for p in rpc("packages")["packages"]]


def test_skip_conflicts_produces_only_noncolliding_rows(tmp_path):
    a = picture(tmp_path / "a" / "same.jpg")
    b = picture(tmp_path / "b" / "same.jpg")
    c = picture(tmp_path / "c" / "extra.jpg")
    out = tmp_path / "out"
    existing = out / "Mağaza görselleri/web/same.webp"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"occupied")
    preview = plan([a, b, c], out, conflictPolicy="skip")
    planned = [r for r in preview["rows"] if r["status"] == "planned"]
    assert len(planned) == 3
    got = rpc("run", planId=preview["planId"])
    assert got["paths"] == [r["target"] for r in planned]
    assert existing.read_bytes() == b"occupied"


def test_same_revision_and_id_cannot_be_rebound_to_different_plan(tmp_path):
    src = picture(tmp_path / "a.png")
    pid = str(uuid.uuid4())
    plan([src], tmp_path / "out", planId=pid)
    bad = rpc("plan", planId=pid, inputs=[str(src)], outputRoot=str(tmp_path / "another"),
              packageId=DEFAULT, revision=1, code=1)
    assert bad["code"] == "plan_id_conflict"


def test_delete_blocks_new_runs_but_prior_success_remains_idempotent(tmp_path):
    img = picture(tmp_path / "source.png")
    package = rpc("savePackage", package={"name":"One", "outputs":[
        {"format":"png", "maxEdge":100, "relativeDir":"images"}]})["package"]
    req = dict(inputs=[str(img)], outputRoot=str(tmp_path / "out"), packageId=package["packageId"], revision=1)
    plan_id = str(uuid.uuid4())
    started = rpc("plan", planId=plan_id, **req)
    completed = rpc("run", planId=plan_id)
    awaiting = rpc("plan", **req)
    rpc("deletePackage", packageId=package["packageId"])
    assert rpc("plan", **req, code=1)["code"] == "package_missing"
    assert rpc("run", planId=awaiting["planId"], code=1)["code"] == "package_missing"
    assert rpc("plan", planId=plan_id, **req) == started
    assert rpc("run", planId=plan_id) == completed


def test_studio_and_package_exports_share_history_limit(tmp_path):
    from pivoki_engine.service import record_export
    img = picture(tmp_path / "exports" / "a" / "studio.png")
    other = picture(tmp_path / "exports" / "b" / "second.jpg")
    preview = plan([img], tmp_path/"bundle")
    bundle = rpc("run", planId=preview["planId"])
    for number in range(50):
        result = record_export(f"Studio {number}", [img, other])
    assert result["directory"] == str(img.parent.parent)
    assert result["paths"] == [str(img), str(other)]
    history = rpc("history")["jobs"]
    assert len(history) == len({row["jobId"] for row in history}) == 50
    assert history[0]["jobId"] == result["jobId"]
    assert history[0]["createdAt"]
    assert not any(row["jobId"] == bundle["jobId"] for row in history)
