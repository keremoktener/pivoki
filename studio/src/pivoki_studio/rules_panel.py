import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from . import rules


class RulePanel(ttk.Frame):
    def __init__(self, parent, lang):
        super().__init__(parent, padding=14)
        self.lang=lang
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(self, columns=("root","state","message"),show="headings",height=5)
        for name,label,width in (("root","İzlenen klasör",230),("state","Durum",65),("message","Son işlem",245)):
            self.table.heading(name,text=label)
            self.table.column(name,width=width)
        self.table.grid(row=0,column=0,columnspan=3,sticky="nsew")
        actions = ttk.Frame(self)
        actions.grid(row=1,column=0,columnspan=3,sticky="w",pady=5)
        for label, action in (("Duraklat / sürdür","pause"),("Hataları yeniden dene","retry"),("Kuralı kaldır","remove")):
            ttk.Button(actions,text=label,command=lambda a=action:self.change(a)).pack(side="left")
        self.root_path, self.output = tk.StringVar(),tk.StringVar()
        for row,label,var in [(2,"Gelen dosyalar",self.root_path),(3,"Çıktı hedefi",self.output)]:
            ttk.Label(self,text=label).grid(row=row,column=0,sticky="w")
            ttk.Entry(self,textvariable=var).grid(row=row,column=1,sticky="ew")
            ttk.Button(self,text="Klasör seç",command=lambda v=var:self.browse(v)).grid(row=row,column=2)
        self.extensions=tk.StringVar(value=rules.DEFAULT_FILTER)
        ttk.Label(self,text="Uzantılar").grid(row=4,column=0,sticky="w")
        ttk.Entry(self,textvariable=self.extensions).grid(row=4,column=1,columnspan=2,sticky="ew")
        self.packages=ttk.Combobox(self,state="readonly")
        ttk.Label(self,text="Paket revizyonu").grid(row=5,column=0,sticky="w")
        self.packages.grid(row=5,column=1,columnspan=2,sticky="ew")
        self.policy=tk.StringVar(value="keep-both")
        ttk.Label(self,text="Çakışma").grid(row=6,column=0,sticky="w")
        ttk.Combobox(self,state="readonly",values=["keep-both","skip"],textvariable=self.policy).grid(row=6,column=1,sticky="w")
        self.existing=tk.BooleanVar()
        ttk.Checkbutton(self,text="Mevcut dosyaları da işle",variable=self.existing).grid(row=7,column=1,sticky="w")
        self.feedback=tk.StringVar()
        ttk.Label(self,textvariable=self.feedback,wraplength=640).grid(row=8,column=0,columnspan=3,sticky="w")
        ttk.Button(self,text="Kuralı dene ve etkinleştir…",command=self.preview).grid(row=9,column=1,sticky="e",pady=8)
        self.refresh()

    def browse(self,var):
        path=filedialog.askdirectory(parent=self)
        if path:
            var.set(path)

    def refresh(self):
        from pivoki_engine.service import dispatch
        self.defs=dispatch({"action":"packages"}).get("packages",[])
        self.packages.configure(values=[f"{p['name']} · r{p['revision']}" for p in self.defs])
        if self.defs and self.packages.get() not in self.packages["values"]:
            self.packages.current(0)
        selected=self.table.selection()
        self.table.delete(*self.table.get_children())
        for row in rules.definitions():
            self.table.insert("","end",iid=row["id"],values=(row["root"],self.lang("Etkin" if row["enabled"] else "Duraklatıldı"),row["message"]))
        if selected and self.table.exists(selected[0]):
            self.table.selection_set(selected)

    def change(self,action):
        selected=self.table.selection()
        if selected:
            rules.change(selected[0],action)
            self.refresh()

    def preview(self):
        from pivoki_engine.service import dispatch
        try:
            idx=self.packages.current()
            if idx<0:
                raise ValueError("Bir paket seçin.")
            pkg=self.defs[idx]
            root,out,files=rules.validated(self.root_path.get(),self.output.get(),self.extensions.get())
            total=0
            if files:
                result=dispatch(dict(action="plan",inputs=list(files),outputRoot=str(out),
                                     packageId=pkg["packageId"],revision=pkg["revision"],conflictPolicy=self.policy.get()))
                if result["status"]!="planned":
                    raise ValueError(result.get("error","Plan hazırlanamadı."))
                total=sum(r["status"]=="planned" for r in result["rows"])
            details=f"{len(files)} dosya · örnek planda {total} çıktı\n{root}\n→ {out}\nPaket: {pkg['name']} · r{pkg['revision']}"
            details += "\nMevcut dosyalar da işlenecek." if self.existing.get() else "\nYalnızca yeni veya değişen dosyalar işlenecek."
            if messagebox.askyesno(self.lang("Kuralı etkinleştir?"),details,parent=self):
                rules.enable(root,out,self.extensions.get(),pkg["packageId"],pkg["revision"],self.policy.get(),self.existing.get())
                self.feedback.set("Kural etkin. Pivoki açıkken klasör izlenir.")
                self.refresh()
        except Exception as exc:
            self.feedback.set(str(exc))
