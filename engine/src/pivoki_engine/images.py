import hashlib
import os
from pathlib import Path
import stat

from PIL import Image, ImageOps, features, UnidentifiedImageError

from .model import FORMATS, Problem, linked

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
DECODERS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF"}
try:
    import pillow_heif
except ImportError:
    pass
else:
    pillow_heif.register_heif_opener()
    EXTENSIONS.update({".heic", ".heif"})
    DECODERS.add("HEIF")
if features.check("avif"):
    EXTENSIONS.add(".avif")
    DECODERS.add("AVIF")


def content_hash(stream, check=lambda: None, copy_to=None):
    h = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        check()
        h.update(chunk)
        if copy_to is not None:
            copy_to.write(chunk)
    return h.hexdigest()


def signature(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns]


def fingerprint(path, check=lambda: None, snapshot=None):
    before = path.lstat()
    if linked(before) or not stat.S_ISREG(before.st_mode):
        raise Problem("source_changed", f"Source is no longer a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        digest = content_hash(stream, check, snapshot)
        if signature(before) != signature(os.fstat(stream.fileno())) or signature(before) != signature(path.lstat()):
            raise Problem("source_changed", f"Source changed while reading: {path}")
    if snapshot:
        snapshot.seek(0)
    return [*signature(before), digest]


def inspect_image(path):
    try:
        with Image.open(path, formats=tuple(DECODERS)) as image:
            return {"format": image.format, "width": image.width, "height": image.height,
                    "frames": getattr(image, "n_frames", 1), "mode": image.mode}
    except (UnidentifiedImageError, Image.DecompressionBombError, ValueError) as exc:
        raise Problem("invalid_image", f"Cannot read {path}: {exc}") from exc


def encode(original, spec, stream):
    image = original.copy()
    try:
        image.thumbnail((spec["maxEdge"], spec["maxEdge"]), Image.Resampling.LANCZOS)
        fmt = spec["format"]
        alpha = image.has_transparency_data
        if fmt == "jpg" and alpha:
            rgba = image.convert("RGBA")
            layer = Image.new("RGB", image.size, "white")
            layer.paste(rgba, mask=rgba.getchannel("A"))
            image.close()
            image = layer
            rgba.close()
        elif image.mode not in ("RGB", "RGBA", "L") or (fmt == "jpg" and image.mode == "RGBA"):
            converted = image.convert("RGBA" if alpha and fmt != "jpg" else "RGB")
            image.close()
            image = converted
        options = {}
        if fmt in ("jpg", "png") and "dpi" in original.info:
            options["dpi"] = original.info["dpi"]
        if fmt in ("jpg", "webp"):
            options["quality"] = 88
        # The pixels have been oriented. Never copy an orientation tag to the derivative.
        image.info.clear()
        image.save(stream, format=FORMATS[fmt], **options)
        return image.size
    finally:
        image.close()


def verify_image(stream, spec, dimensions):
    with Image.open(stream) as decoded:
        decoded.load()
        if decoded.format != FORMATS[spec["format"]] or decoded.size != dimensions:
            raise Problem("validation_failed", "The generated image failed format or dimension validation.")
