"""Directory handles keep file operations anchored to their intended volume and parent."""
from contextlib import contextmanager, ExitStack
import ctypes
import errno
import os
from pathlib import Path
import shutil
import stat
import sys

from .model import Problem, identity, linked


@contextmanager
def windows_directory(path):
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
    create.restype = w.HANDLE
    # Hold ancestors without delete sharing. OPEN_REPARSE_POINT prevents a link substitution.
    handle = create(str(path), 0x80, 3, None, 3, 0x02200000, None)
    if handle == w.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        st = path.lstat()
        if linked(st) or not stat.S_ISDIR(st.st_mode):
            raise Problem("unsafe_output", f"Choose an ordinary destination folder: {path}")
        yield handle
    finally:
        kernel.CloseHandle(w.HANDLE(handle))


class Directory:
    def __init__(self, path, fd=None):
        self.path = path
        self.fd = fd

    def sync(self):
        if self.fd is not None:
            os.fsync(self.fd)

    def stat(self, name):
        if self.fd is None:
            return (self.path / name).lstat()
        return os.stat(name, dir_fd=self.fd, follow_symlinks=False)

    def mkdir(self, name):
        if self.fd is None:
            (self.path / name).mkdir(mode=0o700)
        else:
            os.mkdir(name, mode=0o700, dir_fd=self.fd)

    @contextmanager
    def child(self, name, *, create=False):
        if create:
            try:
                self.mkdir(name)
            except FileExistsError:
                pass
        path = self.path / name
        if self.fd is None:
            with windows_directory(path):
                yield Directory(path)
        else:
            fd = os.open(name, os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY, dir_fd=self.fd)
            try:
                yield Directory(path, fd)
            finally:
                os.close(fd)

    def file(self, name, mode):
        flags = os.O_EXCL | os.O_CREAT | os.O_WRONLY if mode == "wb" else os.O_RDONLY
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        if self.fd is None:
            target = self.path / name
            if mode == "rb" and linked(target.lstat()):
                raise Problem("unsafe_output", f"Unexpected link in the package: {target}")
            fd = os.open(target, flags, 0o600)
        else:
            fd = os.open(name, flags, 0o600, dir_fd=self.fd)
        return os.fdopen(fd, mode)

    @contextmanager
    def subdirectory(self, parts, *, create=False):
        with ExitStack() as stack:
            current = self
            for part in parts:
                current = stack.enter_context(current.child(part, create=create))
            yield current

    def publish(self, source, dest):
        if self.fd is None:
            # Windows rename fails if the destination exists (even an empty directory).
            os.rename(self.path / source, self.path / dest)
            return
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            operation = libc.renameatx_np
            flag = 4  # RENAME_EXCL
        else:
            operation = getattr(libc, "renameat2", None)
            flag = 1  # RENAME_NOREPLACE
        if operation is None:
            raise Problem("publication_unavailable", "This system lacks safe exclusive directory publication.")
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        if operation(self.fd, os.fsencode(source), self.fd, os.fsencode(dest), flag) == -1:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), str(self.path / dest))

    def cleanup(self, name, expected):
        try:
            st = self.stat(name)
        except FileNotFoundError:
            return
        if expected and identity(st) == expected and not linked(st):
            if self.fd is None:
                shutil.rmtree(self.path / name)
            else:
                shutil.rmtree(name, dir_fd=self.fd)


@contextmanager
def output_root(path, anchor, *, create=False):
    path = Path(path)
    with ExitStack() as stack:
        base = Path(path.anchor)
        if os.name == "nt":
            stack.enter_context(windows_directory(base))
            current = Directory(base)
        else:
            fd = os.open(base, os.O_DIRECTORY | os.O_RDONLY)
            stack.callback(os.close, fd)
            current = Directory(base, fd)
        for part in path.relative_to(base).parts:
            current = stack.enter_context(current.child(part, create=create and current.path.is_relative_to(anchor["path"])))
            if str(current.path) == anchor["path"]:
                st = os.fstat(current.fd) if current.fd is not None else current.path.stat()
                if identity(st) != anchor["identity"]:
                    raise Problem("unsafe_output", f"Destination changed after planning: {current.path}")
        yield current
