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
