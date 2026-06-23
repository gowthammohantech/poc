import os
import math
from pathlib import Path
from typing import Tuple
import cv2
import numpy as np

TESSDATA_PREFIX = os.getenv("TESSDATA_PREFIX", "/opt/homebrew/share/tessdata")


def preprocess_image(input_path: str, output_path: str) -> Tuple[int, int]:
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Cannot read image: {input_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
    deskewed = _deskew(denoised)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(deskewed)
    _, thresholded = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    h, w = thresholded.shape
    cv2.imwrite(output_path, thresholded)
    return w, h


def _deskew(gray: np.ndarray) -> np.ndarray:
    try:
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
        if lines is None or len(lines) < 3:
            return gray

        angles = []
        for line in lines[:20]:
            rho, theta = line[0]
            angle = (theta * 180 / np.pi) - 90
            if abs(angle) < 45:
                angles.append(angle)

        if not angles:
            return gray

        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.5:
            return gray

        h, w = gray.shape
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REPLICATE)
        return rotated
    except Exception:
        return gray


def preprocess_pages(page_paths: list[str], preprocessed_dir: Path) -> list[str]:
    preprocessed_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for page_path in page_paths:
        filename = Path(page_path).name
        out_path = str(preprocessed_dir / filename)
        try:
            preprocess_image(page_path, out_path)
        except Exception:
            import shutil
            shutil.copy2(page_path, out_path)
        results.append(out_path)
    return results
