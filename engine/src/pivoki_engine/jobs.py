import json
import os
from pathlib import Path
import sqlite3
import tempfile
from uuid import uuid4

from PIL import Image, ImageOps

from .filesystem import output_root
from .images import DECODERS, content_hash, encode, fingerprint, verify_image
from .model import Problem, absolute, dump, identifier, identity, inspect_root, linked
from .store import get_package, insert_history, job_lock, now


def record_terminal(db, job_id, result):
    result["jobId"] = job_id
    with db:
        db.execute("UPDATE jobs SET state=?,result=? WHERE id=?", (result["status"], dump(result), job_id))
    return result


def record_success(db, job_id, plan, meta):
    paths = [row["target"] for row in plan["rows"] if row["status"] == "planned"]
    result = {"status": "success", "jobId": job_id, "paths": paths, "directory": plan["directory"]}
    entry = {"name": plan["name"], "createdAt": meta["createdAt"], **result}
    with db:
        db.execute("UPDATE jobs SET state='success',result=? WHERE id=?", (dump(result), job_id))
        insert_history(db, entry)
    return result


def failure(exc):
    if isinstance(exc, Problem):
        return exc.result()
    return {"status": "failed", "code": "job_failed", "error": str(exc) or type(exc).__name__}


def bind_source(path, expected, check, copy_to=None):
    try:
        matches = fingerprint(path, check, copy_to) == expected
    except FileNotFoundError:
        matches = False
    if not matches:
        raise Problem("source_changed", f"Source changed after planning. Review a new plan: {path}", source=str(path))


def write_images(stage, plan, check):
    groups = {}
    for row in plan["rows"]:
        if row["status"] == "planned":
            groups.setdefault(row["source"], []).append(row)
    manifest = []
    for source, rows in groups.items():
        check()
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as snapshot:
            bind_source(Path(source), plan["sources"][source], check, snapshot)
            with Image.open(snapshot, formats=tuple(DECODERS)) as decoded, ImageOps.exif_transpose(decoded) as image:
                for row in rows:
                    check()
                    spec = plan["outputs"][row["outputIndex"]]
                    relative = Path(row["relativePath"])
                    with stage.subdirectory(relative.parts[:-1], create=True) as directory:
                        with directory.file(relative.name, "wb") as stream:
                            size = encode(image, spec, stream)
                            stream.flush()
                            os.fsync(stream.fileno())
                        with directory.file(relative.name, "rb") as stream:
                            verify_image(stream, spec, size)
                            stream.seek(0)
                            digest = content_hash(stream, check)
                        directory.sync()
                    manifest.append({"path": relative.as_posix(), "sha256": digest})
    stage.sync()
    return manifest


def matches_publication(root, plan, meta):
    if not meta.get("identity") or not meta.get("manifest"):
        return False
    name = Path(plan["directory"]).name
    try:
        st = root.stat(name)
        if linked(st) or identity(st) != meta["identity"]:
            return False
        with root.child(name) as published:
            for entry in meta["manifest"]:
                relative = Path(entry["path"])
                with published.subdirectory(relative.parts[:-1]) as folder, folder.file(relative.name, "rb") as stream:
                    if content_hash(stream) != entry["sha256"]:
                        return False
        return True
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return False


def recover_one(db, job, plan):
    meta = json.loads(job["meta"])
    result = Problem("interrupted", "Processing was interrupted before the package could be confirmed.").result()
    try:
        with output_root(plan["outputRoot"], plan["anchor"]) as root:
            if job["state"] == "publishing" and matches_publication(root, plan, meta):
                return record_success(db, job["id"], plan, meta)
            root.cleanup(meta["stage"], meta.get("identity"))
    except FileNotFoundError as exc:
        if job["state"] == "publishing":
            return {"status": "failed", "code": "recovery_pending", "error": str(exc), "jobId": job["id"]}
    except (OSError, Problem) as exc:
        # A disconnected or inaccessible volume can return. Keep this journal for a later reconciliation.
        return {**failure(exc), "jobId": job["id"], "code": "recovery_pending"}
    return record_terminal(db, job["id"], result)


