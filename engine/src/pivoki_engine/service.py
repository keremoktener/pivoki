"""One JSON-compatible request/response contract for the GUI, CLI and folder rules."""
import json
from pathlib import Path
import sqlite3
import sys

import PIL
from PIL import features

from . import __version__
from .images import DECODERS, EXTENSIONS, inspect_image
from .jobs import failure, recover, run
from .model import FORMATS, Problem, absolute, identifier
from .planner import plan
from .store import database, get_package, save_package


def dispatch(request, check=lambda: None):
    try:
        if not isinstance(request, dict):
            raise Problem("invalid_argument", "Expected a JSON request object.")
        action = request.get("action")
        if action == "catalog":
            return {"status": "success", "inputs": sorted(EXTENSIONS), "outputs": list(FORMATS),
                    "tools": ["inspect", "resize"], "version": __version__}
        if action == "dependencies":
            return {"status": "success", "python": sys.version.split()[0], "pillow": PIL.__version__,
                    "engine": __version__, "webp": features.check("webp"), "heif": "HEIF" in DECODERS,
                    "avif": "AVIF" in DECODERS}
        if action == "inspect":
            inputs = request.get("inputs")
            if not isinstance(inputs, list) or not inputs:
                raise Problem("invalid_argument", "Specify an image to inspect.")
            items = []
            for value in inputs:
                path = absolute(value)
                items.append({"source": str(path), "bytes": path.stat().st_size, **inspect_image(path)})
            return {"status": "success", "files": items}
        with database() as db:
            recover(db)
            if action == "packages":
                ids = db.execute("SELECT id,rev FROM catalog WHERE active=1 ORDER BY rowid")
                return {"status": "success", "packages": [get_package(db, r["id"], r["rev"]) for r in ids]}
            if action == "savePackage":
                return {"status": "success", "package": save_package(db, request.get("package"))}
            if action == "deletePackage":
                uid = identifier(request.get("packageId"), "packageId")
                with db:
                    db.execute("UPDATE catalog SET active=0 WHERE id=?", (uid,))
                return {"status": "success"}
            if action == "plan":
                return plan(db, request, check)
            if action == "run":
                return run(db, request, check)
            if action == "cancel":
                pid = identifier(request.get("planId"), "planId")
                with db:
                    cur = db.execute("UPDATE jobs SET cancel=1 WHERE plan=? AND state IN ('running','publishing')", (pid,))
                return {"status": "success", "requested": bool(cur.rowcount)}
            if action == "history":
                return {"status": "success", "jobs": [json.loads(row[0]) for row in
                        db.execute("SELECT doc FROM history ORDER BY rowid DESC LIMIT 50")]}
            if action in ("removeHistory", "clearHistory"):
                with db:
                    if action == "removeHistory":
                        job_id = identifier(request.get("jobId"), "jobId")
                        db.execute("DELETE FROM history WHERE id=?", (job_id,))
                    else:
                        db.execute("DELETE FROM history")
                return {"status": "success"}
            raise Problem("invalid_argument", f"Unknown action: {action!r}")
    except (Problem, OSError, ValueError, TypeError, sqlite3.Error, RecursionError) as exc:
        return failure(exc)
