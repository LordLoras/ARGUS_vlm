from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def compute_blank_std(path: Path) -> float:
    """Grayscale std-dev of the frame. Values near 0 indicate a near-blank/solid frame."""
    with Image.open(path) as img:
        arr = np.asarray(img.convert("L"), dtype=np.float32)
        return float(arr.std())


def compute_blur_score(path: Path) -> float:
    """Laplacian variance of the frame. Higher = sharper. Uses cv2 when available."""
    try:
        import cv2  # noqa: PLC0415

        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return 0.0
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except ImportError:
        from PIL import ImageFilter  # noqa: PLC0415

        with Image.open(path) as img:
            edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
            return float(np.asarray(edges, dtype=np.float32).var())


def compute_phash(path: Path) -> str:
    from ad_classifier.dedup.phash import image_phash  # noqa: PLC0415

    return image_phash(path)


def compute_pixel_diff(path_a: Path, path_b: Path, size: tuple[int, int] = (64, 64)) -> float:
    """Mean absolute pixel difference (0..1) between two frames, resized for speed."""
    with Image.open(path_a) as ia, Image.open(path_b) as ib:
        a = np.asarray(ia.convert("RGB").resize(size), dtype=np.float32) / 255.0
        b = np.asarray(ib.convert("RGB").resize(size), dtype=np.float32) / 255.0
        return float(np.abs(a - b).mean())
