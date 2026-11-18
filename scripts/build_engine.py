"""Build the same self-contained helper directory on macOS, Windows or Linux."""
import argparse
import importlib.metadata as md
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def gather_notices(directory):
    for name in ("pillow", "pillow-heif", "qrcode", "zxing-cpp", "pypdf", "reportlab",
                 "rawpy", "numpy", "charset-normalizer", "pivoki-engine", "pivoki-studio", "colorama"):
        try:
            package = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        for f in package.files or ():
            if not any(n in f.name.lower() for n in ("license","copying","notice","copyright")):
                continue
            src = Path(package.locate_file(f))
            if src.is_file() and ".." not in f.parts:
                target = directory / name / f
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src, target)
    shutil.copyfile(ROOT / "LICENSE", directory / "Pivoki-LICENSE.txt")
    python_root = Path(sysconfig.get_path("stdlib"))
    for file in [python_root / "LICENSE.txt", python_root / "LICENSE", Path(sys.base_prefix)/"LICENSE.txt"]:
        if file.is_file():
            shutil.copyfile(file,directory/"Python-LICENSE.txt")
            break


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",action="store_true",help="Include installed rawpy and LibRaw support")
    args=parser.parse_args()
    import tkinter
    import pivoki_engine, pivoki_studio, zxingcpp
    import PIL, qrcode, pypdf, reportlab, pillow_heif
    if args.raw:
        import rawpy
    work=ROOT / "build" / "freeze"
    work.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        notices=Path(tmp,"licenses")
        notices.mkdir()
        gather_notices(notices)
        options = [
            sys.executable,"-m","PyInstaller","--clean","--noconfirm","--onedir","--name","pivoki-engine",
            "--distpath",str(ROOT/"dist"/"engine"),"--workpath",str(work),"--specpath",tmp,
            "--add-data",f"{notices}:licenses","--collect-all","pillow_heif",
            "--collect-data","reportlab","--hidden-import","PIL._tkinter_finder",
            "--collect-submodules","pivoki_studio","--exclude-module","pytest",
            "--exclude-module","matplotlib","--exclude-module","IPython",
        ]
        if args.raw:
            options += ["--collect-all","rawpy"]
        else:
            options += ["--exclude-module","rawpy"]
        subprocess.run(options+[str(ROOT/"scripts"/"packaging"/"engine_entry.py")],cwd=ROOT,check=True)


if __name__=="__main__":
    main()
