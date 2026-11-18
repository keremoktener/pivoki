import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys
import unicodedata
from uuid import UUID

DEFAULT = "4c951577-984b-43a3-b90d-d640668837db"
PRESET = {"schemaVersion": 1, "packageId": DEFAULT, "revision": 1, "name": "Mağaza görselleri",
          "outputs": [{"format": "webp", "maxEdge": 1600, "relativeDir": "web"},
                      {"format": "jpg", "maxEdge": 400, "relativeDir": "kucuk"}]}
FORMATS = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP"}
RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)", re.I)
ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class Problem(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code = code
        self.details = details

    def result(self):
        return {"status": "cancelled" if self.code == "cancelled" else "failed",
                "code": self.code, "error": str(self), **self.details}


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def identifier(value, field):
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise Problem("invalid_argument", f"{field} must be a UUID.") from None


def component(name):
    if (not isinstance(name, str) or not name or name in (".", "..") or name[-1] in " ."
            or ILLEGAL.search(name) or RESERVED.match(name) or len(name.encode("utf-8")) > 220):
        raise Problem("invalid_name", f"Invalid filename component: {name!r}")
    return name


def relative_dir(value):
    if value in ("", "."):
        return ""
    if not isinstance(value, str) or PureWindowsPath(value).drive or "\\" in value:
        raise Problem("invalid_path", f"Use a relative folder path: {value!r}")
    return "/".join(component(p) for p in value.split("/"))


def file_stem(stem):
    stem = ILLEGAL.sub("_", stem).strip(" .") or "image"
    if RESERVED.match(stem):
        stem = "_" + stem
    return stem.encode("utf-8")[:180].decode("utf-8", errors="ignore")


def package_definition(doc):
    if not isinstance(doc, dict) or doc.get("schemaVersion", 1) != 1:
        raise Problem("invalid_package", "Expected a version 1 package.")
    name = component(doc.get("name"))
    if name.startswith(".pivoki-"):
        raise Problem("invalid_name", "This name is reserved for temporary files.")
    rows = doc.get("outputs")
    if not isinstance(rows, list) or not rows:
        raise Problem("invalid_package", "Add at least one output.")
    outputs = []
    for row in rows:
        if not isinstance(row, dict):
            raise Problem("invalid_package", "Expected an output definition.")
        fmt = row.get("format")
        fmt = fmt.lower() if isinstance(fmt, str) else ""
        fmt = "jpg" if fmt == "jpeg" else fmt
        edge = row.get("maxEdge")
        if fmt not in FORMATS or type(edge) is not int or not 1 <= edge <= 65535:
            raise Problem("invalid_package", "Choose PNG, JPG or WebP and a maximum edge between 1 and 65535.")
        outputs.append({"format": fmt, "maxEdge": edge, "relativeDir": relative_dir(row.get("relativeDir", ""))})
    return {"schemaVersion": 1, "name": name, "outputs": outputs}


def absolute(value):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise Problem("invalid_path", f"Invalid path: {value!r}")
    path = Path(os.path.abspath(Path(value).expanduser()))
    # macOS publishes these system aliases even when a file chooser returns a logical path.
    if sys.platform == "darwin" and len(path.parts) > 1 and path.parts[1] in ("tmp", "var", "etc"):
        alias = Path("/", path.parts[1])
        if alias.is_symlink() and alias.resolve() == Path("/private", path.parts[1]):
            path = alias.resolve().joinpath(*path.parts[2:])
    return path


def linked(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def identity(st):
    return [st.st_dev, st.st_ino]


def inspect_root(path):
    anchor = Path(path.anchor)
    for candidate in [*reversed(path.parents), path]:
        try:
            st = candidate.lstat()
        except FileNotFoundError:
            break
        if linked(st) or not stat.S_ISDIR(st.st_mode):
            raise Problem("unsafe_output", f"Choose an ordinary destination folder: {candidate}")
        anchor = candidate
    return {"path": str(anchor), "identity": identity(anchor.stat())}


def volume_key(path):
    """Use the actual target volume when its OS exposes its filename comparison policy."""
    case_sensitive = os.name != "nt"
    normalize = sys.platform == "darwin"
    if sys.platform == "darwin":
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        # Darwin _PC_CASE_SENSITIVE (sys/unistd.h).
        case_sensitive = libc.pathconf(os.fsencode(path), 11) == 1
    elif os.name == "nt":
        import ctypes
        from ctypes import wintypes
        from .filesystem import windows_directory
        with windows_directory(path) as handle:
            flags = wintypes.DWORD()
            ok = ctypes.windll.kernel32.GetFileInformationByHandleEx(
                wintypes.HANDLE(handle), 23, ctypes.byref(flags), ctypes.sizeof(flags))
            case_sensitive = bool(ok and flags.value & 1)

    def key(value):
        name = unicodedata.normalize("NFD", value) if normalize else value
        return name if case_sensitive else name.casefold()
    return key
