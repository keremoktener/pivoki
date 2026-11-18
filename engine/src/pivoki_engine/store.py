from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

from .model import DEFAULT, PRESET, Problem, dump, identifier, package_definition


def data_home():
    if custom := os.environ.get("PIVOKI_DATA_DIR"):
        return Path(custom).expanduser().absolute()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Pivoki/Engine"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Pivoki/Engine"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "pivoki/engine"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def database():
    home = data_home()
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(home / "engine.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS packages (id TEXT, rev INTEGER, doc TEXT NOT NULL,
                PRIMARY KEY (id, rev));
            CREATE TABLE IF NOT EXISTS catalog (id TEXT PRIMARY KEY, rev INTEGER, active INTEGER);
            CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, request TEXT, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, plan TEXT UNIQUE, state TEXT,
                meta TEXT NOT NULL, result TEXT, cancel INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
        """)
        with db:
            db.execute("INSERT OR IGNORE INTO packages VALUES (?,1,?)", (DEFAULT, dump(PRESET)))
            db.execute("INSERT OR IGNORE INTO catalog VALUES (?,1,1)", (DEFAULT,))
        yield db
    finally:
        db.close()


def get_package(db, package_id, revision=None):
    uid = identifier(package_id, "packageId")
    rec = db.execute("SELECT rev FROM catalog WHERE id=? AND active=1", (uid,)).fetchone()
    if not rec:
        raise Problem("package_missing", "This package is unavailable.")
    if revision is None:
        revision = rec[0]
    if revision is not None and (type(revision) is not int or revision < 1):
        raise Problem("invalid_argument", "revision must be a positive integer.")
    rec = db.execute("SELECT doc FROM packages WHERE id=? AND rev=?", (uid, revision)).fetchone()
    if not rec:
        raise Problem("package_missing", "The package revision is unavailable.")
    return json.loads(rec[0])


def insert_history(db, entry):
    db.execute("INSERT INTO history VALUES (?,?)", (entry["jobId"], dump(entry)))
    db.execute("DELETE FROM history WHERE rowid NOT IN (SELECT rowid FROM history ORDER BY rowid DESC LIMIT 50)")


def save_package(db, doc):
    parsed = package_definition(doc)
    uid = identifier(doc["packageId"], "packageId") if doc.get("packageId") else str(uuid4())
    with db:
        db.execute("BEGIN IMMEDIATE")
        rec = db.execute("SELECT rev, active FROM catalog WHERE id=?", (uid,)).fetchone()
        if rec and (not rec["active"] or doc.get("revision", rec["rev"]) != rec["rev"]):
            raise Problem("stale_revision", "Reload the latest package revision before saving.")
        parsed.update(packageId=uid, revision=(rec["rev"] if rec else 0) + 1)
        db.execute("INSERT INTO packages VALUES (?,?,?)", (uid, parsed["revision"], dump(parsed)))
        db.execute("INSERT OR REPLACE INTO catalog VALUES (?,?,1)", (uid, parsed["revision"]))
    return parsed


@contextmanager
def job_lock(plan_id):
    """The OS releases this lock if a worker is killed, including during publication."""
    folder = data_home() / "locks"
    folder.mkdir(mode=0o700, exist_ok=True)
    # Locks are stable inodes. Unlinking a locked inode permits a second concurrent owner.
    with (folder / plan_id).open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                yield False
                return
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
        yield True
