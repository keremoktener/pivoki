import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from .images import EXTENSIONS, fingerprint, inspect_image
from .model import (DEFAULT, Problem, absolute, dump, file_stem, identifier, inspect_root,
                    linked, package_definition, volume_key)
from .store import get_package

BUNDLES = {".pages", ".rtfd", ".numbers", ".key", ".app", ".photoslibrary"}


def scan(inputs, output, recursive, name, check):
    sources, skipped = {}, []
    visited = set()

    def exclude(path, reason):
        skipped.append({"source": str(path), "reason": reason})

    def visit(path, top):
        check()
        try:
            st = path.lstat()
            if linked(st):
                exclude(path, "symbolic_link")
            elif stat.S_ISDIR(st.st_mode):
                if path.suffix.lower() in BUNDLES:
                    exclude(path, "document_bundle")
                elif not top and (path == output or path.name.startswith(".pivoki-stage-")
                                  or (path.parent == output and (path.name == name or path.name.startswith(name + " (")))):
                    exclude(path, "output_directory")
                elif not top and not recursive:
                    exclude(path, "subfolder_excluded")
                elif (st.st_dev, st.st_ino) not in visited:
                    visited.add((st.st_dev, st.st_ino))
                    for entry in sorted(path.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
                        visit(entry, False)
            elif stat.S_ISREG(st.st_mode) and path.suffix.lower() in EXTENSIONS:
                if str(path) not in sources:
                    inspect_image(path)
                    sources[str(path)] = fingerprint(path, check)
            else:
                exclude(path, "unsupported_format")
        except (PermissionError, FileNotFoundError) as exc:
            if top:
                raise Problem("input_unavailable", f"Cannot open the selected input: {path}") from exc
            exclude(path, "unreadable")
        except Problem as exc:
            if top or exc.code != "invalid_image":
                raise
            exclude(path, exc.code)

    for path in sorted({absolute(p) for p in inputs}, key=lambda p: (str(p).casefold(), str(p))):
        visit(path, True)
    return sources, skipped


def existing_leaf(root, relative):
    """A link or non-directory at any ancestor also blocks this proposed path."""
    path = root
    for part in relative.parts:
        if not os.path.lexists(path):
            return False
        st = path.lstat()
        if linked(st) or not stat.S_ISDIR(st.st_mode):
            return True
        path /= part
    return os.path.lexists(path)


def layout(sources, pkg, out, policy, key):
    base = pkg["name"]
    original = out / base
    directory = original
    counter = 2
    while os.path.lexists(directory):
        directory = out / f"{base} ({counter})"
        counter += 1
    occupied = set()
    for spec in pkg["outputs"]:
        directory_path = Path(spec["relativeDir"])
        occupied.update(key(p.as_posix()) for p in [directory_path, *directory_path.parents] if p != Path("."))
    rows = []
    for source in sources:
        for i, spec in enumerate(pkg["outputs"]):
            folder = Path(spec["relativeDir"])
            stem = file_stem(Path(source).stem)
            ext = "." + spec["format"]
            relative = folder / (stem + ext)
            original_name = original / relative
            row = {"source": source, "target": str(directory / relative), "originalTarget": str(original_name),
                   "outputIndex": i, "status": "planned", "reason": ""}
            candidate = relative
            collision = key(candidate.as_posix()) in occupied
            if policy == "skip" and (collision or existing_leaf(original, relative)):
                row.update(status="skipped", reason="name_conflict", target=str(original_name))
            else:
                number = 2
                while key(candidate.as_posix()) in occupied:
                    candidate = folder / f"{stem} ({number}){ext}"
                    number += 1
                occupied.add(key(candidate.as_posix()))
                row.update(target=str(directory / candidate), relativePath=candidate.as_posix())
                if collision or directory != original:
                    row["reason"] = "kept_both"
            rows.append(row)
    return directory, rows


def public_plan(doc):
    return {field: doc[field] for field in ("status", "planId", "packageId", "revision", "name",
                                              "directory", "rows", "skipped", "inputCount", "conflictCount")}


def plan(db, request, check):
    supplied_id = request.get("planId")
    pid = identifier(supplied_id, "planId") if supplied_id else str(uuid4())
    command = dump({k: v for k, v in request.items() if k not in ("action", "planId")})
    if supplied_id:
        prior = db.execute("SELECT request,doc FROM plans WHERE id=?", (pid,)).fetchone()
        if prior:
            if prior["request"] != command:
                raise Problem("plan_id_conflict", "This plan ID already identifies another request.")
            return public_plan(json.loads(prior["doc"]))
    inputs = request.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise Problem("invalid_argument", "Select one or more input files or folders.")
    recursive = request.get("recursive", False)
    policy = request.get("conflictPolicy", "keep-both")
    if type(recursive) is not bool or policy not in ("keep-both", "skip"):
        raise Problem("invalid_argument", "Choose a valid folder scope and conflict policy.")
    if "package" in request:
        pkg = package_definition(request["package"])
        pkg.update(packageId=None, revision=1)
    else:
        pkg = get_package(db, request.get("packageId", DEFAULT), request.get("revision"))
    out = absolute(request.get("outputRoot"))
    anchor = inspect_root(out)
    sources, skipped = scan(inputs, out, recursive, pkg["name"], check)
    directory, rows = layout(sources, pkg, out, policy, volume_key(Path(anchor["path"])))
    doc = {"status": "planned", "planId": pid, "packageId": pkg["packageId"], "revision": pkg["revision"],
           "name": pkg["name"], "outputs": pkg["outputs"], "anchor": anchor, "outputRoot": str(out),
           "directory": str(directory), "sources": sources, "rows": rows, "skipped": skipped,
           "inputCount": len(sources), "conflictCount": sum(bool(r["reason"]) for r in rows)}
    with db:
        db.execute("INSERT OR IGNORE INTO plans VALUES (?,?,?)", (pid, command, dump(doc)))
        prior = db.execute("SELECT request,doc FROM plans WHERE id=?", (pid,)).fetchone()
        if prior["request"] != command:
            raise Problem("plan_id_conflict", "This plan ID already identifies another request.")
    return public_plan(json.loads(prior["doc"]))
