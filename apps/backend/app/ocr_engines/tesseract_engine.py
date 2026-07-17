import os
import shutil
from pathlib import Path
from typing import List, Dict, Any
import pytesseract
from PIL import Image
import pandas as pd

def _resolve_tesseract_cmd() -> str | None:
    configured_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if configured_cmd and Path(configured_cmd).exists():
        return configured_cmd

    discovered_cmd = shutil.which("tesseract")
    if discovered_cmd:
        return discovered_cmd

    return None


def _resolve_tessdata_prefix() -> str | None:
    configured_prefix = os.getenv("TESSDATA_PREFIX", "").strip()
    if configured_prefix and Path(configured_prefix).exists():
        return configured_prefix
    return None


TESSERACT_CMD = _resolve_tesseract_cmd()
TESSDATA_PREFIX = _resolve_tessdata_prefix()
CONFIDENCE_THRESHOLD = 60.0

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
if TESSDATA_PREFIX:
    os.environ.setdefault("TESSDATA_PREFIX", TESSDATA_PREFIX)


def run_tesseract(image_paths: List[str]) -> Dict[str, Any]:
    all_text_parts = []
    all_confidences = []
    page_references = []
    word_count = 0

    for path in image_paths:
        img = Image.open(path)
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT,
                                              lang="eng", config="--psm 6")
            words = [w for w, c in zip(data["text"], data["conf"])
                     if w.strip() and int(c) > 0]
            confs = [int(c) for w, c in zip(data["text"], data["conf"])
                     if w.strip() and int(c) > 0]
            page_text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
            all_text_parts.append(page_text)
            all_confidences.extend(confs)
            word_count += len(words)
            boxes = []
            for i, (word, confidence) in enumerate(zip(data["text"], data["conf"])):
                if not word.strip() or float(confidence) <= 0:
                    continue
                boxes.append({
                    "text": word,
                    "x": int(data["left"][i]),
                    "y": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                    "confidence": float(confidence),
                })
            page_references.append({
                "width": img.width,
                "height": img.height,
                "boxes": boxes,
            })
        except Exception as e:
            all_text_parts.append("")
            page_references.append({"width": img.width, "height": img.height, "boxes": []})

    combined_text = "\n\n--- PAGE BREAK ---\n\n".join(all_text_parts)
    avg_confidence = float(sum(all_confidences) / len(all_confidences)) if all_confidences else 0.0

    return {
        "text": combined_text,
        "confidence": avg_confidence,
        "word_count": word_count,
        "low_confidence": avg_confidence < CONFIDENCE_THRESHOLD,
        "metadata": {
            "engine": "TESSERACT",
            "pages_processed": len(image_paths),
            "avg_word_confidence": avg_confidence,
            "page_references": page_references,
        },
    }
