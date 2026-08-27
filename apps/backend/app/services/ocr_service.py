from typing import List, Dict, Any


def run_ocr_engine(engine: str, image_paths: List[str]) -> Dict[str, Any]:
    if engine == "TESSERACT":
        from app.ocr_engines.tesseract_engine import run_tesseract
        return run_tesseract(image_paths)
    elif engine == "PADDLEOCR":
        from app.ocr_engines.paddle_engine import run_paddle
        return run_paddle(image_paths)
    else:
        raise ValueError(f"Unknown local OCR engine: {engine}")


def run_ocr_with_fallback(initial_engine: str, image_paths: List[str]) -> tuple[Dict[str, Any], str]:
    """
    Runs OCR with automatic fallback.
    Returns (result, final_engine_used).
    Fallback chain: TESSERACT -> PADDLEOCR -> (caller handles LLM fallback)
    """
    engines_to_try = _build_fallback_chain(initial_engine)

    last_result = None
    last_engine = None
    for engine in engines_to_try:
        try:
            result = run_ocr_engine(engine, image_paths)
        except Exception:
            continue  # Continue to next engine on error
        last_result, last_engine = result, engine
        if not result.get("low_confidence", True):
            return result, engine
        # Continue to next engine on low confidence

    # All engines errored or stayed low-confidence; return the last attempt made
    if last_result is not None:
        return last_result, last_engine

    return {
        "text": "",
        "confidence": 0.0,
        "word_count": 0,
        "low_confidence": True,
        "metadata": {"engine": "FAILED", "error": "all engines failed"},
    }, "FAILED"


def _build_fallback_chain(initial_engine: str) -> List[str]:
    if initial_engine == "TESSERACT":
        return ["TESSERACT", "PADDLEOCR"]
    return [initial_engine]
