import tkinter as tk
from tkinter import messagebox, ttk

from pivoki_engine.service import dispatch

from .app import button, tr


def edit(workspace):
    parent = workspace.root
    window = tk.Toplevel(parent)
    window.title(tr("Edit packages", "Paketleri düzenle"))
    window.transient(parent)
    window.grab_set()
    body = ttk.Frame(window, padding=16)
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)
    selected = tk.StringVar(window)
    name = tk.StringVar(window)
    new = tr("New package", "Yeni paket")
    stored = workspace.packages
    chooser = ttk.Combobox(
        body, textvariable=selected, values=[new, *stored], state="readonly", width=37
    )
    ttk.Label(body, text=tr("Package", "Paket")).grid(
        row=0, column=0, sticky="w", padx=(0, 8)
    )
    chooser.grid(row=0, column=1, sticky="ew")
    ttk.Label(body, text=tr("Name", "Ad")).grid(row=1, column=0, sticky="w")
    entry = ttk.Entry(body, textvariable=name)
    entry.grid(row=1, column=1, sticky="ew", pady=7)
    grid = ttk.Frame(body)
    grid.grid(row=2, column=0, columnspan=2, sticky="ew")
    labels = [
        tr("Format", "Biçim"),
        tr("Maximum edge (px)", "Uzun kenar (px)"),
        tr("Relative folder", "Göreli klasör"),
    ]
    for i, title in enumerate(labels):
        ttk.Label(grid, text=title).grid(row=0, column=i, sticky="w", padx=3)
    rows = []

    def add(spec=None):
        spec = spec or {"format": "png", "maxEdge": 1600, "relativeDir": ""}
        row = [
            tk.StringVar(window, value=spec[k])
            for k in ("format", "maxEdge", "relativeDir")
        ]
        widgets = [
            ttk.Combobox(
                grid,
                textvariable=row[0],
                values=["png", "jpg", "webp"],
                state="readonly",
                width=8,
            ),
            ttk.Entry(grid, textvariable=row[1], width=14),
            ttk.Entry(grid, textvariable=row[2], width=22),
        ]

        def remove():
            for widget in widgets:
                widget.destroy()
            rows.remove((row, widgets))

        widgets.append(button(grid, tr("Remove", "Kaldır"), remove))
        position = grid.grid_size()[1]
        for i, widget in enumerate(widgets):
            widget.grid(row=position, column=i, sticky="ew", padx=3, pady=2)
        rows.append((row, widgets))

    def select(*_):
        for _, widgets in rows:
            for widget in widgets:
                widget.destroy()
        rows.clear()
        pkg = stored.get(selected.get())
        name.set(pkg["name"] if pkg else "")
        for output in (
            pkg["outputs"]
            if pkg
            else [{"format": "webp", "maxEdge": 1600, "relativeDir": "web"}]
        ):
            add(output)
        delete_btn.state(["!disabled" if pkg else "disabled"])

    def save():
        try:
            outputs = [
                {
                    "format": r[0].get(),
                    "maxEdge": int(r[1].get()),
                    "relativeDir": r[2].get(),
                }
                for r, _ in rows
            ]
        except ValueError:
            messagebox.showerror(
                "Pivoki",
                tr("Enter a whole number of pixels.", "Piksel için tam sayı girin."),
                parent=window,
            )
            return
        pkg = {**stored.get(selected.get(), {}), "name": name.get(), "outputs": outputs}
        result = dispatch({"action": "savePackage", "package": pkg})
        if result["status"] == "success":
            workspace.load_commands(result["package"]["packageId"])
            window.destroy()
        else:
            messagebox.showerror("Pivoki", result["error"], parent=window)

    def delete():
        pkg = stored.get(selected.get())
        if pkg and messagebox.askyesno(
            "Pivoki",
            tr("Delete package? ", "Paket silinsin mi? ") + pkg["name"],
            parent=window,
        ):
            result = dispatch(
                {
                    "action": "deletePackage",
                    "packageId": pkg["packageId"],
                    "revision": pkg["revision"],
                }
            )
            if result["status"] == "success":
                workspace.load_commands()
                window.destroy()
            else:
                messagebox.showerror("Pivoki", result["error"], parent=window)

    bar = ttk.Frame(body, padding=(0, 8))
    bar.grid(row=3, column=0, columnspan=2, sticky="ew")
    button(bar, tr("Add output", "Çıktı ekle"), add).pack(side="left")
    delete_btn = button(bar, tr("Delete package", "Paketi sil"), delete)
    delete_btn.pack(side="left", padx=4)
    button(bar, tr("Save revision", "Revizyonu kaydet"), save).pack(side="right")
    button(bar, tr("Cancel", "İptal"), window.destroy).pack(side="right", padx=4)
    chooser.bind("<<ComboboxSelected>>", select)
    window.bind("<Escape>", lambda e: window.destroy())
    selected.set(workspace.command.get() if workspace.command.get() in stored else new)
    select()
    entry.focus_set()
