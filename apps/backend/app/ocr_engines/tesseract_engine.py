import os
from typing import List, Dict, Any
import pytesseract
from PIL import Image
import pandas as pd

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "/opt/homebrew/bin/tesseract")
TESSDATA_PREFIX = os.getenv("TESSDATA_PREFIX", "/opt/homebrew/share/tessdata")
CONFIDENCE_THRESHOLD = 60.0
TESSERACT_CONFIG = "--psm 6 -c preserve_interword_spaces=1"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
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
                                              lang="eng", config=TESSERACT_CONFIG)
            words = [w for w, c in zip(data["text"], data["conf"])
                     if w.strip() and _to_confidence(c) > 0]
            confs = [_to_confidence(c) for w, c in zip(data["text"], data["conf"])
                     if w.strip() and _to_confidence(c) > 0]
            page_text = pytesseract.image_to_string(img, lang="eng", config=TESSERACT_CONFIG)
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
                    "block_num": int(data.get("block_num", [0])[i]),
                    "line_num": int(data.get("line_num", [0])[i]),
                    "word_num": int(data.get("word_num", [0])[i]),
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


def _to_confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0
