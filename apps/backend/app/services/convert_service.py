import os
from pathlib import Path
from typing import List
from PIL import Image

POPPLER_PATH = os.getenv("POPPLER_PATH", "/opt/homebrew/bin")
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp"}


def convert_to_pages(source_path: str, output_dir: Path) -> List[str]:
    ext = Path(source_path).suffix.lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    if ext == ".pdf":
        return _pdf_to_pages(source_path, output_dir)
    elif ext in SUPPORTED_IMAGE_EXTS:
        return _image_to_page(source_path, output_dir)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _pdf_to_pages(pdf_path: str, output_dir: Path) -> List[str]:
    from pdf2image import convert_from_path
    images = convert_from_path(
        pdf_path,
        dpi=200,
        fmt="png",
        poppler_path=POPPLER_PATH,
    )
    paths = []
    for i, img in enumerate(images, start=1):
        out_path = output_dir / f"page_{i:03d}.png"
        img.save(str(out_path), "PNG")
        paths.append(str(out_path))
    return paths


def _image_to_page(image_path: str, output_dir: Path) -> List[str]:
    img = Image.open(image_path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    out_path = output_dir / "page_001.png"
    img.save(str(out_path), "PNG")
    return [str(out_path)]
