import time
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOKI_DATA_DIR", str(tmp_path / "state"))
    from pivoki_linux.app import Workspace, create_root

    root, dnd = create_root()
    root.withdraw()
    app = Workspace(root, dnd)
    yield app
    app.close()


def settle(app):
    limit = time.monotonic() + 20
    while app.task is not None and time.monotonic() < limit:
        app.root.update()
        time.sleep(0.01)
    assert app.task is None, app.status.get()


def test_drop_data_preserves_unicode_and_rejects_remote_links(desktop):
    from pivoki_linux.app import drop_files

    assert drop_files(
        desktop.root,
        "{/tmp/ürün 1.png} file:///tmp/a%20b.jpg https://example.com/x.png",
    ) == ["/tmp/ürün 1.png", "/tmp/a b.jpg"]


def test_desktop_plan_approval_conversion_and_library(desktop, tmp_path):
    source = tmp_path / "İki resim.jpg"
    Image.new("RGB", (93, 57), "green").save(source)
    desktop.add_inputs([source])
    desktop.destination.set(str(tmp_path / "Output"))
    desktop.command.set("PNG")
    assert not desktop.recursive.get()
    desktop.preview()
    settle(desktop)
    assert desktop.plan["status"] == "planned", desktop.status.get()
    path = Path(desktop.plan["rows"][0]["target"])
    assert not path.exists()
    desktop.run()
    settle(desktop)
    with Image.open(path) as result:
        assert result.format == "PNG" and result.size == (93, 57)
    assert desktop.history_items[0]["paths"] == [str(path)]
    desktop.refresh_history()
    assert desktop.history_items[0]["directory"] == str(path.parent)


def test_stale_plan_is_invalidated_before_run(desktop, tmp_path):
    path = tmp_path / "a.jpg"
    Image.new("RGB", (10, 4)).save(path)
    desktop.add_inputs([path])
    desktop.destination.set(str(tmp_path / "out"))
    desktop.preview()
    settle(desktop)
    assert desktop.plan
    desktop.recursive.set(True)
    assert desktop.plan is None


def test_session_reports_xwayland_and_global_shortcut_fallback():
    from pivoki_linux.app import session_label

    assert "XWayland" in session_label("Wayland", "x11", True)
    assert "X11" in session_label("X11", "x11", False)
    assert "Ctrl+O" in session_label("Wayland", "x11", False)


def test_xdnd_from_source_window_updates_input_selection(desktop, tmp_path):
    import shutil
    import subprocess
    import tkinter as tk

    if desktop.root.tk.call("tk", "windowingsystem") != "x11" or not shutil.which(
        "xdotool"
    ):
        pytest.skip("Requires an X11/XWayland session with xdotool.")
    assert desktop.dnd, "Install pivoki-desktop[drop] for the protocol test."
    path = tmp_path / "dropped photo.jpg"
    Image.new("RGB", (100, 51)).save(path)
    root = desktop.root
    root.geometry("780x650+0+0")
    root.deiconify()
    sender = tk.Toplevel(root)
    sender.geometry("165x90+830+30")
    label = tk.Label(sender, text="Drag image")
    label.pack(fill="both", expand=True)
    label.drag_source_register(1, "DND_Files")
    label.dnd_bind("<<DragInitCmd>>", lambda event: ("copy", "DND_Files", (str(path),)))
    # The compositor places the two surfaces asynchronously. Wait for their
    # configure events before using screen coordinates for the physical drag.
    deadline = time.monotonic() + 0.65
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)

    def center(widget):
        return [
            widget.winfo_rootx() + widget.winfo_width() // 2,
            widget.winfo_rooty() + widget.winfo_height() // 2,
        ]

    sx, sy = center(label)
    tx, ty = center(desktop.listbox)
    cmd = [
        "xdotool",
        "mousemove",
        sx,
        sy,
        "sleep",
        ".15",
        "mousedown",
        "1",
        "sleep",
        ".1",
        "mousemove",
        sx - 15,
        sy,
        "sleep",
        ".15",
        "mousemove",
        sx - 35,
        sy,
        "sleep",
        ".15",
        "mousemove",
        tx,
        ty,
        "sleep",
        ".3",
        "mouseup",
        "1",
    ]
    mover = subprocess.Popen(list(map(str, cmd)))
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not desktop.inputs:
        root.update()
        time.sleep(0.01)
    mover.wait(timeout=3)
    assert desktop.inputs == [str(path)]


def test_native_file_chooser_selects_a_real_file(desktop, tmp_path):
    root = desktop.root
    if root.tk.call("tk", "windowingsystem") != "x11":
        pytest.skip("Drives the X11/XWayland Tk file dialog.")
    source = tmp_path / "ürün.png"
    Image.new("RGB", (30, 17)).save(source)
    root.deiconify()
    root.update()

    def choose():
        dialog = root.tk.call("grab", "current", ".")
        entry = str(dialog) + ".contents.f2.ent"
        if not root.tk.call("winfo", "exists", entry):
            root.after(40, choose)
            return
        root.tk.call(entry, "delete", 0, "end")
        root.tk.call(entry, "insert", 0, root.tk.call("list", str(source)))
        root.tk.call(str(dialog) + ".contents.f2.ok", "invoke")

    root.after(40, choose)
    # Exit the modal dialog if the backend implementation changes.
    watchdog = root.after(
        8000, lambda: root.tk.call("set", "::tk::Priv(selectFilePath)", "")
    )
    try:
        desktop.pick_files()
    finally:
        root.after_cancel(watchdog)
    assert desktop.inputs == [str(source)]


def test_cancel_button_preserves_earlier_success_and_removes_partial_package(
    desktop, tmp_path, monkeypatch
):
    from threading import Event
    from pivoki_engine import jobs

    source = tmp_path / "photo.png"
    Image.new("RGB", (64, 32)).save(source)
    desktop.add_inputs([source])
    desktop.destination.set(str(tmp_path / "out"))
    desktop.preview()
    settle(desktop)
    desktop.run()
    settle(desktop)
    first = desktop.history_items[0]
    held, release = Event(), Event()
    original = jobs.encode

    def hold(*args):
        held.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(jobs, "encode", hold)
    desktop.preview()
    settle(desktop)
    directory = Path(desktop.plan["directory"])
    desktop.run()
    try:
        assert held.wait(5)
        desktop.cancel()
        assert "disabled" in desktop.stop_btn.state()
    finally:
        release.set()
    settle(desktop)
    desktop.refresh_history()
    assert desktop.history_items == [first]
    assert not directory.exists() and all(Path(p).exists() for p in first["paths"])


def test_library_clear_requires_confirmation_and_preserves_output(
    desktop, tmp_path, monkeypatch
):
    from pivoki_engine.service import record_export

    img = tmp_path / "verified.png"
    Image.new("RGB", (10, 10)).save(img)
    record_export("Single output", [img])
    desktop.refresh_history()
    monkeypatch.setattr("pivoki_linux.app.messagebox.askyesno", lambda *a, **kw: False)
    desktop.clear_history()
    assert len(desktop.history_items) == 1
    monkeypatch.setattr("pivoki_linux.app.messagebox.askyesno", lambda *a, **kw: True)
    desktop.clear_history()
    assert desktop.history_items == [] and img.is_file()
