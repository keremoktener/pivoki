"""Read UYAP's zipped content.xml and export new, unsigned working copies."""
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import iterparse

from .files import new_file

MAX_XML = 8 * 1024 * 1024
MAX_UNITS = 1_000_000
MAX_NODES = 50_000
DECIMAL = "NUMBER_TYPE_NUMBER_DOT"
FORMATS = {
    DECIMAL: ("decimal", "."),
    "NUMBER_TYPE_NUMBER_PARENTHESIS": ("decimal", ")"),
    "NUMBER_TYPE_SMALL_LETTER_DOT": ("lowerLetter", "."),
    "NUMBER_TYPE_CAPITAL_LETTER_DOT": ("upperLetter", "."),
    "NUMBER_TYPE_SMALL_ROMAN_DOT": ("lowerRoman", "."),
    "NUMBER_TYPE_CAPITAL_ROMAN_DOT": ("upperRoman", "."),
}


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass
class Paragraph:
    runs: list[Run]
    align: int
    level: int = 0
    list_id: str | None = None
    number_format: str = "decimal"
    suffix: str = "."
    marker: str = ""

    def text(self):
        return (self.marker + " " if self.marker else "") + "".join(r.text for r in self.runs)


@dataclass
class Table:
    rows: list[list[list[Paragraph]]]


@dataclass
class Document:
    blocks: list = field(default_factory=list)
    warnings: set = field(default_factory=set)
    signatures: list = field(default_factory=list)
    margins: tuple = (43., 28., 30., 30.)
    landscape: bool = False


def _xml_tree(data):
    depth = nodes = 0
    iterator = iterparse(BytesIO(data), events=("start", "end"), forbid_dtd=True,
                         forbid_entities=True, forbid_external=True)
    for event, element in iterator:
        if event == "start":
            depth += 1
            nodes += 1
            if depth > 50 or nodes > MAX_NODES:
                raise ValueError("UDF belge yapısı çok büyük veya iç içe.")
        else:
            depth -= 1
    return iterator.root


