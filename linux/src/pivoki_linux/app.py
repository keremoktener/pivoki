import argparse
from collections import Counter
import os
import subprocess
import sys
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlsplit

from pivoki_engine.model import Problem
from pivoki_engine.service import dispatch


def tr(english, turkish):
    lang = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    )
    return turkish if lang.lower().startswith("tr") else english


def create_root():
    root = tk.Tk(className="Pivoki")
    try:
        from tkinterdnd2 import TkinterDnD

        TkinterDnD.require(root)
    except (ImportError, RuntimeError, tk.TclError, OSError):
        return root, False
    return root, True


def session_label(session, backend, dnd):
    if session.lower() == "wayland":
        name = "Wayland / XWayland" if backend == "x11" else "Wayland"
        drop = tr(
            "in-window drop via the compositor",
            "pencereye bırakma, bileşik yönetici üzerinden",
        )
    elif backend == "x11" or session.lower() == "x11":
        name, drop = "X11", tr("in-window Xdnd drop", "pencereye Xdnd ile bırakma")
    else:
        name, drop = session or backend, tr("in-window drop", "pencereye bırakma")
    if not dnd:
        drop = tr("file chooser", "dosya seçici")
    return f"{name}  ·  {drop}  ·  " + tr("Ctrl+O in Pivoki", "Pivoki içinde Ctrl+O")


def drop_files(root, payload):
    # Some Xdnd sources send one unquoted absolute filename, including spaces.
    if (
        isinstance(payload, str)
        and payload.startswith("/")
        and os.path.lexists(payload)
    ):
        return [payload]
    accepted = []
    for token in root.tk.splitlist(payload):
        if token.startswith("/"):
            accepted.append(token)
            continue
        parsed = urlsplit(token)
        if (
            parsed.scheme == "file"
            and parsed.netloc in ("", "localhost")
            and parsed.path.startswith("/")
        ):
            accepted.append(unquote(parsed.path))
    return accepted


def button(parent, text, command, **kw):
    return ttk.Button(parent, text=text, command=command, **kw)


def tree(parent, columns, heights, width):
    frame = ttk.Frame(parent)
    value = ttk.Treeview(
        frame,
        columns=[k for k, _ in columns],
        show="headings",
        height=heights,
        selectmode="browse",
    )
    for (key, title), size in zip(columns, width):
        value.heading(key, text=title, anchor="w")
        value.column(key, anchor="w", width=size, minwidth=min(size, 70))
    vertical = ttk.Scrollbar(frame, command=value.yview)
    horizontal = ttk.Scrollbar(frame, orient="horizontal", command=value.xview)
    value.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    value.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    return frame, value


