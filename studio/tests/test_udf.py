import hashlib
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader

from pivoki_studio.udf import inspect_udf, render_pdf, export_docx


def sample(path, *, mapped=None, signature=True):
    root=ET.Element("template",format_id="1.8")
    payload=ET.SubElement(root,"content")
    elements=ET.SubElement(root,"elements")
    offset=0
    strings=[]

    def para(parent,text,**attributes):
        nonlocal offset
        p=ET.SubElement(parent,"paragraph",attributes)
        length=len(text.encode("utf-16-le"))//2
        ET.SubElement(p,"content",startOffset=str(offset),length=str(length))
        strings.append(text+"\n")
        offset+=length+1

    para(elements,"Örnek 🗂 dosya")
    para(elements,"İlk öğe",Numbered="true",ListId="45",NumberType="NUMBER_TYPE_NUMBER_DOT")
    para(elements,"Çalışma tutanağı",Numbered="true",ListId="45")
    row=ET.SubElement(ET.SubElement(elements,"table",columnCount="2"),"row")
    para(ET.SubElement(row,"cell"),"Süre")
    para(ET.SubElement(row,"cell"),"Üç gün")
    para(elements,"Şube görüşü")
    if mapped:
        mapped(elements)
    payload.text="".join(strings)
    with ZipFile(path,"w",compression=ZIP_DEFLATED) as z:
        z.writestr("content.xml",ET.tostring(root,encoding="utf-8",xml_declaration=True))
        if signature:
            z.writestr("sign.sgn","synthetic unsigned signature marker")
            z.writestr("META-INF/signatures.p7s","synthetic unsigned signature marker")
    return path


class Udf(unittest.TestCase):
    def test_preview_pdf_and_editable_word_preserve_content_and_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            source=sample(root/"örnek.udf")
            saved=hashlib.sha256(source.read_bytes()).digest()
            preview=inspect_udf(source)
            self.assertEqual((preview["tables"],preview["numberedParagraphs"],preview["paragraphs"]),(1,2,6))
            self.assertIn("1. İlk öğe\n2. Çalışma tutanağı",preview["text"])
            self.assertIn("Süre | Üç gün",preview["text"])
            self.assertEqual(preview["signatureParts"], ["META-INF/signatures.p7s","sign.sgn"])
            self.assertTrue(any("U+1F5C2" in w for w in preview["warnings"]))
            dest=render_pdf(source,root/"copy.pdf")
            text="\n".join(page.extract_text() for page in PdfReader(dest).pages)
            for line in ["1. İlk öğe","2. Çalışma tutanağı","Süre","Üç gün","Şube görüşü"]:
                self.assertIn(line,text)
            out=export_docx(source,root/"copy.docx")
            word=Document(out)
            self.assertEqual(word.tables[0].cell(0,1).text,"Üç gün")
            self.assertEqual(word.paragraphs[1].text,"İlk öğe")
            first,second=[p._p.find("./"+qn("w:pPr")+"/"+qn("w:numPr")+"/"+qn("w:numId")) for p in word.paragraphs[1:3]]
            self.assertEqual(first.val,second.val)
            with self.assertRaises(FileExistsError):
                render_pdf(source,dest)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),saved)

    def test_invalid_offsets_dtd_and_unsupported_content(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            def broken(elements):
                child=elements[0][0]
                child.set("startOffset","6"); child.set("length","1")
            invalid=sample(root/"offset.udf",mapped=broken)
            with self.assertRaisesRegex(ValueError,"Unicode"):
                inspect_udf(invalid)
            unknown=sample(root/"image.udf",mapped=lambda el:ET.SubElement(el[0],"image",imageData="omitted"))
            self.assertTrue(any("image" in item for item in inspect_udf(unknown)["warnings"]))
            dtd=root/"bad.udf"
            with ZipFile(dtd,"w") as z:
                z.writestr("content.xml",'<!DOCTYPE template><template><content/><elements/></template>')
            with self.assertRaises(ValueError):
                inspect_udf(dtd)

    def test_plan_and_export_do_not_write_through_existing_target(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            source=sample(root/"original.udf")
            target=root/"existing.docx"
            target.write_bytes(b"prior")
            with self.assertRaises(FileExistsError):
                export_docx(source,target)
            self.assertEqual(target.read_bytes(),b"prior")
