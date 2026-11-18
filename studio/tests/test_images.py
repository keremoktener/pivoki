import unittest

from PIL import Image, ImageDraw
from pathlib import Path
from tempfile import TemporaryDirectory

from pivoki_studio import images, qr
from pivoki_studio.files import new_file


class ImageExports(unittest.TestCase):
    def test_qr_decodes_utf8_at_requested_dimensions(self):
        text = "İstanbul'dan merhaba 🌿"
        encoded = qr.make(text, 513, "Q")
        self.assertEqual(encoded.size, (513, 513))
        self.assertEqual(qr.read(encoded), [text])

    def test_caption_keeps_original_and_grows(self):
        original = Image.new("RGBA", (210, 90), "navy")
        result = images.caption(original, "Türkçe karakterli uzun açıklama " * 14)
        self.assertGreater(result.height, 150)
        self.assertEqual(result.crop((0, 0, *original.size)).tobytes(), original.tobytes())
        self.assertEqual(images.caption(original, "").size, original.size)

    def test_connected_background_retains_white_in_enclosed_shape(self):
        original = Image.new("RGBA", (40, 30), "white")
        pen = ImageDraw.Draw(original)
        pen.rectangle((8, 7, 30, 22), outline="black", width=2)
        result = images.remove_background(original, 4, 0)
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((20, 15))[3], 255)

    def test_ico_has_seven_layers_and_no_overwrite(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "sample.ico")
            with new_file(path) as work:
                images.write_ico(Image.new("RGBA", (80, 40), "red"), work)
            with Image.open(path) as im:
                self.assertEqual(len(im.ico.sizes()), 7)
                self.assertEqual(im.getpixel((0,0))[3], 0)
            with self.assertRaises(FileExistsError), new_file(path):
                self.fail("An occupied name must fail before writing.")

    def test_collision_after_open_preserved(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "result")
            with self.assertRaises(FileExistsError):
                with new_file(path) as work:
                    work.write_bytes(b"ours")
                    path.write_bytes(b"competitor")
            self.assertEqual(path.read_bytes(), b"competitor")
