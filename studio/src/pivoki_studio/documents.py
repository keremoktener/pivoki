"""PDF exports retain the source. Signed inputs require an explicit working-copy choice."""
from io import BytesIO
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .files import tool
from .images import watermark_overlay


def signed(reader):
    # Visit reachable objects without decoding any content streams. Detached
    # signature dictionaries and certification timestamps need not be form fields.
    stack = [reader.root_object]
    visited = set()
    while stack:
        node = stack.pop()
        if isinstance(node, IndirectObject):
            key = (node.idnum,node.generation)
            if key in visited:
                continue
            visited.add(key)
            if len(visited)>250_000:
                raise ValueError("PDF imza durumu güvenle belirlenemedi.")
            node = node.get_object()
        if isinstance(node, DictionaryObject):
            if (node.get("/Type") in {"/Sig","/DocTimeStamp"} or node.get("/FT")=="/Sig"
                    or "/ByteRange" in node or "/Perms" in node):
                return True
            stack.extend(node.values())
        elif isinstance(node, ArrayObject):
            stack.extend(node)
    return False


def inspect_pdf(path):
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("Bu işlem için erişilebilir, şifrelenmemiş bir PDF seçin.")
    return reader, signed(reader)


def selected_pages(spec, count):
    if not spec.strip():
        return list(range(count))
    chosen = set()
    for item in spec.split(","):
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", item.strip())
        if not match:
            raise ValueError("Sayfa aralığı örneği: 1,3-5")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= count:
            raise ValueError(f"Sayfalar 1–{count} içinde olmalı.")
        chosen.update(range(first-1,last))
    return sorted(chosen)


def working_copy(source, target, *, watermark=None, pages="", allow_signed=False):
    reader, has_signature = inspect_pdf(source)
    if has_signature and not allow_signed:
        raise ValueError("İmzasız çalışma kopyası için açık onay gerekir.")
    selection = selected_pages(pages, len(reader.pages))
    writer = PdfWriter()
    if has_signature or watermark is None:
        # Copy the visible page content into a fresh document, stripping interactive
        # fields (including signatures) and any signature references in the catalog.
        for page in reader.pages:
            writer.add_page(page, excluded_keys=["/Annots", "/PieceInfo"])
    else:
        writer.clone_document_from_reader(reader)
    if watermark:
        for index in selection:
            page = writer.pages[index]
            page.transfer_rotation_to_content()
            box = page.cropbox
            w,h = float(box.width), float(box.height)
            scale = min(2, 1800 / max(w,h))
            stamp = watermark_overlay((max(1,round(w*scale)),max(1,round(h*scale))), **watermark)
            packet = BytesIO()
            overlay = Canvas(packet, pagesize=(w,h))
            overlay.drawImage(ImageReader(stamp),0,0,w,h,mask="auto")
            overlay.showPage()
            overlay.save()
            packet.seek(0)
            page.merge_transformed_page(PdfReader(packet).pages[0],
                                        Transformation().translate(float(box.left),float(box.bottom)))
    writer.write(target)
    actual = PdfReader(target)
    if len(actual.pages) != len(reader.pages) or (has_signature and signed(actual)):
        raise ValueError("PDF çıktı doğrulaması başarısız.")


def original_zip(paths, target):
    used = set()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in map(Path, paths):
            name = path.name
            n = 2
            while name.casefold() in used:
                name = f"{path.stem} ({n}){path.suffix}"
                n += 1
            used.add(name.casefold())
            archive.write(path,name)
    with zipfile.ZipFile(target) as check:
        if check.testzip() is not None:
            raise ValueError("ZIP doğrulanamadı.")


def pdf_svg(source, page, target):
    reader, signature = inspect_pdf(source)
    if signature:
        raise ValueError("Önce imzasız çalışma kopyası oluşturun.")
    if not 1 <= page <= len(reader.pages):
        raise ValueError("Geçersiz PDF sayfası.")
    subprocess.run([tool("pdftocairo"), "-f",str(page),"-l",str(page),"-svg",str(source),str(target)],
                   check=True, capture_output=True)
    if ET.parse(target).getroot().tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("SVG çıktısı doğrulanamadı.")


def pdf_archive(source, target):
    reader, signature = inspect_pdf(source)
    if signature:
        raise ValueError("Önce imzasız çalışma kopyası oluşturun.")
    gs, validator = tool("gswin64c" if __import__("os").name == "nt" else "gs"), tool("verapdf")
    from PIL import ImageCms
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp/"profile.icc").write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        ps = tmp / "output-intent.ps"
        ps.write_text("""
[/_objdef {icc_PDFA} /type /stream /OBJ pdfmark
[{icc_PDFA} << /N 3 >> /PUT pdfmark
[{icc_PDFA} (profile.icc) (r) file /PUT pdfmark
[/_objdef {OutputIntent_PDFA} /type /dict /OBJ pdfmark
[{OutputIntent_PDFA} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {icc_PDFA}
 /OutputConditionIdentifier (sRGB) >> /PUT pdfmark
[{Catalog} << /OutputIntents [ {OutputIntent_PDFA} ] >> /PUT pdfmark
""")
        subprocess.run([gs,"-dPDFA=2","-dBATCH","-dNOPAUSE","-dPDFACompatibilityPolicy=1",
                        "-sDEVICE=pdfwrite","-sColorConversionStrategy=RGB",
                        "--permit-file-read=profile.icc",f"-sOutputFile={target}",str(ps),str(source)],
                       cwd=tmp, capture_output=True, check=True)
        report = subprocess.run([validator,"--format","xml","--flavour","2b",str(target)],
                                capture_output=True, check=True)
        checks = [node for node in ET.fromstring(report.stdout).iter() if node.tag.split("}")[-1]=="validationReport"]
        if len(checks) != 1 or checks[0].get("isCompliant") != "true":
            raise ValueError("Bağımsız PDF/A-2b doğrulaması geçmedi.")
