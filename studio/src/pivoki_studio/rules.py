"""Persistent, opt-in folder rules. Desktop and Studio workers share one tick lock."""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import stat
import time
import uuid

from pivoki_engine.store import data_home, job_lock

DEFAULT_FILTER = ".jpg,.jpeg,.png,.webp,.heic,.heif,.tif,.tiff,.bmp"
SETTLE_SECONDS = 6


@contextmanager
def database():
    home = data_home()
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(home / "studio-rules.sqlite3", timeout=12)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS rules (
                id TEXT PRIMARY KEY, root TEXT, destination TEXT, extensions TEXT,
                package TEXT, revision INTEGER, policy TEXT, enabled INTEGER, message TEXT);
            CREATE TABLE IF NOT EXISTS events (
                rule TEXT, path TEXT, version TEXT, observed REAL, state TEXT, plan TEXT, message TEXT,
                PRIMARY KEY(rule,path));
        """)
        with db:
            yield db
    finally:
        db.close()


def definitions():
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM rules ORDER BY rowid")]


def scan(root, extensions):
    allowed = {part.strip().lower().lstrip(".") for part in extensions.split(",")}
    if not allowed or any(not x.isalnum() for x in allowed):
        raise ValueError("Filtreye virgülle ayrılmış dosya uzantıları girin.")
    result = {}
    for entry in Path(root).iterdir():
        if entry.name.startswith(".") or entry.suffix.lower()[1:] not in allowed:
            continue
        try:
            info = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 1024:
            result[str(entry)] = f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}"
    return result


def validated(root, destination, extensions):
    if not root or not destination:
        raise ValueError("Kaynak ve hedef klasör seçin.")
    root, destination = Path(root).resolve(strict=True), Path(destination).resolve(strict=True)
    if not root.is_dir() or not destination.is_dir() or root == destination:
        raise ValueError("İki farklı klasör seçin.")
    if root.is_relative_to(destination):
        raise ValueError("İzlenen klasör hedefin içinde olamaz.")
    return root, destination, scan(root, extensions)


def enable(root, destination, extensions, package, revision, policy, include_existing):
    root, destination, existing = validated(root, destination, extensions)
    key = str(uuid.uuid4())
    if policy not in {"keep-both", "skip"}:
        raise ValueError("Çakışma politikası geçersiz.")
    with database() as db:
        db.execute("INSERT INTO rules VALUES(?,?,?,?,?,?,?,1,'')",
                   (key, str(root), str(destination), extensions, package, revision, policy))
        if not include_existing:
            db.executemany("INSERT INTO events VALUES(?,?,?,0,'ignored',NULL,'')",
                           [(key, path, version) for path, version in existing.items()])
    return key


def change(key, action):
    with database() as db:
        if action == "remove":
            db.execute("DELETE FROM rules WHERE id=?", (key,))
            db.execute("DELETE FROM events WHERE rule=?", (key,))
        elif action == "pause":
            db.execute("UPDATE rules SET enabled=1-enabled WHERE id=?", (key,))
        elif action == "retry":
            db.execute("UPDATE events SET state='pending', observed=?, plan=NULL WHERE rule=? AND state='error'",
                       (time.time(), key))
        else:
            raise ValueError("Bilinmeyen kural eylemi.")


def tick(clock=time.time, dispatch=None):
    if dispatch is None:
        from pivoki_engine.service import dispatch
    active = [r for r in definitions() if r["enabled"]]
    if not active:
        return
    with job_lock("watch-worker") as acquired:
        if not acquired:
            return
        for rule in active:
            key = rule["id"]
            try:
                found = scan(rule["root"], rule["extensions"])
                with database() as db:
                    if not db.execute("SELECT 1 FROM rules WHERE id=? AND enabled=1", (key,)).fetchone():
                        continue
                    # Forget removed names so an identical file moved back can be processed.
                    for old, in db.execute("SELECT path FROM events WHERE rule=?", (key,)).fetchall():
                        if old not in found:
                            db.execute("DELETE FROM events WHERE rule=? AND path=?", (key,old))
                    for path, version in found.items():
                        db.execute("""INSERT INTO events VALUES(?,?,?,?,'pending',NULL,'')
                            ON CONFLICT(rule,path) DO UPDATE SET version=excluded.version, observed=excluded.observed,
                            state='pending',plan=NULL,message='' WHERE version!=excluded.version""",
                                   (key, path, version, clock()))
                    event = db.execute("""SELECT * FROM events WHERE rule=? AND state='pending'
                        AND observed<=? ORDER BY observed,path LIMIT 1""", (key,clock()-SETTLE_SECONDS)).fetchone()
                    if not event:
                        continue
                    plan = event["plan"] or str(uuid.uuid4())
                    db.execute("UPDATE events SET plan=? WHERE rule=? AND path=?", (plan,key,event["path"]))
                # Persist the id before processing. The engine can reconcile a published plan on restart.
                response = dispatch(dict(action="plan", planId=plan, inputs=[event["path"]],
                                         outputRoot=rule["destination"], recursive=False,
                                         packageId=rule["package"], revision=rule["revision"], conflictPolicy=rule["policy"]))
                if response.get("status") == "planned":
                    response = dispatch(dict(action="run", planId=plan))
                status = response.get("status")
                message = response.get("directory") or response.get("error") or status or ""
                state = "done" if status in {"success","skipped"} else "error"
                with database() as db:
                    if response.get("code") == "replan_required":
                        db.execute("UPDATE events SET plan=NULL,observed=? WHERE rule=? AND path=?", (clock(),key,event["path"]))
                    else:
                        db.execute("UPDATE events SET state=?,message=? WHERE rule=? AND path=? AND version=?",
                                   (state,message,key,event["path"],event["version"]))
                    db.execute("UPDATE rules SET message=? WHERE id=?", (f"{Path(event['path']).name} · {message}",key))
            except Exception as exc:
                with database() as db:
                    db.execute("UPDATE rules SET message=? WHERE id=?", (str(exc),key))


def parent_running(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        handle = k.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return k.WaitForSingleObject(wintypes.HANDLE(handle), 0) == 258
        finally:
            k.CloseHandle(wintypes.HANDLE(handle))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def serve(parent_pid):
    while parent_running(parent_pid):
        tick()
        time.sleep(2)
    return 0
