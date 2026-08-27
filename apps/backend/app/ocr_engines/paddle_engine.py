from typing import List, Dict, Any
from PIL import Image

CONFIDENCE_THRESHOLD = 0.70

_ocr_instance = None


def _get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR

        # PaddleOCR 3.x removed the former ``show_log`` and ``use_angle_cls``
        # constructor options. enable_mkldnn=False works around a crash in
        # paddlepaddle's oneDNN/PIR CPU inference path (NotImplementedError:
        # ConvertPirAttribute2RuntimeAttribute not support ...) that otherwise
        # fails every page and silently degrades this engine to zero confidence.
        _ocr_instance = PaddleOCR(lang="en", enable_mkldnn=False)
    return _ocr_instance


def run_paddle(image_paths: List[str]) -> Dict[str, Any]:
    try:
        ocr = _get_ocr_instance()
    except ImportError:
        return {
            "text": "",
            "confidence": 0.0,
            "word_count": 0,
            "low_confidence": True,
            "metadata": {"engine": "PADDLEOCR", "error": "paddleocr not installed"},
        }
    all_text_parts = []
    all_confidences = []
    page_references = []
    errors = []
    word_count = 0

    for path in image_paths:
        try:
            with Image.open(path) as image:
                image_width, image_height = image.size
            result = ocr.predict(path)
            if not result:
                all_text_parts.append("")
                page_references.append({"width": image_width, "height": image_height, "boxes": []})
                continue
            page_result = result[0]
            texts = page_result.get("rec_texts", [])
            scores = page_result.get("rec_scores", [])
            polygons = page_result.get("rec_polys", [])
            lines = [str(text) for text in texts if str(text).strip()]
            boxes = []
            for text, confidence, coordinates in zip(texts, scores, polygons):
                text = str(text)
                if not text.strip():
                    continue
                conf = float(confidence)
                all_confidences.append(conf)
                word_count += len(text.split())
                if coordinates is not None and len(coordinates):
                    xs = [float(point[0]) for point in coordinates]
                    ys = [float(point[1]) for point in coordinates]
                    boxes.append({
                        "text": text,
                        "x": min(xs),
                        "y": min(ys),
                        "width": max(xs) - min(xs),
                        "height": max(ys) - min(ys),
                        "confidence": conf * 100,
                    })
            all_text_parts.append("\n".join(lines))
            page_references.append({"width": image_width, "height": image_height, "boxes": boxes})
        except Exception as e:
            all_text_parts.append("")
            page_references.append({"width": 0, "height": 0, "boxes": []})
            errors.append(f"{type(e).__name__}: {e}")

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
            "page_references": page_references,
            "errors": errors,
        },
    }
