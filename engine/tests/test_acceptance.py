import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest
from PIL import Image

DEFAULT = "4c951577-984b-43a3-b90d-d640668837db"
ENGINE = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOKI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PYTHONPATH", str(ENGINE) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def cli(*args, data=None, code=0):
    result = subprocess.run([sys.executable, "-m", "pivoki_engine", *map(str, args)],
                            input=json.dumps(data) if data is not None else None,
                            capture_output=True, encoding="utf-8", timeout=60)
    assert result.returncode == code, (result.stdout, result.stderr)
    return json.loads(result.stdout)


def rpc(action, *, code=0, **params):
    return cli("rpc", data={"action": action, **params}, code=code)


def picture(path, size=(122, 57), color="red"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def plan(paths, root, **extra):
    return rpc("plan", inputs=list(map(str, paths)), outputRoot=str(root),
               packageId=DEFAULT, revision=1, **extra)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_ac01_nested_scan_reports_unsupported_and_skips_output_tree(tmp_path):
    src = tmp_path / "in"
    picture(src / "a.jpg")
    picture(src / "b.jpg")
    picture(src / "sub" / "c.png")
    (src / "readme.txt").write_text("skip")
    out = src / "Teslim"
    picture(out / "unrelated.jpg")
    picture(src / "report.pages" / "preview.png")
    flat = plan([src], out)
    assert {Path(r["source"]).name for r in flat["rows"]} == {"a.jpg", "b.jpg"}
    deep = plan([src], out, recursive=True)
    assert {Path(r["source"]).name for r in deep["rows"]} == {"a.jpg", "b.jpg", "c.png"}
    assert any("readme.txt" in r["source"] and r["reason"] for r in deep["skipped"])
    assert list(out.iterdir()) == [out / "unrelated.jpg"]


def test_ac02_collision_after_approval_preserves_inputs_and_competitor(tmp_path):
    a = picture(tmp_path / "a" / "ürün.jpg")
    b = picture(tmp_path / "b" / "ürün.jpg", color="blue")
    before = {str(p): digest(p) for p in [a, b]}
    out = tmp_path / "Teslim"
    existing = out / "Mağaza görselleri" / "web" / "ürün.webp"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing")
    result = plan([a, b], out)
    targets = [Path(row["target"]) for row in result["rows"]]
    assert len(set(targets)) == len(targets) == 4
    assert existing not in targets
    rival = targets[0]
    rival.parent.mkdir(parents=True)
    rival.write_bytes(b"competitor")
    failed = rpc("run", planId=result["planId"], code=1)
    assert failed["code"] == "replan_required"
    assert rival.read_bytes() == b"competitor"
    assert existing.read_bytes() == b"existing"
    assert {str(p): digest(p) for p in [a, b]} == before
    assert rpc("history")["jobs"] == []


def test_ac11_twenty_images_one_atomic_job(tmp_path):
    src = tmp_path / "ürün"
    for n in range(20):
        picture(src / f"foto {n}.png", (1800, 540), color=(n, 20, 90))
    out = tmp_path / "Export"
    preview = plan([src], out)
    assert len(preview["rows"]) == 40
    assert not out.exists()
    result = rpc("run", planId=preview["planId"])
    assert result["paths"] == [r["target"] for r in preview["rows"]]
    for path in map(Path, result["paths"]):
        expected = (1600, 480) if path.suffix == ".webp" else (400, 120)
        with Image.open(path) as im:
            im.load()
            assert im.size == expected
        if shutil.which("sips"):
            probe = subprocess.check_output(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)], text=True)
            assert f"pixelWidth: {expected[0]}" in probe and f"pixelHeight: {expected[1]}" in probe
        elif shutil.which("ffprobe"):
            probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                                             "-of", "json", str(path)], text=True)
            assert json.loads(probe)["streams"][0] == {"width": expected[0], "height": expected[1]}
    assert [j["jobId"] for j in rpc("history")["jobs"]] == [result["jobId"]]
    assert rpc("run", planId=preview["planId"]) == result


def test_ac20_cli_unicode_paths_and_rpc_equivalence(tmp_path):
    inputs = [picture(tmp_path / name) for name in ["A adı.png", "İki boşluk.jpg"]]
    out = tmp_path / "İşler"
    args = ["package", "run", DEFAULT, "--revision", "1", "--input", *inputs, "--out", out,
            "--on-conflict", "keep-both", "--json"]
    assert cli(*args, "--dry-run")["rows"] == plan(inputs, out)["rows"]
    result = cli(*args)
    gui_plan = plan(inputs, tmp_path / "GUI")
    gui = rpc("run", planId=gui_plan["planId"])
    assert list(map(digest, result["paths"])) == list(map(digest, gui["paths"]))
    bad = cli(*args, "--input", tmp_path / "missing.jpg", code=1)
    assert bad["status"] == "failed" and bad["code"]
    assert cli("package", "run", "--json", code=64)["status"] == "failed"


def test_ac21_history_clearing_is_persistent_and_preserves_files(tmp_path):
    image = picture(tmp_path / "x.png")
    plans = [plan([image], tmp_path / p)["planId"] for p in ("one", "two")]
    jobs = [rpc("run", planId=pid) for pid in plans]
    checksums = {path: digest(path) for job in jobs for path in job["paths"]}
    rpc("removeHistory", jobId=jobs[0]["jobId"])
    assert [j["jobId"] for j in rpc("history")["jobs"]] == [jobs[1]["jobId"]]
    rpc("clearHistory")
    assert len(rpc("history")["jobs"]) == 0
    assert {p: digest(p) for p in checksums} == checksums
    rpc("run", planId=plans[0])
    assert rpc("history")["jobs"] == []


def test_caller_supplied_plan_id_is_immutable(tmp_path):
    image = picture(tmp_path / "a.png")
    out = tmp_path / "out"
    key = str(uuid.uuid4())
    result = plan([image], out, planId=key)
    assert plan([image], out, planId=key) == result
    assert result["planId"] == key
