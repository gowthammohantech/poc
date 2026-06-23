from typing import List, Dict, Any
import cv2
import numpy as np


def analyze_complexity(page_paths: List[str]) -> Dict[str, Any]:
    if not page_paths:
        return {"score": 0, "level": "SIMPLE", "reasons": []}

    scores = []
    all_reasons = []
    for path in page_paths:
        score, reasons = _analyze_single_page(path)
        scores.append(score)
        all_reasons.extend(reasons)

    final_score = float(np.mean(scores))
    level = _score_to_level(final_score)
    return {
        "score": round(final_score, 1),
        "level": level,
        "reasons": list(set(all_reasons)),
    }


def _analyze_single_page(path: str) -> tuple[float, list[str]]:
    img = cv2.imread(path)
    if img is None:
        return 20.0, ["unreadable_page"]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    reasons = []
    score = 0.0

    # Table detection via horizontal/vertical line density
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=w * 0.3, maxLineGap=20)
    if lines is not None and len(lines) > 6:
        score += 20
        reasons.append("complex_table_structure")
    elif lines is not None and len(lines) > 2:
        score += 10
        reasons.append("simple_table_structure")

    # Text density (dark pixel ratio)
    _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    text_ratio = np.sum(binary > 0) / (h * w)
    if text_ratio > 0.15:
        score += 15
        reasons.append("high_text_density")
    elif text_ratio > 0.08:
        score += 8
        reasons.append("medium_text_density")

    # Multi-column detection
    col_score = _detect_columns(binary, w)
    if col_score > 1:
        score += 15 * min(col_score / 3, 1.0)
        reasons.append("multi_column_layout")

    # Low contrast / handwriting likelihood
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < 100:
        score += 20
        reasons.append("possible_handwriting_or_low_quality")
    elif laplacian_var < 300:
        score += 10
        reasons.append("moderate_image_quality")

    # Image complexity (many distinct regions)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    region_count = len(contours)
    if region_count > 200:
        score += 20
        reasons.append("many_distinct_regions")
    elif region_count > 80:
        score += 10
        reasons.append("moderate_regions")

    # Resolution penalty (very low res = harder)
    if w < 800 or h < 600:
        score += 10
        reasons.append("low_resolution")

    return min(score, 100.0), reasons


def _detect_columns(binary: np.ndarray, width: int) -> int:
    vertical_sum = np.sum(binary, axis=0)
    threshold = np.max(vertical_sum) * 0.05
    gaps = vertical_sum < threshold
    gap_regions = 0
    in_gap = False
    for v in gaps:
        if v and not in_gap:
            gap_regions += 1
            in_gap = True
        elif not v:
            in_gap = False
    return gap_regions


def _score_to_level(score: float) -> str:
    if score <= 40:
        return "SIMPLE"
    elif score <= 60:
        return "MEDIUM"
    elif score <= 80:
        return "HIGH"
    else:
        return "VERY_HIGH"
