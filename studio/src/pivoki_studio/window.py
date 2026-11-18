"""Desktop editors for individual images, documents, media and folder rules."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from PIL import Image, ImageGrab, ImageOps, ImageTk
from . import documents, images, media, qr, rules
from .files import new_file, tool
from .rules_panel import RulePanel

PHOTO = ("Açıklama şeridi","Filigran","Fonu kaldır","Çokgen","ICO","EXIF zamanı","Kamera RAW")
PDF = ("PDF filigranı","İmzasız çalışma kopyası","Özgünleri ZIP yap","PDF sayfalarını SVG yap","PDF/A-2b")
VIDEO = ("Mac ile uyumlu MP4","Hedef boyut","Video maskesi")
QR = ("QR oluştur","Dosyadan QR oku","Ekrandan QR oku")


def show_path(path):
    if os.name=="nt":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open" if sys.platform=="darwin" else "xdg-open",str(path)])


class Studio(tk.Tk):
    def __init__(self, paths=()):
        super().__init__()
        self.title("Pivoki Studio")
        self.geometry("980x680")
        self.minsize(680,500)
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix="pivoki-export")
        self.temp=tempfile.TemporaryDirectory(prefix="pivoki-preview-")
        self.paths=list(map(Path,paths))
        self.points=[]
        self.undos=[]
        self.closed_shape=False
        self.busy=False
        self.protocol("WM_DELETE_WINDOW",self.close)
        self.configure(bg="#1e3026")
        self.style=ttk.Style(self)
        self.style.configure("Title.TLabel",font=("TkDefaultFont",19,"bold"))
        head=tk.Frame(self,bg="#1e3026",padx=18,pady=10)
        head.pack(fill="x")
        tk.Label(head,text="Pivoki",font=("TkDefaultFont",22,"bold"),bg="#1e3026",fg="#f2f5ef").pack(side="left")
        tk.Label(head,text="Studio",font=("TkDefaultFont",16),bg="#1e3026",fg="#d7ed99",padx=10).pack(side="left")
        self.tabs=ttk.Notebook(self)
        self.tabs.pack(fill="both",expand=True,padx=8,pady=8)
        editor=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(editor,text="Düzenleyici")
        self.rules_view=RulePanel(self.tabs)
        self.tabs.add(self.rules_view,text="Klasör kuralları")
        self.tabs.bind("<<NotebookTabChanged>>",self.tab_changed)
        top=ttk.Frame(editor)
        top.pack(fill="x",pady=(0,8))
        ttk.Button(top,text="Dosya seç…",command=self.choose).pack(side="left")
        self.source=tk.StringVar()
        ttk.Label(top,textvariable=self.source).pack(side="left",padx=8)
        self.update_source()
        body=ttk.Panedwindow(editor,orient="horizontal")
        body.pack(fill="both",expand=True)
        control=ttk.Frame(body,padding=(0,0,8,0))
        body.add(control,weight=1)
        self.op=tk.StringVar(value=PHOTO[0] if paths else QR[0])
        ttk.Label(control,text="İşlem",style="Title.TLabel").pack(anchor="w")
        self.chooser=ttk.Combobox(control,textvariable=self.op,state="readonly",width=27,values=PHOTO+PDF+VIDEO+QR)
        self.chooser.pack(fill="x",pady=(3,10))
        self.chooser.bind("<<ComboboxSelected>>",lambda _:self.settings())
        self.options=ttk.Frame(control)
        self.options.pack(fill="both",expand=True)
        self.canvas=tk.Canvas(body,bg="#e9eee5",highlightthickness=1,highlightbackground="#a8b7a9",
                              width=520,height=360,takefocus=1)
        body.add(self.canvas,weight=3)
        self.canvas.bind("<Configure>",lambda _:self.render_canvas())
        self.canvas.bind("<Button-1>",self.click_point)
        self.canvas.bind("<Return>",lambda _:self.close_polygon())
        self.canvas.bind("<Escape>",lambda _:self.reset_points())
        self.status=tk.StringVar(value="Hazır")
        footer=ttk.Frame(editor)
        footer.pack(fill="x",pady=(10,0))
        ttk.Label(footer,textvariable=self.status,wraplength=400).pack(side="left",fill="x",expand=True)
        self.preview_btn=ttk.Button(footer,text="Önizle",command=self.preview)
        self.preview_btn.pack(side="left")
        self.save_btn=ttk.Button(footer,text="Kopyayı kaydet…",command=self.save)
        self.save_btn.pack(side="left",padx=(6,0))
        self.picture=None
        self.timer=None
        self.fields={}
        self.last_dir=None
        self.settings()
        self.after(1500,self.service_rules)

    def close(self):
        if self.busy:
            self.status.set("İşlem sürüyor. Pencereyi işlem bitince kapatabilirsiniz.")
            return
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.temp.cleanup()
        self.destroy()

    def service_rules(self):
        if not self.busy:
            self.pool.submit(rules.tick)
        self.after(8000,self.service_rules)

    def tab_changed(self,_event):
        if self.tabs.index("current")==1:
            self.rules_view.refresh()

    def update_source(self):
        self.source.set(", ".join(p.name for p in self.paths[:2])+(f" +{len(self.paths)-2}" if len(self.paths)>2 else "") if self.paths else "Dosya seçilmedi")

    def choose(self):
        if self.busy:
            return
        paths=filedialog.askopenfilenames(parent=self)
        if paths:
            self.paths=list(map(Path,paths))
            self.update_source()
            self.reset_points()
            ext=self.paths[0].suffix.lower()
            if ext==".pdf":
                self.op.set(PDF[0])
            elif ext in {".mov",".mp4",".mkv",".webm",".avi"}:
                self.op.set(VIDEO[0])
            elif ext in {".dng",".cr2",".cr3",".nef",".arw",".orf",".raf",".rw2"}:
                self.op.set(PHOTO[6])
            elif self.op.get() not in PHOTO and self.op.get()!=QR[1]:
                self.op.set(PHOTO[0])
            self.settings()

    def field(self,key,label,default="",choices=None,multiline=False):
        ttk.Label(self.options,text=label).pack(anchor="w",pady=(5,1))
        if multiline:
            widget=tk.Text(self.options,height=3,width=25,wrap="word",undo=True)
            widget.insert("1.0",default)
            widget.bind("<KeyRelease>",lambda _:self.schedule_preview())
            self.fields[key]=lambda:widget.get("1.0","end-1c")
        else:
            var=tk.StringVar(value=default)
            widget=(ttk.Combobox(self.options,textvariable=var,values=choices,state="readonly",width=22)
                    if choices else ttk.Entry(self.options,textvariable=var,width=20))
            self.fields[key]=var.get
            var.trace_add("write",lambda *_:self.schedule_preview())
        widget.pack(fill="x")
        return widget

    def settings(self):
        for child in self.options.winfo_children():
            child.destroy()
        self.fields={}
        self.picture=None
        self.render_canvas()
        op=self.op.get()
        self.preview_btn.configure(text="Önizle")
        self.save_btn.configure(text="Kopyayı kaydet…",state="normal")
        if op in (PHOTO[0], QR[0]):
            self.field("text","Metin","" if op==PHOTO[0] else "Pivoki",multiline=True)
        if op==QR[0]:
            self.field("size","PNG boyutu (px)","512")
            self.field("level","Hata düzeltme","M",("L","M","Q","H"))
        elif op in (PHOTO[1],PDF[0]):
            from pivoki_engine.store import data_home
            self.profile=data_home()/"watermark-profile.json"
            try:
                defaults=json.loads(self.profile.read_text())
            except (OSError,ValueError):
                defaults={}
            self.field("text","Filigran metni",defaults.get("text","Pivoki"))
            logo=self.field("logo","Logo dosyası (isteğe bağlı)",defaults.get("logo",""))
            def pick_logo():
                path=filedialog.askopenfilename(parent=self)
                if path:
                    logo.delete(0,"end")
                    logo.insert(0,path)
            ttk.Button(self.options,text="Logo seç…",command=pick_logo).pack(anchor="w")
            self.field("corner","Konum (üst T / alt B · sol L / sağ R)",defaults.get("corner","BR"),("TL","TR","BL","BR"))
            self.field("margin","Kenar boşluğu (%)",defaults.get("margin","4"))
            self.field("opacity","Opaklık (%)",defaults.get("opacity","70"))
            ttk.Button(self.options,text="Profili sakla",command=self.save_profile).pack(anchor="w",pady=4)
        elif op==PHOTO[2]:
            self.field("tol","Tolerans (0–255)","18")
            self.field("feather","Kenar yumuşatma (px)","1")
            ttk.Button(self.options,text="Özgünü göster",command=lambda:self.preview(original=True)).pack(anchor="w")
        elif op in (PHOTO[3],VIDEO[2]):
            self.field("x","Köşe X · genişlik oranı","0.25")
            self.field("y","Köşe Y · yükseklik oranı","0.25")
            self.point_index=self.field("point","Seçili köşe","1")
            for label,act in (("Nokta ekle","add"),("Noktayı taşı","move"),("Noktayı kaldır","delete"),("Geri al","undo")):
                ttk.Button(self.options,text=label,command=lambda a=act:self.edit_point(a)).pack(side="top",anchor="w")
            ttk.Button(self.options,text="Şekli kapat",command=self.close_polygon).pack(anchor="w")
        elif op==PHOTO[5]:
            self.field("offset","EXIF saat dilimi eksikse (±SS:DD)","")
        if op in (PDF[0],PDF[3]):
            self.field("pages","Sayfalar (tümü veya 1,3-5)","")
        if op in (VIDEO[1],VIDEO[2]):
            if op==VIDEO[1]:
                self.field("mb","Hedef dosya boyutu (MB)","10")
            self.field("start","Başlangıç / örnek (saniye)","0")
            if op==VIDEO[2]:
                self.field("end","Bitiş (saniye)","1")
                self.field("angle","Maske açısı (derece)","0")
        if op in (QR[1],QR[2]):
            self.save_btn.configure(text="QR oku")
        self.status.set("Hazır")
        self.schedule_preview()

    def save_profile(self):
        try:
            fields=self.values()
            self.profile.parent.mkdir(parents=True,exist_ok=True)
            fields.pop("pages",None)
            with tempfile.NamedTemporaryFile("w",dir=self.profile.parent,delete=False,encoding="utf-8") as f:
                json.dump(fields,f)
            os.replace(f.name,self.profile)
            self.status.set("Filigran profili kaydedildi.")
        except Exception as exc:
            self.status.set(str(exc))

    def values(self):
        return {key:get() for key,get in self.fields.items()}

    def schedule_preview(self):
        if self.timer:
            self.after_cancel(self.timer)
        if self.op.get() in PHOTO[:5]+(QR[0],) and (self.paths or self.op.get()==QR[0]):
            self.timer=self.after(420,self.preview)

    def reset_points(self):
        self.points=[]
        self.undos=[]
        self.closed_shape=False

    def click_point(self,event):
        self.canvas.focus_set()
        if self.op.get() not in (PHOTO[3],VIDEO[2]) or not self.picture or not hasattr(self,"bounds"):
            return
        x,y,w,h=self.bounds
        p=((event.x-x)/w,(event.y-y)/h)
        if all(0<=v<=1 for v in p):
            self.undos.append((self.points.copy(),self.closed_shape))
            self.points.append(p)
            self.closed_shape=False
            self.render_canvas()

    def edit_point(self,action):
        try:
            v=self.values()
            if action=="undo":
                if self.undos:
                    self.points,self.closed_shape=self.undos.pop()
            else:
                p=(float(v["x"]),float(v["y"]))
                if any(not 0<=t<=1 for t in p):
                    raise ValueError("Koordinatlar 0–1 aralığında olmalı.")
                idx=int(v["point"])-1
                if action!="add" and not 0<=idx<len(self.points):
                    raise ValueError("Geçerli bir köşe numarası seçin.")
                self.undos.append((self.points.copy(),self.closed_shape))
                if action=="move":
                    self.points[idx]=p
                elif action=="delete":
                    self.points.pop(idx)
                else:
                    self.points.append(p)
                self.closed_shape=self.closed_shape and len(set(self.points))>=3
            self.preview()
        except Exception as exc:
            self.status.set(str(exc))

    def close_polygon(self):
        if len(set(self.points))>=3:
            self.undos.append((self.points.copy(),self.closed_shape))
            self.closed_shape=True
            self.preview()
        else:
            self.status.set("Şekli kapatmak için en az üç farklı köşe ekleyin.")

    def work(self,task,done):
        if self.busy:
            return
        self.busy=True
        self.status.set("İşleniyor…")
        self.save_btn.state(["disabled"])
        self.preview_btn.state(["disabled"])
        self.chooser.state(["disabled"])
        future=self.pool.submit(task)
        def poll():
            if not future.done():
                self.after(60,poll)
                return
            self.busy=False
            self.save_btn.state(["!disabled"])
            self.preview_btn.state(["!disabled"])
            self.chooser.state(["!disabled"])
            try:
                done(future.result())
            except Exception as exc:
                self.status.set(str(exc))
        self.after(20,poll)

    def request(self):
        op=self.op.get()
        if not self.paths and op not in (QR[0],QR[2]):
            raise ValueError("Önce bir kaynak dosya seçin.")
        return op,self.values(),list(self.paths),list(self.points),self.closed_shape

    def preview(self,original=False):
        try:
            req=self.request()
        except ValueError as exc:
            self.status.set(str(exc))
            return
        op,v,paths,points,closed=req
        if op in (QR[1],QR[2]):
            self.status.set("Okumayı başlatmak için QR oku düğmesini kullanın.")
            return
        def prepare():
            if op in PHOTO[:5]+(QR[0],PHOTO[6]):
                pic=images.source_image(paths[0]) if original else self.image(req,preview=True)
                return pic
            if op==PHOTO[5]:
                filesystem=datetime.fromtimestamp(paths[0].stat().st_mtime).astimezone().isoformat()
                return f"Dosya: {filesystem}  ·  EXIF: {images.exif_time(paths[0],v['offset']).isoformat()}"
            if op in PDF:
                if op==PDF[2]:
                    return "\n".join(p.name for p in paths)
                reader,signature=documents.inspect_pdf(paths[0])
                return f"{len(reader.pages)} sayfa · " + ("İmza alanı var" if signature else "İmza alanı bulunamadı")
            temp=Path(self.temp.name)
            if op==VIDEO[1]:
                compare=temp/"comparison.mp4"
                media.comparison(paths[0],compare,float(v["start"]),float(v["mb"]))
                return compare
            if op==VIDEO[2]:
                frame=temp/"frame.png"
                media.invoke([tool("ffmpeg"),"-v","error","-y","-ss",v["start"],"-i",str(paths[0]),"-frames:v","1",str(frame)])
                return images.source_image(frame)
            video,a,duration=media.inspect(paths[0])
            return f"{duration:.1f} sn · {video['width']} × {video['height']} · {video['codec_name']} · {a['codec_name'] if a else 'Sessiz'}"
        def ready(result):
            if isinstance(result,Image.Image):
                self.picture=result
                self.render_canvas()
                self.status.set(f"{result.width} × {result.height} px")
            elif isinstance(result,Path):
                show_path(result)
                self.status.set("Solda özgün sahne, sağda hedef boyutun kodlama örneği.")
            else:
                self.status.set(result)
        self.work(prepare,ready)

    def render_canvas(self):
        self.canvas.delete("all")
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        if not getattr(self,"picture",None):
            self.canvas.create_text(w/2,h/2,text="Önizleme",fill="#516755",font=("TkDefaultFont",16))
            return
        pic=ImageOps.contain(self.picture,(max(1,w-16),max(1,h-16)),Image.Resampling.LANCZOS)
        self.tkpic=ImageTk.PhotoImage(pic)
        x,y=(w-pic.width)/2,(h-pic.height)/2
        self.canvas.create_image(x,y,image=self.tkpic,anchor="nw")
        self.bounds=(x,y,pic.width,pic.height)
        if self.op.get() in (PHOTO[3],VIDEO[2]):
            points=[(x+a*pic.width,y+b*pic.height) for a,b in self.points]
            if len(points)>1:
                outline=points+points[:1] if self.closed_shape else points
                self.canvas.create_line(*[n for p in outline for n in p],fill="#356343",width=2)
            for i,(a,b) in enumerate(points,1):
                self.canvas.create_oval(a-4,b-4,a+4,b+4,fill="#d7ed99",outline="#213e31")
                self.canvas.create_text(a+7,b-7,text=str(i),fill="#213e31",anchor="w")

    @staticmethod
    def image(req,preview=False):
        op,v,paths,points,closed=req
        if op==QR[0]:
            return qr.make(v["text"],int(v["size"]),v["level"])
        if op==PHOTO[6]:
            try:
                import rawpy
            except ImportError:
                raise ValueError("Kamera RAW desteği için pivoki-studio[raw] kurun.") from None
            with rawpy.imread(str(paths[0])) as raw:
                return Image.fromarray(raw.postprocess(use_camera_wb=True,output_color=rawpy.ColorSpace.sRGB)).convert("RGBA")
        img=images.source_image(paths[0])
        if op==PHOTO[0]:
            return images.caption(img,v["text"])
        if op==PHOTO[1]:
            return Image.alpha_composite(img,images.watermark_overlay(img.size,**Studio.mark_args(v)))
        if op==PHOTO[2]:
            return images.remove_background(img,int(v["tol"]),float(v["feather"]))
        if op==PHOTO[3]:
            if preview and not closed:
                return img
            if not closed:
                raise ValueError("Önce şekli kapatın.")
            return images.polygon(img,points)
        return img

    @staticmethod
    def mark_args(v):
        return dict(text=v["text"],logo=v["logo"],corner=v["corner"],margin=float(v["margin"]),opacity=float(v["opacity"]))

    def save(self):
        try:
            req=self.request()
            op,v,paths,points,closed=req
            if op in (QR[1],QR[2]):
                return self.read_codes(op)
            signed_ok=False
            if op in PDF and op!=PDF[2]:
                reader,signed=documents.inspect_pdf(paths[0])
                if signed:
                    if op not in PDF[:2]:
                        raise ValueError("Önce imzasız çalışma kopyası oluşturun veya özgünleri ZIP yapın.")
                    signed_ok=messagebox.askyesno("İmzasız çalışma kopyası",
                        "İmza ve etkileşimli form alanları çalışma kopyasından kaldırılacak. Devam edilsin mi?",parent=self)
                    if not signed_ok:
                        return
            if op==PDF[3]:
                pages=documents.selected_pages(v["pages"],len(reader.pages))
                location=filedialog.askdirectory(parent=self)
                if not location:
                    return
                from .svg_export import export_pages
                self.work(lambda:export_pages(paths[0],Path(location),pages),self.success)
                return
            ext=".png"
            if op==PHOTO[4]: ext=".ico"
            if op==PHOTO[5]: ext=paths[0].suffix
            if op in PDF: ext=".zip" if op==PDF[2] else ".pdf"
            if op in VIDEO: ext=".mp4"
            initial=(paths[0].stem if paths else "QR")+" - Pivoki"+ext
            name=filedialog.asksaveasfilename(parent=self,initialfile=initial,defaultextension=ext,filetypes=[(ext.upper(),f"*{ext}")])
            if not name:
                return
            target=Path(name)
            if target.suffix.lower()!=ext.lower():
                raise ValueError(f"Çıktı uzantısı {ext} olmalı.")
            def export():
                with new_file(target) as work:
                    if op==PHOTO[5]:
                        stamp=images.exif_time(paths[0],v["offset"]).timestamp()
                        shutil.copyfile(paths[0],work)
                        os.utime(work,(stamp,stamp))
                        if abs(work.stat().st_mtime-stamp)>2:
                            raise ValueError("Dosya tarihi hedefte doğrulanamadı.")
                    elif op in PHOTO or op==QR[0]:
                        pic=self.image(req)
                        if op==PHOTO[4]:
                            images.write_ico(pic,work)
                        else:
                            pic.save(work,format="PNG")
                            with Image.open(work) as check:
                                check.verify()
                    elif op==PDF[2]:
                        documents.original_zip(paths,work)
                    elif op in PDF[:2]:
                        documents.working_copy(paths[0],work,watermark=self.mark_args(v) if op==PDF[0] else None,
                                               pages=v.get("pages",""),allow_signed=signed_ok)
                    elif op==PDF[4]:
                        documents.pdf_archive(paths[0],work)
                    elif op in VIDEO:
                        if op==VIDEO[2] and not closed:
                            raise ValueError("Önce maske şeklini kapatın.")
                        media.encode(paths[0],work,mode=("quicktime","target","mask")[VIDEO.index(op)],
                                     mb=float(v.get("mb",10)),start=float(v.get("start",0)),end=float(v.get("end",0)),
                                     points=points,angle=float(v.get("angle",0)))
                return target
            self.work(export,self.success)
        except Exception as exc:
            self.status.set(str(exc))

    def success(self,target):
        from pivoki_engine.service import record_export
        saved = sorted(target.glob("*.svg")) if target.is_dir() else [target]
        try:
            record_export(self.op.get(), saved)
            self.status.set(f"Kaydedildi · {target}")
        except Exception as exc:
            self.status.set(f"Kaydedildi · {target} · Geçmişe yazılamadı: {exc}")
        if messagebox.askyesno("Çıktı hazır",f"{target}\n\nKlasörde gösterilsin mi?",parent=self):
            show_path(target if target.is_dir() else target.parent)

    def read_codes(self,op):
        def display(values):
            self.deiconify()
            if not values:
                self.status.set("Seçili görüntüde QR kodu bulunamadı.")
                return
            dlg=tk.Toplevel(self)
            dlg.title("Okunan QR kodları")
            for value in dict.fromkeys(values):
                ttk.Label(dlg,text=value,wraplength=420,padding=8).pack(anchor="w")
                def copy(v=value):
                    self.clipboard_clear()
                    self.clipboard_append(v)
                ttk.Button(dlg,text="Kopyala",command=copy).pack(anchor="w")
                if value.lower().startswith(("https://","http://")):
                    ttk.Button(dlg,text="Bağlantıyı aç",command=lambda v=value:webbrowser.open(v)).pack(anchor="w")
            self.status.set(f"{len(values)} QR kodu okundu.")
        if op==QR[1]:
            self.work(lambda:qr.read(images.source_image(self.paths[0])),display)
        else:
            self.withdraw()
            def grab():
                try:
                    result=qr.read(ImageGrab.grab(all_screens=True))
                    display(result)
                except Exception as exc:
                    self.deiconify()
                    self.status.set(f"Ekran yakalanamadı · {exc}")
            self.after(350,grab)