def recover(db):
    pending = db.execute("SELECT plan FROM jobs WHERE state IN ('running','publishing')").fetchall()
    for row in pending:
        with job_lock(row["plan"]) as acquired:
            if not acquired:
                continue
            job = db.execute("SELECT * FROM jobs WHERE plan=?", (row["plan"],)).fetchone()
            if job["state"] in ("running", "publishing"):
                plan = json.loads(db.execute("SELECT doc FROM plans WHERE id=?", (row["plan"],)).fetchone()[0])
                recover_one(db, job, plan)


def check_target(root, name, plan):
    try:
        root.stat(name)
    except FileNotFoundError:
        return
    raise Problem("replan_required", f"A new destination already exists. Review a new plan: {plan['directory']}",
                  target=plan["directory"])


def run(db, request, external_check):
    plan_id = identifier(request.get("planId"), "planId")
    rec = db.execute("SELECT doc FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not rec:
        raise Problem("plan_missing", "This plan is unavailable. Create a new plan.")
    plan = json.loads(rec[0])
    cancel_file = absolute(request["cancelFile"]) if request.get("cancelFile") else None
    with job_lock(plan_id) as acquired:
        if not acquired:
            raise Problem("job_busy", "This plan is currently running.")
        prior = db.execute("SELECT * FROM jobs WHERE plan=?", (plan_id,)).fetchone()
        if prior:
            if prior["result"]:
                return json.loads(prior["result"])
            return recover_one(db, prior, plan)

        job_id = str(uuid4())
        meta = {"stage": ".pivoki-stage-" + job_id, "createdAt": now()}
        with db:
            db.execute("BEGIN IMMEDIATE")
            if plan["packageId"]:
                get_package(db, plan["packageId"], plan["revision"])
            db.execute("INSERT INTO jobs (id,plan,state,meta) VALUES (?,?,'running',?)",
                       (job_id, plan_id, dump(meta)))

        def check():
            external_check()
            if ((cancel_file and cancel_file.exists())
                    or db.execute("SELECT cancel FROM jobs WHERE id=?", (job_id,)).fetchone()[0]):
                raise Problem("cancelled", "The job was cancelled before publication.")

        published = False
        try:
            check()
            if not any(r["status"] == "planned" for r in plan["rows"]):
                return record_terminal(db, job_id, {"status": "skipped", "code": "no_outputs", "paths": []})
            with output_root(plan["outputRoot"], plan["anchor"], create=True) as root:
                final_name = Path(plan["directory"]).name
                check_target(root, final_name, plan)
                root.mkdir(meta["stage"])
                try:
                    meta["identity"] = identity(root.stat(meta["stage"]))
                    with db:
                        db.execute("UPDATE jobs SET meta=? WHERE id=?", (dump(meta), job_id))
                    with root.child(meta["stage"]) as stage:
                        meta["manifest"] = write_images(stage, plan, check)
                    for source, signature in plan["sources"].items():
                        bind_source(Path(source), signature, check)
                    inspect_root(Path(plan["outputRoot"]))
                    if root.fd is not None and identity(os.fstat(root.fd)) != identity(root.path.stat()):
                        raise Problem("unsafe_output", "Destination was moved. Review a new plan.")
                    with db:
                        db.execute("UPDATE jobs SET state='publishing',meta=? WHERE id=?", (dump(meta), job_id))
                    check()
                    try:
                        root.publish(meta["stage"], final_name)
                    except OSError:
                        check_target(root, final_name, plan)
                        raise
                    published = True
                    root.sync()
                    return record_success(db, job_id, plan, meta)
                finally:
                    if not published:
                        root.cleanup(meta["stage"], meta.get("identity"))
        except (OSError, TypeError, ValueError, RuntimeError, sqlite3.Error, Problem, Image.DecompressionBombError) as exc:
            if published:
                # The namespace operation is the commit point. Leave a recoverable journal if cataloging failed.
                raise Problem("recovery_pending", f"Package was published. Reopen to reconcile its history: {exc}",
                              jobId=job_id) from exc
            return record_terminal(db, job_id, failure(exc))