def _archive(source):
    if Path(source).stat().st_size > 64 << 20:
        raise ValueError("UDF arşivi 64 MB sınırını aşıyor.")
    try:
        with ZipFile(source) as archive:
            entries = archive.infolist()
            contents = [item for item in entries if item.filename == "content.xml"]
            if len(entries) > 256 or len(contents) != 1 or contents[0].file_size > MAX_XML:
                raise ValueError("UDF tek bir content.xml içermeli (en fazla 8 MB).")
            with archive.open(contents[0]) as stream:
                data = stream.read(MAX_XML + 1)
            if len(data) > MAX_XML:
                raise ValueError("UDF XML içeriği çok büyük.")
            signatures = sorted(item.filename for item in entries if not item.is_dir() and
                                (Path(item.filename).suffix.lower() in {".sgn", ".p7s", ".p7m", ".xsig", ".xades"} or
                                 "signature" in item.filename.lower() or "imza" in item.filename.lower()))
    except (BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ValueError("Bu UDF arşivi açılamadı.") from error
    return _xml_tree(data), signatures


def _bounded_integer(value, low, high):
    try:
        n = int(value)
    except (ValueError, TypeError) as error:
        raise ValueError("UDF öğesinin sayı alanı geçersiz.") from error
    if not low <= n <= high:
        raise ValueError("UDF öğesinin sayı alanı sınır dışında.")
    return n


def _marker(number, kind):
    if kind == "bullet":
        return "•"
    if kind in {"lowerLetter", "upperLetter"}:
        letters = ""
        while number:
            number, digit = divmod(number - 1, 26)
            letters = chr(ord("a") + digit) + letters
        return letters.upper() if kind == "upperLetter" else letters
    if kind in {"upperRoman", "lowerRoman"}:
        roman = ""
        for value, symbol in [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
                              (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]:
            count, number = divmod(number, value)
            roman += symbol * count
        return roman.lower() if kind == "lowerRoman" else roman
    return str(number)


def _read(source):
    root, signatures = _archive(source)
    content, elements = root.find("content"), root.find("elements")
    if root.tag != "template" or content is None or elements is None:
        raise ValueError("UDF belge metni veya öğe ağacı eksik.")
    text = (content.text or "").encode("utf-16-le")
    if len(text) > MAX_UNITS * 2:
        raise ValueError("UDF belge metni işleme sınırını aşıyor.")
    document = Document(signatures=signatures)
    page = root.find("./properties/pageFormat")
    if page is not None:
        if page.get("mediaSizeName","1") != "1":
            document.warnings.add("Standart dışı kâğıt boyutu A4 olarak aktarılır.")
        document.landscape = page.get("paperOrientation","1") == "0"
        margins = tuple(float(page.get(k, d)) for k,d in zip(
            ("leftMargin","rightMargin","topMargin","bottomMargin"),document.margins))
        if not all(0 <= n <= 180 for n in margins):
            raise ValueError("UDF sayfa kenar boşlukları desteklenen aralıkta değil.")
        document.margins = margins

    remaining = MAX_UNITS
    counters = Counter()
    implicit = 0
    active_implicit = False

    def paragraph(node):
        nonlocal remaining, implicit, active_implicit
        runs = []
        for inline in node:
            if inline.tag in {"content", "field", "space", "tab"} and "startOffset" in inline.attrib:
                start = _bounded_integer(inline.get("startOffset"), 0, len(text)//2)
                length = _bounded_integer(inline.get("length"), 0, min(remaining,len(text)//2-start))
                remaining -= length
                try:
                    value = text[start*2:(start+length)*2].decode("utf-16-le")
                except UnicodeDecodeError as error:
                    raise ValueError("UDF metin aralığı bir Unicode karakterini bölüyor.") from error
                if inline.tag == "field":
                    document.warnings.add("Dinamik alanlar kayıtlı metinleriyle aktarılır.")
            elif inline.tag in {"tab", "space"}:
                value = "\t" if inline.tag == "tab" else " "
            else:
                document.warnings.add("Aktarılmayan öğe: " + inline.tag)
                value = "[Görsel]" if inline.tag == "image" else ""
            runs.append(Run(value.replace("\u200b",""), *(inline.get(k)=="true" for k in ("bold","italic","underline"))))
        if runs:
            runs[-1].text = runs[-1].text.removesuffix("\n")
        p = Paragraph(runs, _bounded_integer(node.get("Alignment","0"),0,3))
        numbered, bulleted = node.get("Numbered")=="true", node.get("Bulleted")=="true"
        if numbered or bulleted:
            p.level = _bounded_integer(node.get("ListLevel","0"),0,8)
            if node.get("ListId") is not None:
                p.list_id = "id:" + node.get("ListId")
                active_implicit = False
            else:
                if not active_implicit:
                    implicit += 1
                active_implicit = True
                p.list_id = "group:" + str(implicit)
            style = node.get("NumberType", DECIMAL)
            if numbered and style not in FORMATS:
                document.warnings.add("Desteklenmeyen numaralandırma ondalık gösterilir: " + style)
            p.number_format, p.suffix = FORMATS.get(style, FORMATS[DECIMAL]) if numbered else ("bullet","")
            for level in range(p.level+1,9):
                counters.pop((p.list_id,level),None)
            counters[p.list_id,p.level] += 1
            p.marker = _marker(counters[p.list_id,p.level],p.number_format) + p.suffix
        else:
            active_implicit = False
        return p

    def blocks(parent):
        for child in parent:
            if child.tag == "paragraph":
                yield paragraph(child)
            elif child.tag == "table":
                rows = []
                for row in child:
                    if row.tag != "row":
                        document.warnings.add("Aktarılmayan tablo öğesi: " + row.tag)
                        continue
                    cells = []
                    for cell in row:
                        if cell.tag != "cell":
                            document.warnings.add("Aktarılmayan satır öğesi: " + cell.tag)
                            continue
                        if cell.get("colspan","1") != "1" or cell.get("rowspan","1") != "1":
                            document.warnings.add("Birleştirilmiş hücreler ayrı hücreler olarak aktarılır.")
                        contents = []
                        for block in blocks(cell):
                            if isinstance(block, Paragraph):
                                contents.append(block)
                            else:
                                document.warnings.add("İç içe tablolar hücre içinde paragraflara dönüştürülür.")
                                contents.extend(p for r in block.rows for c in r for p in c)
                        cells.append(contents)
                    if len(cells)>30:
                        raise ValueError("UDF tablosu en fazla 30 sütun içerebilir.")
                    if cells:
                        rows.append(cells)
                if rows:
                    yield Table(rows)
            else:
                document.warnings.add("Aktarılmayan belge öğesi: " + child.tag)
    document.blocks = list(blocks(elements))
    if not document.blocks:
        raise ValueError("UDF içinde önizlenebilir paragraf veya tablo bulunamadı.")
    if signatures:
        document.warnings.add("İmza bileşeni özgün UDF içinde saklanır. PDF ve DOCX imzasız çalışma kopyalarıdır; imza geçerliliği denetlenmedi.")
    document.warnings.add("Sayfalama, yazı tipi ve aralıklar değişebilir. Önizleme metni ve tablo sırasını gösterir.")
    return document


@lru_cache(maxsize=1)
def _pdf_fonts():
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    folder = Path(reportlab.__file__).parent / "fonts"
    for variant,file in (("UdfVera","Vera.ttf"),("UdfBold","VeraBd.ttf"),("UdfItalic","VeraIt.ttf"),("UdfBI","VeraBI.ttf")):
        if variant not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(variant,str(folder/file)))
    pdfmetrics.registerFontFamily("UdfVera",normal="UdfVera",bold="UdfBold",italic="UdfItalic",boldItalic="UdfBI")
    return pdfmetrics.getFont("UdfVera").face.charToGlyph


def inspect_udf(source):
    """Return read-only text, structural counts and disclosures for the GUI."""
    doc = _read(source)
    lines, paragraphs, numbered, tables = [], 0, 0, 0
    for block in doc.blocks:
        if isinstance(block, Paragraph):
            lines.append(block.text())
            paragraphs += 1
            numbered += block.marker != "" and block.number_format != "bullet"
        else:
            tables += 1
            for row in block.rows:
                lines.append(" | ".join(" / ".join(p.text() for p in cell) for cell in row))
                for cell in row:
                    paragraphs += len(cell)
                    numbered += sum(bool(p.marker) and p.number_format!="bullet" for p in cell)
    text = "\n".join(lines)
    glyphs = _pdf_fonts()
    missing = sorted(ord(c) for c in set(text) if not c.isspace() and ord(c) not in glyphs)
    if missing:
        points = ", ".join(f"U+{code:04X}" for code in missing[:12])
        doc.warnings.add("PDF yazı tipinde eksik karakterler var. DOCX metni karakterleri korur: " + points)
    return {"text":text, "warnings":sorted(doc.warnings), "signatureParts":doc.signatures,
            "paragraphs":paragraphs, "numberedParagraphs":numbered, "tables":tables}


def render_pdf(source, target):
    """Lay out paragraphs and tables with an embedded Turkish-capable Unicode font."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import LongTable, Paragraph as PdfParagraph, SimpleDocTemplate, TableStyle

    doc = _read(source)
    _pdf_fonts()
    left,right,top,bottom = doc.margins
    size = landscape(A4) if doc.landscape else A4

    def make_paragraph(p):
        markup = escape(p.marker) + " " if p.marker else ""
        for run in p.runs:
            value = escape(run.text).replace("\t","&#160;"*4).replace("\n","<br/>")
            for enabled,tag in ((run.bold,"b"),(run.italic,"i"),(run.underline,"u")):
                if enabled:
                    value = f"<{tag}>{value}</{tag}>"
            markup += value
        style = ParagraphStyle("UDF",fontName="UdfVera",fontSize=10.5,leading=14,
                               alignment=p.align,leftIndent=p.level*10,spaceAfter=4)
        return PdfParagraph(markup or "&#160;",style)

    story = []
    for block in doc.blocks:
        if isinstance(block,Paragraph):
            story.append(make_paragraph(block))
        else:
            width = max(map(len,block.rows))
            matrix = [[([make_paragraph(p) for p in cell] or [""]) for cell in row]
                      + [""]*(width-len(row)) for row in block.rows]
            table = LongTable(matrix,colWidths=[(size[0]-left-right-12)/width]*width,
                              splitByRow=1,splitInRow=1,hAlign="LEFT")
            table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.grey),
                                       ("VALIGN",(0,0),(-1,-1),"TOP")]))
            story.append(table)
    with new_file(target) as prepared:
        SimpleDocTemplate(str(prepared),pagesize=size,leftMargin=left,rightMargin=right,
                          topMargin=top,bottomMargin=bottom,title=Path(source).stem).build(story)
    return Path(target)


def export_docx(source, target):
    """Write editable paragraphs, native Word tables, list definitions and list IDs."""
    from docx import Document as WordDocument
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt

    doc = _read(source)
    word = WordDocument()
    section = word.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE if doc.landscape else WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = (Mm(297),Mm(210)) if doc.landscape else (Mm(210),Mm(297))
    section.left_margin,section.right_margin,section.top_margin,section.bottom_margin = map(Pt,doc.margins)
    numbering = word.part.numbering_part.element
    styles_by_list = {}
    for block in doc.blocks:
        paragraphs = [block] if isinstance(block,Paragraph) else [p for row in block.rows for cell in row for p in cell]
        for p in paragraphs:
            if p.list_id is not None:
                styles_by_list.setdefault(p.list_id,{})[p.level]=(p.number_format,p.suffix)

    def child(parent,name,value):
        node=OxmlElement("w:"+name)
        node.set(qn("w:val"),str(value))
        parent.append(node)
        return node

    # Keep separate numbering instances for distinct UDF list IDs, including lists in table cells.
    ids = {}
    base=max((int(n.get(qn("w:abstractNumId"))) for n in numbering.findall(qn("w:abstractNum"))), default=-1)+1
    for offset,(key,levels) in enumerate(styles_by_list.items()):
        abstract=OxmlElement("w:abstractNum")
        number=base+offset
        abstract.set(qn("w:abstractNumId"),str(number))
        child(abstract,"multiLevelType","multilevel")
        for index in range(max(levels)+1):
            fmt,suffix=levels.get(index,("decimal","."))
            level=OxmlElement("w:lvl"); level.set(qn("w:ilvl"),str(index)); abstract.append(level)
            child(level,"start",1)
            child(level,"numFmt",fmt)
            child(level,"lvlText","•" if fmt=="bullet" else f"%{index+1}{suffix}")
            child(level,"lvlJc","left")
        # ECMA-376 places abstract definitions before concrete numbering instances.
        numbering.insert_element_before(abstract,"w:num","w:numIdMacAtCleanup")
        ids[key]=numbering.add_num(number).numId

    def put_paragraph(p,destination):
        destination.alignment=(WD_ALIGN_PARAGRAPH.LEFT,WD_ALIGN_PARAGRAPH.CENTER,WD_ALIGN_PARAGRAPH.RIGHT,WD_ALIGN_PARAGRAPH.JUSTIFY)[p.align]
        if p.list_id is not None:
            numbering_props=destination._p.get_or_add_pPr().get_or_add_numPr()
            numbering_props.get_or_add_ilvl().val=p.level
            numbering_props.get_or_add_numId().val=ids[p.list_id]
            destination.paragraph_format.left_indent=Pt(14+p.level*12)
        for r in p.runs:
            run=destination.add_run(r.text)
            run.bold,run.italic,run.underline=r.bold,r.italic,r.underline

    for block in doc.blocks:
        if isinstance(block,Paragraph):
            put_paragraph(block,word.add_paragraph())
        else:
            cols=max(map(len,block.rows))
            table=word.add_table(rows=0,cols=cols)
            table.style="Table Grid"
            for row in block.rows:
                cells=table.add_row().cells
                for i,paragraphs in enumerate(row):
                    for j,p in enumerate(paragraphs):
                        put_paragraph(p,cells[i].paragraphs[0] if j==0 else cells[i].add_paragraph())
    with new_file(target) as prepared:
        word.save(prepared)
    return Path(target)
