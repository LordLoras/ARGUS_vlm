from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ad_classifier.pipeline.ocr.models import OCRItem

_LEGAL_PATTERN = re.compile(
    r"\b("
    r"apr|financ(?:e|ing)|qualified buyers?|eligib(?:le|ility)|excludes?|"
    r"must take|delivery by|offer (?:ends|expires)|tax|title|license|fees?|"
    r"dealer installed|see dealer|terms?|conditions?|subject to|not all|lease|"
    r"professional driver|closed course|do not attempt|trademark|registered"
    r")\b",
    re.IGNORECASE,
)
_STRONG_FINE_PRINT_PATTERN = re.compile(
    r"\b("
    r"qualified buyers?|eligib(?:le|ility)|excludes?|must take|delivery by|"
    r"offer (?:ends|expires)|tax|title|license|fees?|see dealer|terms?|"
    r"conditions?|subject to|not all|professional driver|closed course|"
    r"do not attempt|trademark|registered"
    r")\b",
    re.IGNORECASE,
)


def split_fine_print(
    items: list[OCRItem],
    *,
    frame_path: Path | None = None,
) -> tuple[list[OCRItem], list[OCRItem]]:
    frame_size = _image_size(frame_path) if frame_path else None
    main: list[OCRItem] = []
    fine_print: list[OCRItem] = []
    for item in items:
        target = fine_print if is_fine_print(item, frame_size=frame_size) else main
        target.append(item)
    return main, fine_print


def is_fine_print(
    item: OCRItem,
    *,
    frame_size: tuple[int, int] | None = None,
) -> bool:
    text = re.sub(r"\s+", " ", item.text or "").strip()
    if not text:
        return False

    metrics = _bbox_metrics(item.bbox, frame_size)
    legal = bool(_LEGAL_PATTERN.search(text))
    strong_fine_print = bool(_STRONG_FINE_PRINT_PATTERN.search(text))
    long_text = len(text) >= 70 or len(text.split()) >= 10
    very_long_text = len(text) >= 100 or len(text.split()) >= 14

    if metrics is None:
        return strong_fine_print and very_long_text

    height = metrics["height"]
    width = metrics["width"]
    frame_width = metrics.get("frame_width")
    frame_height = metrics.get("frame_height")
    height_ratio = height / frame_height if frame_height else None
    y_min_ratio = metrics["y_min"] / frame_height if frame_height else None
    width_ratio = width / frame_width if frame_width else None

    small_absolute = height <= 16
    small_relative = height_ratio is not None and height_ratio <= 0.038
    small = small_absolute or small_relative
    bottom_band = y_min_ratio is not None and y_min_ratio >= 0.72
    dense_line = (
        width_ratio is not None
        and width_ratio >= 0.45
        and len(text) >= 36
        and (small_relative or small_absolute)
    )

    return (small and (legal or long_text)) or (
        bottom_band and (legal or long_text) and dense_line
    )


def fine_print_notice(items: list[OCRItem], *, max_chars: int = 420) -> str:
    snippets: list[str] = []
    for item in items:
        text = re.sub(r"\s+", " ", item.text or "").strip()
        if not text:
            continue
        if _LEGAL_PATTERN.search(text) or len(text) >= 40:
            snippets.append(text)
    joined = " ".join(snippets)
    if len(joined) <= max_chars:
        return joined
    return joined[:max_chars].rsplit(" ", 1)[0].strip(" ,;:-") + "..."


def _bbox_metrics(
    bbox: list[float] | None,
    frame_size: tuple[int, int] | None,
) -> dict[str, float] | None:
    if not bbox or len(bbox) < 4:
        return None
    xs = [float(value) for value in bbox[0::2]]
    ys = [float(value) for value in bbox[1::2]]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    metrics = {
        "width": width,
        "height": height,
        "x_min": min(xs),
        "y_min": min(ys),
    }
    if frame_size:
        metrics["frame_width"] = float(frame_size[0])
        metrics["frame_height"] = float(frame_size[1])
    return metrics


@lru_cache(maxsize=256)
def _image_size(path: Path | None) -> tuple[int, int] | None:
    if path is None or not path.exists():
        return None
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return None
