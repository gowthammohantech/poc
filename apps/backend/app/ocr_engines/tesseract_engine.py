import os
from typing import List, Dict, Any
import pytesseract
from PIL import Image
import pandas as pd

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "/opt/homebrew/bin/tesseract")
TESSDATA_PREFIX = os.getenv("TESSDATA_PREFIX", "/opt/homebrew/share/tessdata")
CONFIDENCE_THRESHOLD = 60.0

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
os.environ.setdefault("TESSDATA_PREFIX", TESSDATA_PREFIX)


def run_tesseract(image_paths: List[str]) -> Dict[str, Any]:
    all_text_parts = []
    all_confidences = []
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
        except Exception as e:
            all_text_parts.append("")

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
        },
    }
