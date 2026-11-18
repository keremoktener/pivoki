import tempfile
from pathlib import Path

from pivoki_engine.filesystem import output_root
from pivoki_engine.model import inspect_root
from .documents import pdf_svg


def export_pages(source, destination, pages):
    destination = Path(destination).resolve(strict=True)
    label = Path(source).stem + " - SVG"
    # Exclusive directory rename publishes the whole set, or leaves the original set intact.
    with output_root(destination, inspect_root(destination)) as root:
        with tempfile.TemporaryDirectory(prefix=".pivoki-svg-", dir=destination) as tmp:
            for page in pages:
                pdf_svg(source,page+1,Path(tmp)/f"{page+1:04}.svg")
            root.publish(Path(tmp).name,label)
    return destination / label
