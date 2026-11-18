import qrcode
import zxingcpp
from PIL import Image
from qrcode.exceptions import DataOverflowError


def make(text, size=512, level="M"):
    if not text.strip() or not 64 <= size <= 4096 or level not in {"L","M","Q","H"}:
        raise ValueError("Metin, düzeltme seviyesi ve 64–4096 px aralığında bir boyut seçin.")
    qr = qrcode.QRCode(error_correction=getattr(qrcode.constants, "ERROR_CORRECT_" + level), border=4)
    qr.add_data(text.encode("utf-8"), optimize=0)
    try:
        qr.make(fit=True)
    except DataOverflowError as exc:
        raise ValueError("Metin bu QR koduna sığmıyor.") from exc
    count = qr.modules_count + 8
    qr.box_size = size // count
    if not qr.box_size:
        raise ValueError("Okunabilir modüller için daha büyük bir çıktı seçin.")
    pattern = qr.make_image().convert("L")
    result = Image.new("L", (size, size), 255)
    result.paste(pattern, ((size - pattern.width)//2, (size - pattern.height)//2))
    return result


def read(image):
    return [item.text for item in zxingcpp.read_barcodes(image.convert("RGB"), formats=zxingcpp.BarcodeFormat.QRCode)]
