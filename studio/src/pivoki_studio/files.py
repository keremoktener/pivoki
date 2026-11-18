"""Prepare exports on the destination volume and publish without overwriting."""
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def new_file(target):
    target = Path(target).absolute()
    if not target.parent.is_dir():
        raise ValueError("Önce mevcut bir hedef klasör seçin.")
    if os.path.lexists(target):
        raise FileExistsError(f"Bu ad kullanımda. Başka bir ad seçin. {target}")
    with tempfile.TemporaryDirectory(prefix=".pivoki-studio-", dir=target.parent) as work:
        prepared = Path(work) / target.name
        yield prepared
        if not prepared.is_file() or prepared.stat().st_size == 0:
            raise ValueError("Çıktı boş.")
        if os.name == "nt":
            os.rename(prepared, target)  # Windows fails when the destination exists.
        else:
            os.link(prepared, target)


def tool(name):
    """Finder-launched bundles do not inherit the user's interactive shell PATH."""
    path = shutil.which(name)
    if not path and os.name != "nt":
        path = shutil.which(name, path="/opt/homebrew/bin:/usr/local/bin:/usr/bin")
    if not path:
        raise ValueError(f"Bu işlem için {name} kurulmalı.")
    return path