class Workspace:
    def __init__(self, root, dnd=False):
        self.root, self.dnd = root, dnd
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.task = None
        self.closing = False
        self.inputs = []
        self.plan = None
        self.history_items = []
        self.destination = tk.StringVar(root)
        self.recursive = tk.BooleanVar(root, False)
        self.command = tk.StringVar(root)
        self.keep_both = tr("Keep both", "İki kopyayı sakla")
        self.skip = tr("Skip", "Atla")
        self.policy = tk.StringVar(root, self.keep_both)
        self.status = tk.StringVar(root)
        self.exact_path = tk.StringVar(root)
        self.last_dir = None
        self.root.title("Pivoki")
        root.geometry("960x730")
        root.minsize(710, 640)
        style = ttk.Style(root)
        if root.tk.call("tk", "windowingsystem") == "x11":
            style.theme_use("clam")
            style.configure(
                ".",
                font=("DejaVu Sans", 10),
                background="#fbfaf6",
                foreground="#202921",
            )
            style.configure("TButton", padding=(9, 5))
            style.configure("Treeview", rowheight=26, fieldbackground="white")
            style.map(
                "Treeview",
                background=[("selected", "#356343")],
                foreground=[("selected", "white")],
            )
            style.configure("Accent.TButton", background="#356343", foreground="white")
            style.map(
                "Accent.TButton",
                background=[("disabled", "#d8dfd5"), ("active", "#294e35")],
                foreground=[("disabled", "#435244")],
            )
        header = ttk.Frame(root, padding=(18, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Pivoki", font=("TkDefaultFont", 21, "bold")).pack(
            side="left"
        )
        button(header, tr("Open Studio", "Studio’yu aç"), self.open_studio).pack(
            side="right"
        )
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=16)
        self.home = ttk.Frame(self.tabs, padding=12)
        self.library = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.home, text=tr("Create outputs", "Çıktı oluştur"))
        self.tabs.add(self.library, text=tr("Library", "Kütüphane"))
        self.form()
        self.library_form()
        session = os.environ.get("XDG_SESSION_TYPE") or (
            "Wayland" if os.environ.get("WAYLAND_DISPLAY") else ""
        )
        ttk.Label(
            root,
            text=session_label(session, root.tk.call("tk", "windowingsystem"), dnd),
            padding=(16, 7),
        ).pack(fill="x")
        self.tabs.bind("<<NotebookTabChanged>>", self.change_tab)
        for var in (self.command, self.destination, self.policy, self.recursive):
            var.trace_add("write", self.invalidate)
        root.bind("<Control-o>", lambda e: self.pick_files())
        root.bind(
            "<Control-Return>", lambda e: self.run() if self.plan else self.preview()
        )
        root.bind("<Escape>", lambda e: self.cancel())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.load_commands()
        self.invalidate()

    def form(self):
        page = self.home
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)
        bar = ttk.Frame(page)
        bar.grid(row=0, column=0, sticky="ew")
        title = (
            tr("Drop files or folders here", "Dosyaları veya klasörleri buraya bırakın")
            if self.dnd
            else tr("Inputs", "Girdiler")
        )
        ttk.Label(bar, text=title, font=("TkDefaultFont", 11, "bold")).pack(side="left")
        button(bar, tr("Files…", "Dosyalar…"), self.pick_files).pack(side="right")
        button(bar, tr("Folder…", "Klasör…"), self.pick_folder).pack(
            side="right", padx=4
        )
        button(bar, tr("Remove", "Kaldır"), self.remove_inputs).pack(side="right")
        self.listbox = tk.Listbox(
            page,
            height=3,
            selectmode="extended",
            activestyle="dotbox",
            relief="solid",
            borderwidth=1,
            exportselection=False,
        )
        self.listbox.grid(row=1, column=0, sticky="ew", pady=5)
        self.listbox.bind("<Delete>", lambda e: self.remove_inputs())
        if self.dnd:
            self.listbox.drop_target_register("DND_Files")
            self.listbox.dnd_bind("<<Drop>>", self.drop)
        config = ttk.Frame(page)
        config.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        config.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            config,
            text=tr("Include subfolders", "Alt klasörleri dahil et"),
            variable=self.recursive,
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(config, text=tr("Output package", "Çıktı paketi")).grid(
            row=1, column=0, sticky="w", padx=(0, 12)
        )
        self.commands = ttk.Combobox(
            config, state="readonly", textvariable=self.command
        )
        self.commands.grid(row=1, column=1, sticky="ew")
        button(
            config, tr("Edit packages…", "Paketleri düzenle…"), self.edit_packages
        ).grid(row=1, column=2, padx=(8, 0))
        ttk.Label(config, text=tr("Destination", "Hedef klasör")).grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(config, textvariable=self.destination).grid(
            row=2, column=1, sticky="ew", pady=5
        )
        button(config, tr("Choose…", "Seç…"), self.pick_destination).grid(
            row=2, column=2, sticky="ew", padx=(8, 0)
        )
        ttk.Label(config, text=tr("Name conflicts", "Ad çakışmaları")).grid(
            row=3, column=0, sticky="w"
        )
        ttk.Combobox(
            config,
            textvariable=self.policy,
            values=[self.keep_both, self.skip],
            state="readonly",
            width=22,
        ).grid(row=3, column=1, sticky="w")
        self.preview_btn = button(config, tr("Preview plan", "Planı gör"), self.preview)
        self.preview_btn.grid(row=3, column=2, sticky="ew", padx=(8, 0))
        ttk.Label(
            page,
            text=tr("Output plan", "Çıktı planı"),
            font=("TkDefaultFont", 11, "bold"),
        ).grid(row=4, column=0, sticky="w")
        frame, self.rows = tree(
            page,
            [
                ("source", tr("Source", "Kaynak")),
                ("original", tr("Original target", "Özgün hedef")),
                ("target", tr("Planned target", "Planlanan hedef")),
                ("reason", tr("Status", "Durum")),
            ],
            4,
            [185, 255, 270, 125],
        )
        frame.grid(row=5, column=0, sticky="nsew", pady=5)
        self.rows.bind("<<TreeviewSelect>>", self.selected_path)
        ttk.Entry(page, textvariable=self.exact_path, state="readonly").grid(
            row=6, column=0, sticky="ew"
        )
        actions = ttk.Frame(page)
        actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self.run_btn = button(
            actions,
            tr("Create approved outputs", "Onaylanan çıktıları oluştur"),
            self.run,
            style="Accent.TButton",
        )
        self.run_btn.pack(side="right")
        self.stop_btn = button(actions, tr("Cancel", "İptal"), self.cancel)
        self.stop_btn.pack(side="right", padx=4)
        self.show_btn = button(
            actions, tr("Open output folder", "Çıktı klasörünü aç"), self.open_last
        )
        self.show_btn.pack(side="left")
        ttk.Label(page, textvariable=self.status, wraplength=680).grid(
            row=8, column=0, sticky="w", pady=(6, 0)
        )

    def library_form(self):
        box, self.history_table = tree(
            self.library,
            [
                ("name", tr("Job", "İş")),
                ("time", tr("Saved", "Kaydedildi")),
                ("directory", tr("Folder", "Klasör")),
            ],
            8,
            [160, 175, 420],
        )
        box.pack(fill="both", expand=True)
        self.history_table.bind("<Double-Button-1>", lambda e: self.open_history())
        self.history_table.bind("<Return>", lambda e: self.open_history())
        bar = ttk.Frame(self.library, padding=(0, 8))
        bar.pack(fill="x")
        button(bar, tr("Open folder", "Klasörü aç"), self.open_history).pack(
            side="left"
        )
        button(
            bar, tr("Remove from history", "Geçmişten kaldır"), self.remove_history
        ).pack(side="left", padx=4)
        button(bar, tr("Clear history…", "Geçmişi temizle…"), self.clear_history).pack(
            side="right"
        )

    def load_commands(self, prefer=None):
        reply = dispatch({"action": "packages"})
        packages = reply.get("packages", [])
        labels = [f"{p['name']} · r{p['revision']}" for p in packages]
        duplicates = Counter(labels)
        self.packages = {
            (f"{label} · {p['packageId'][:8]}" if duplicates[label] > 1 else label): p
            for label, p in zip(labels, packages)
        }
        self.choices = {
            label: {"packageId": p["packageId"], "revision": p["revision"]}
            for label, p in self.packages.items()
        }
        for fmt in dispatch({"action": "catalog"}).get("outputs", []):
            label = "JPEG" if fmt == "jpg" else fmt.upper()
            self.choices[label] = {
                "package": {
                    "name": label,
                    "outputs": [{"format": fmt, "maxEdge": 65535, "relativeDir": ""}],
                }
            }
        names = list(self.choices)
        self.commands.configure(values=names)
        selected = next(
            (
                k
                for k, v in self.choices.items()
                if prefer and v.get("packageId") == prefer
            ),
            None,
        )
        self.command.set(selected or (names[0] if names else ""))
        if reply["status"] == "failed":
            self.status.set(reply["error"])

    def invalidate(self, *_):
        self.plan = None
        self.last_dir = None
        self.exact_path.set("")
        self.row_paths = {}
        self.rows.delete(*self.rows.get_children())
        if not self.task:
            self.status.set(
                tr(
                    "Select inputs and a destination, then preview the output paths.",
                    "Girdileri ve hedef klasörü seçip çıktı yollarını inceleyin.",
                )
            )
        self.update_buttons()

    def update_buttons(self):
        busy = self.task is not None
        ready = bool(
            self.inputs and self.command.get() and self.destination.get().strip()
        )
        for widget, enabled in [
            (self.preview_btn, ready and not busy),
            (
                self.run_btn,
                bool(
                    self.plan
                    and any(r["status"] == "planned" for r in self.plan["rows"])
                )
                and not busy,
            ),
            (self.stop_btn, busy and not self.cancel_event.is_set()),
            (self.show_btn, bool(self.last_dir)),
        ]:
            widget.state(["!disabled" if enabled else "disabled"])

    def add_inputs(self, paths):
        if self.task:
            return
        for path in paths:
            value = os.fspath(path)
            if value and value not in self.inputs:
                self.inputs.append(value)
                self.listbox.insert("end", value)
        self.invalidate()

    def remove_inputs(self):
        if self.task:
            return
        for index in reversed(self.listbox.curselection()):
            self.listbox.delete(index)
            self.inputs.pop(index)
        self.invalidate()

    def drop(self, event):
        paths = drop_files(self.root, event.data)
        if not paths or self.task:
            return "refuse_drop"
        self.add_inputs(paths)
        return "copy"

    def pick_files(self):
        if not self.task:
            self.add_inputs(filedialog.askopenfilenames(parent=self.root))

    def pick_folder(self):
        if not self.task:
            folder = filedialog.askdirectory(parent=self.root)
            if folder:
                self.add_inputs([folder])

    def pick_destination(self):
        if not self.task:
            folder = filedialog.askdirectory(parent=self.root)
            if folder:
                self.destination.set(folder)

    def begin(self, request, callback, label):
        if self.task:
            return
        self.cancel_event = Event()

        def check():
            if self.cancel_event.is_set():
                raise Problem("cancelled", tr("Cancelled", "İptal edildi"))

        self.status.set(label)
        self.task = self.executor.submit(dispatch, request, check)
        self.update_buttons()

        def poll():
            if not self.task.done():
                self.root.after(40, poll)
                return
            future, self.task = self.task, None
            try:
                reply = future.result()
                if reply["status"] in ("failed", "cancelled"):
                    self.plan = None
                    self.status.set(reply.get("error", reply["status"]))
                else:
                    callback(reply)
            except Exception as exc:
                self.status.set(str(exc))
            self.update_buttons()
            if self.closing:
                self.close()

        self.root.after(5, poll)

    def request(self):
        return {
            "action": "plan",
            "inputs": list(self.inputs),
            "outputRoot": self.destination.get(),
            "recursive": self.recursive.get(),
            "conflictPolicy": "skip" if self.policy.get() == self.skip else "keep-both",
            **self.choices[self.command.get()],
        }

    def preview(self):
        if (
            self.task
            or not self.inputs
            or not self.destination.get().strip()
            or self.command.get() not in self.choices
        ):
            return
        self.invalidate()
        request = self.request()

        def ready(reply):
            if self.request() != request:
                self.invalidate()
                return
            self.plan = reply
            directory = Path(reply["directory"])
            for row in reply["rows"]:
                original = Path(row["originalTarget"])
                target = Path(row["target"])
                node = self.rows.insert(
                    "",
                    "end",
                    values=[
                        Path(row["source"]).name,
                        original.relative_to(directory.parent / reply["name"]),
                        target.relative_to(directory.parent),
                        self.reason(row["reason"] or row["status"]),
                    ],
                )
                self.row_paths[node] = row["target"]
            for item in reply["skipped"]:
                node = self.rows.insert(
                    "",
                    "end",
                    values=[
                        Path(item["source"]).name,
                        "",
                        "",
                        self.reason(item["reason"]),
                    ],
                )
                self.row_paths[node] = item["source"]
            if self.row_paths:
                self.rows.selection_set(next(iter(self.row_paths)))
                self.selected_path()
            count = sum(r["status"] == "planned" for r in reply["rows"])
            conflicts = reply["conflictCount"]
            self.status.set(
                tr(
                    f"{count} outputs · {conflicts} name conflicts. Review the paths before creating outputs.",
                    f"{count} çıktı · {conflicts} ad çakışması. Oluşturmadan önce yolları kontrol edin.",
                )
            )

        self.begin(
            request, ready, tr("Preparing output plan…", "Çıktı planı hazırlanıyor…")
        )

    @staticmethod
    def reason(code):
        words = {
            "planned": ("Planned", "Planlandı"),
            "kept_both": ("Keeping both copies", "İki kopya saklanacak"),
            "name_conflict": ("Skipped · name conflict", "Atlandı · adaş dosya"),
            "subfolder_excluded": ("Subfolder excluded", "Alt klasör dışlandı"),
            "document_bundle": ("Document bundle", "Belge paketi"),
            "symbolic_link": ("Symbolic link", "Sembolik bağlantı"),
            "invalid_image": ("Invalid image", "Geçersiz görsel"),
            "unreadable": ("Unreadable", "Okunamıyor"),
            "output_directory": ("Output directory", "Çıktı klasörü"),
            "unsupported_format": ("Unsupported format", "Desteklenmeyen biçim"),
        }
        return tr(*words[code]) if code in words else code

    def selected_path(self, _=None):
        if selection := self.rows.selection():
            self.exact_path.set(self.row_paths.get(selection[0], ""))

    def run(self):
        if (
            self.task
            or not self.plan
            or not any(r["status"] == "planned" for r in self.plan["rows"])
        ):
            return
        pid = self.plan["planId"]
        self.plan = None

        def finished(reply):
            self.last_dir = reply.get("directory")
            if self.last_dir:
                self.status.set(tr("Saved to ", "Kaydedildi · ") + self.last_dir)
            else:
                self.status.set(
                    tr("All outputs were skipped.", "Tüm çıktılar atlandı.")
                )
            self.refresh_history()

        self.begin(
            {"action": "run", "planId": pid},
            finished,
            tr("Creating outputs…", "Çıktılar oluşturuluyor…"),
        )

    def cancel(self):
        if self.task:
            self.cancel_event.set()
            self.status.set(tr("Cancelling…", "İptal ediliyor…"))
            self.update_buttons()

    def change_tab(self, _):
        if self.tabs.select() == str(self.library):
            self.refresh_history()

    def refresh_history(self):
        reply = dispatch({"action": "history"})
        if reply["status"] == "failed":
            self.status.set(reply["error"])
            return
        self.history_items = reply["jobs"]
        self.history_table.delete(*self.history_table.get_children())
        for job in self.history_items:
            self.history_table.insert(
                "",
                "end",
                iid=job["jobId"],
                values=[
                    job["name"],
                    job["createdAt"][:19].replace("T", " ") + " UTC",
                    job["directory"],
                ],
            )

    def open_path(self, path):
        if not Path(path).is_dir():
            messagebox.showinfo(
                "Pivoki",
                tr("Last known location: ", "Son bilinen konum: ") + path,
                parent=self.root,
            )
            return
        try:
            subprocess.Popen(["xdg-open", path], start_new_session=True)
        except OSError as exc:
            messagebox.showerror("Pivoki", str(exc), parent=self.root)

    def open_last(self):
        if self.last_dir:
            self.open_path(self.last_dir)

    def open_history(self):
        if choice := self.history_table.selection():
            self.open_path(self.history_table.item(choice[0], "values")[2])

    def remove_history(self):
        if choice := self.history_table.selection():
            reply = dispatch({"action": "removeHistory", "jobId": choice[0]})
            if reply["status"] == "failed":
                messagebox.showerror("Pivoki", reply["error"], parent=self.root)
            self.refresh_history()

    def clear_history(self):
        count = len(self.history_items)
        if count and messagebox.askyesno(
            "Pivoki",
            tr(
                f"Remove {count} history entries? Your files stay in their folders.",
                f"{count} geçmiş kaydı kaldırılsın mı? Dosyalar klasörlerinde kalır.",
            ),
            parent=self.root,
        ):
            reply = dispatch({"action": "clearHistory"})
            if reply["status"] == "failed":
                messagebox.showerror("Pivoki", reply["error"], parent=self.root)
            self.refresh_history()

    def open_studio(self):
        subprocess.Popen(
            [sys.executable, "-m", "pivoki_engine", "studio", "--", *self.inputs],
            start_new_session=True,
        )

    def edit_packages(self):
        if self.task:
            return
        from .editor import edit

        edit(self)

    def close(self):
        if self.task:
            self.closing = True
            self.cancel()
            return
        self.executor.shutdown(wait=False)
        self.root.destroy()


def main(argv=None):
    p = argparse.ArgumentParser(description="Pivoki Linux desktop")
    p.add_argument("paths", nargs="*")
    args = p.parse_args(argv)
    root, drop = create_root()
    app = Workspace(root, drop)
    if args.paths:
        app.add_inputs(args.paths)
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pivoki_engine",
            "watch",
            "--parent-pid",
            str(os.getpid()),
        ]
    )
    root.mainloop()
    return 0
