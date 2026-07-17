import os
import shutil
from pathlib import Path
from typing import List
from PIL import Image
from pdf2image import convert_from_path

def _resolve_poppler_path() -> str | None:
    configured_path = os.getenv("POPPLER_PATH", "").strip()
    if configured_path and Path(configured_path).exists():
        return configured_path

    for candidate in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"):
        pdfinfo = Path(candidate) / ("pdfinfo.exe" if os.name == "nt" else "pdfinfo")
        if pdfinfo.exists():
            return candidate

    if shutil.which("pdfinfo"):
        return None

    return None


POPPLER_PATH = _resolve_poppler_path()
HEIF_EXTS = {".heic", ".heif"}
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", *HEIF_EXTS}


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
    convert_kwargs = {
        "dpi": 200,
        "fmt": "png",
    }
    if POPPLER_PATH:
        convert_kwargs["poppler_path"] = POPPLER_PATH

    images = convert_from_path(pdf_path, **convert_kwargs)
    paths = []
    for i, img in enumerate(images, start=1):
        out_path = output_dir / f"page_{i:03d}.png"
        img.save(str(out_path), "PNG")
        paths.append(str(out_path))
    return paths


def _image_to_page(image_path: str, output_dir: Path) -> List[str]:
    if Path(image_path).suffix.lower() in HEIF_EXTS:
        try:
            from pillow_heif import register_heif_opener
        except ImportError as exc:
            raise ValueError(
                "HEIC/HEIF support requires the pillow-heif package. "
                "Install it with: pip install pillow-heif"
            ) from exc
        register_heif_opener()

    img = Image.open(image_path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    out_path = output_dir / "page_001.png"
    img.save(str(out_path), "PNG")
    return [str(out_path)]
