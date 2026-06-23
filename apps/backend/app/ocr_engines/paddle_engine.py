from typing import List, Dict, Any

CONFIDENCE_THRESHOLD = 0.70


def run_paddle(image_paths: List[str]) -> Dict[str, Any]:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return {
            "text": "",
            "confidence": 0.0,
            "word_count": 0,
            "low_confidence": True,
            "metadata": {"engine": "PADDLEOCR", "error": "paddleocr not installed"},
        }

    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    all_text_parts = []
    all_confidences = []
    word_count = 0

    for path in image_paths:
        try:
            result = ocr.ocr(path, cls=True)
            if not result or not result[0]:
                all_text_parts.append("")
                continue
            lines = []
            for line in result[0]:
                if line and len(line) >= 2:
                    text_info = line[1]
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                        text = str(text_info[0])
                        conf = float(text_info[1])
                        lines.append(text)
                        all_confidences.append(conf)
                        word_count += len(text.split())
            all_text_parts.append("\n".join(lines))
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
            "engine": "PADDLEOCR",
            "pages_processed": len(image_paths),
            "avg_confidence": avg_confidence,
        },
    }
