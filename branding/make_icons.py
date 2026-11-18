"""Render the Pivoki folded-sheet mark. Requires Pillow and macOS iconutil for ICNS."""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
canvas = Image.new("RGBA", (1024, 1024))
draw = ImageDraw.Draw(canvas)
draw.rounded_rectangle((50, 50, 974, 974), radius=214, fill="#213E31")
# The paper stack forms a P. The folded corner points toward the two output sheets.
draw.polygon([(263, 402), (449, 505), (449, 790), (263, 684)], fill="#8BB787")
draw.polygon([(263, 402), (550, 240), (764, 357), (477, 523)], fill="#E6F3BE")
draw.polygon([(477, 523), (764, 357), (764, 454), (477, 620)], fill="#B9D87D")
draw.polygon([(477, 660), (715, 524), (715, 612), (477, 749)], fill="#73A77B")
canvas.save(ROOT / "Pivoki.png", optimize=True)
canvas.save(ROOT / "Pivoki.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
with tempfile.TemporaryDirectory() as tmp:
    iconset = Path(tmp) / "Pivoki.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = "@2x" if scale == 2 else ""
            image = canvas.resize((size * scale,) * 2, Image.Resampling.LANCZOS)
            image.save(iconset / f"icon_{size}x{size}{suffix}.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ROOT / "Pivoki.icns")], check=True)
