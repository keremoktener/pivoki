from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

SIZES = [16, 24, 32, 48, 64, 128, 256]


def source_image(path):
    with Image.open(path) as original:
        return ImageOps.exif_transpose(original).convert("RGBA")


def font(size):
    import reportlab
    return ImageFont.truetype(str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"), size=size)


def wrap_lines(text, face, width):
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            if current and face.getlength(current + " " + word) > width:
                lines.append(current)
                current = ""
            current = (current + " " + word).lstrip()
            while face.getlength(current) > width and len(current) > 1:
                lo, hi = 1, len(current) - 1
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if face.getlength(current[:mid]) <= width:
                        lo = mid
                    else:
                        hi = mid - 1
                lines.append(current[:lo])
                current = current[lo:]
        lines.append(current)
    return lines


def caption(image, text):
    if not text.strip():
        return image.copy()
    pad = min(32, max(1, image.width // 40))
    face = font(max(9, min(72, image.width // 35)))
    lines = wrap_lines(text, face, max(1, image.width - 2 * pad))
    height = sum(face.getmetrics()) + max(1, face.size // 5)
    out = Image.new("RGBA", (image.width, image.height + pad * 2 + height * len(lines)), "white")
    out.paste(image, (0, 0))
    pen = ImageDraw.Draw(out)
    for i, line in enumerate(lines):
        pen.text((pad, image.height + pad + i * height), line, font=face, fill="#202921")
    return out


def watermark_overlay(size, *, text="", logo=None, corner="BR", margin=4, opacity=70):
    width, height = size
    if corner not in {"TR", "TL", "BR", "BL"} or not 0 <= margin <= 40 or not 0 <= opacity <= 100:
        raise ValueError("Filigran ayarlarını kontrol edin.")
    if logo:
        mark = source_image(logo)
        mark.thumbnail((max(1, width // 3), max(1, height // 3)), Image.Resampling.LANCZOS)
    else:
        if not text.strip():
            raise ValueError("Filigran için metin girin veya logo seçin.")
        face = font(max(8, min(width, height) // 16))
        box = face.getbbox(text, stroke_width=1)
        mark = Image.new("RGBA", (max(1, box[2] - box[0]), max(1, box[3] - box[1])))
        ImageDraw.Draw(mark).text((-box[0], -box[1]), text, font=face, fill="white",
                                  stroke_width=1, stroke_fill="#202921")
        mark.thumbnail((max(1, width * 3 // 4), max(1, height // 3)), Image.Resampling.LANCZOS)
    mark.putalpha(mark.getchannel("A").point(lambda x: round(x * opacity / 100)))
    inset = round(min(width, height) * margin / 100)
    x = inset if corner[1] == "L" else width - inset - mark.width
    y = inset if corner[0] == "T" else height - inset - mark.height
    overlay = Image.new("RGBA", size)
    overlay.alpha_composite(mark, (x, y))
    return overlay


def remove_background(image, tolerance, feather):
    if not (0 <= tolerance <= 255 and 0 <= feather <= 32):
        raise ValueError("Tolerans 0–255, yumuşatma 0–32 aralığında olmalı.")
    rgb = image.convert("RGB")
    w, h = rgb.size
    sample = [rgb.getpixel((x, y)) for x in range(0, w, max(1, w // 48)) for y in (0, h-1)]
    sample += [rgb.getpixel((x, y)) for y in range(0, h, max(1, h // 48)) for x in (0, w-1)]
    background = Counter(sample).most_common(1)[0][0]
    delta = ImageChops.difference(rgb, Image.new("RGB", rgb.size, background))
    r, g, b = delta.split()
    similar = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda d: 255 if d <= tolerance else 0)
    # Connect all four edges through an extra border, then identify their component.
    bordered = ImageOps.expand(similar, 1, fill=255)
    ImageDraw.floodfill(bordered, (0, 0), 128)
    alpha = bordered.crop((1, 1, w+1, h+1)).point(lambda p: 0 if p == 128 else 255)
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    result = image.copy()
    result.putalpha(ImageChops.multiply(alpha, result.getchannel("A")))
    return result


def polygon(image, points):
    if len(set(points)) < 3:
        raise ValueError("Şekli kapatmak için üç farklı köşe gerekir.")
    if any(not 0 <= n <= 1 for point in points for n in point):
        raise ValueError("Köşe görüntü sınırları içinde olmalı.")
    vertices = [(round(x * (image.width-1)), round(y * (image.height-1))) for x,y in points]
    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    draw.polygon(vertices, fill=(166, 224, 81, 72))
    draw.line(vertices + vertices[:1], fill="#356343", width=max(1, min(image.size)//180), joint="curve")
    return Image.alpha_composite(image, overlay)


def write_ico(image, path):
    tile = Image.new("RGBA", (256, 256))
    fg = ImageOps.contain(image, tile.size, Image.Resampling.LANCZOS)
    tile.alpha_composite(fg, ((256-fg.width)//2, (256-fg.height)//2))
    tile.save(path, format="ICO", sizes=[(n, n) for n in SIZES])
    with Image.open(path) as check:
        if check.ico.sizes() != {(n, n) for n in SIZES}:
            raise ValueError("ICO katmanları doğrulanamadı.")


def exif_time(path, offset=""):
    with Image.open(path) as im:
        fields = im.getexif().get_ifd(0x8769)
    stamp = fields.get(36867)
    if not stamp:
        raise ValueError("Çekim tarihi (DateTimeOriginal) bulunamadı.")
    zone = fields.get(36881) or offset
    if not isinstance(zone, str) or not re.fullmatch(r"[+-](?:0\d|1[0-4]):[0-5]\d", zone):
        raise ValueError("EXIF saat dilimi belirsiz. ±SS:DD biçiminde bir saat dilimi girin.")
    minutes = (int(zone[1:3])*60 + int(zone[4:6])) * (-1 if zone[0] == "-" else 1)
    return datetime.strptime(stamp, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone(timedelta(minutes=minutes)))
