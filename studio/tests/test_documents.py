import tempfile
from pathlib import Path
import unittest
import zipfile

from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from pivoki_studio import documents


class Documents(unittest.TestCase):
    def test_page_selection_preserves_other_text_and_originals(self):
        with tempfile.TemporaryDirectory() as root:
            source, result, zipped = [Path(root,n) for n in ("s.pdf","r.pdf","originals.zip")]
            pdf = Canvas(str(source),pagesize=(200,300))
            for n in range(3):
                pdf.drawString(15,100,f"Page {n+1}")
                pdf.showPage()
            pdf.save()
            before=source.read_bytes()
            documents.working_copy(source, result, watermark={"text":"Pivoki"},pages="2")
            reader=PdfReader(result)
            self.assertEqual(len(reader.pages),3)
            self.assertEqual([len(p.images) for p in reader.pages],[0,1,0])
            self.assertIn("Page 2",reader.pages[1].extract_text())
            documents.original_zip([source,source],zipped)
            with zipfile.ZipFile(zipped) as check:
                self.assertEqual(len(check.namelist()),2)
                for name in check.namelist():
                    self.assertEqual(check.read(name),before)
            self.assertEqual(source.read_bytes(),before)

    def test_selected_svg_pages_are_published_as_a_single_set(self):
        import shutil
        import xml.etree.ElementTree as ET
        from pivoki_studio.svg_export import export_pages
        if not shutil.which("pdftocairo"):
            self.skipTest("Poppler is required")
        with tempfile.TemporaryDirectory() as root:
            source=Path(root,"vector.pdf")
            pdf=Canvas(str(source))
            for i in range(2):
                pdf.circle(50,50,15,fill=1)
                pdf.showPage()
            pdf.save()
            result=export_pages(source,Path(root),[0,1])
            self.assertEqual(sorted(p.name for p in result.iterdir()),["0001.svg","0002.svg"])
            for p in result.iterdir():
                self.assertTrue(ET.parse(p).findall(".//{http://www.w3.org/2000/svg}path"))
            with self.assertRaises(FileExistsError):
                export_pages(source,Path(root),[0])
            self.assertEqual(len(list(result.iterdir())),2)

    def test_pdfa_independent_validator_and_broken_input(self):
        import shutil
        from pivoki_studio.files import new_file
        if not shutil.which("verapdf") or not (shutil.which("gs") or shutil.which("gswin64c")):
            self.skipTest("Ghostscript and veraPDF required")
        with tempfile.TemporaryDirectory() as root:
            src, out=Path(root,"drawing.pdf"),Path(root,"archive.pdf")
            pdf=Canvas(str(src))
            pdf.drawString(10,20,"Pivoki")
            pdf.showPage()
            pdf.save()
            with new_file(out) as stage:
                documents.pdf_archive(src,stage)
            self.assertEqual(len(PdfReader(out).pages),1)
            src.write_bytes(b"broken input")
            with self.assertRaises(Exception), new_file(Path(root,"bad.pdf")) as stage:
                documents.pdf_archive(src,stage)
            self.assertFalse(Path(root,"bad.pdf").exists())
