"""Prepare exports on the destination volume and publish without overwriting."""
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def new_file(target):
    from pivoki_engine.filesystem import output_root
    from pivoki_engine.model import inspect_root

    requested = Path(target).absolute()
    parent = requested.parent.resolve(strict=True)
    target = parent / requested.name
    if not parent.is_dir():
        raise ValueError("Önce mevcut bir hedef klasör seçin.")
    if os.path.lexists(target):
        raise FileExistsError(f"Bu ad kullanımda. Başka bir ad seçin. {target}")
    # Use the engine's exclusive rename on the target volume. This also works
    # with removable filesystems where hard links are unavailable.
    with output_root(parent, inspect_root(parent)) as root:
        with tempfile.TemporaryDirectory(prefix=".pivoki-studio-", dir=parent) as work:
            prepared = Path(work) / target.name
            yield prepared
            if not prepared.is_file() or prepared.is_symlink() or prepared.stat().st_size == 0:
                raise ValueError("Çıktı boş veya doğrulanamadı.")
            root.publish(str(prepared.relative_to(parent)), target.name)


def tool(name):
    """Finder-launched bundles do not inherit the user's interactive shell PATH."""
    managed = None
    if name in {"ffmpeg", "ffprobe"}:
        if sys.platform == "darwin":
            managed = Path.home() / "Library/Application Support/Pivoki/Tools/media-v1"
        elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
            managed = Path(os.environ["LOCALAPPDATA"]) / "Pivoki/Tools/v1"
    path = shutil.which(name, path=str(managed)) if managed else None
    path = path or shutil.which(name)
    if not path and os.name != "nt":
        path = shutil.which(name, path="/opt/homebrew/bin:/usr/local/bin:/usr/bin")
    if not path:
        raise ValueError(f"Bu işlem için {name} kurulmalı.")
    return path
