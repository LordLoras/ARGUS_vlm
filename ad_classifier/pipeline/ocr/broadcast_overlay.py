from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ad_classifier.pipeline.ocr.models import OCRItem

_BROADCAST_CONTEXT_PATTERN = re.compile(
    r"\b("
    r"flash\s+flood|flood\s+warning|live\s*radar|radar|tornado|"
    r"severe\s+thunderstorm|weather\s+alert|weather\s+warning|"
    r"washed\s+out|road\s+surfaces|electrical\s+wires?|"
    r"swiftly\s+moving\s+water|inches\s+of\s+water|williamson"
    r")\b",
    re.IGNORECASE,
)


def split_broadcast_overlay(
    items: list[OCRItem],
    *,
    frame_path: Path | None = None,
) -> tuple[list[OCRItem], list[OCRItem]]:
    """Separate TV broadcast/weather overlays from ad creative OCR.

    The detector is intentionally conservative: it only activates when a
    strong broadcast/weather term appears inside the small upper-left TV
    overlay region, then excludes the whole nearby overlay block for that
    frame. This keeps normal ad logos intact unless the frame clearly has a
    broadcast crawl/radar/weather graphic.
    """

    frame_size = _image_size(frame_path) if frame_path else None
    if frame_size is None or not _has_broadcast_context(items, frame_size):
        return items, []

    main: list[OCRItem] = []
    overlay: list[OCRItem] = []
    for item in items:
        target = overlay if _in_upper_left_overlay(item, frame_size) else main
        target.append(item)
    return main, overlay


def _has_broadcast_context(
    items: list[OCRItem],
    frame_size: tuple[int, int],
) -> bool:
    return any(
        _BROADCAST_CONTEXT_PATTERN.search(_clean_text(item.text))
        and _in_upper_left_overlay(item, frame_size)
        for item in items
    )


def _in_upper_left_overlay(
    item: OCRItem,
    frame_size: tuple[int, int],
) -> bool:
    metrics = _bbox_metrics(item.bbox)
    if metrics is None:
        return False

    frame_width = float(frame_size[0])
    frame_height = float(frame_size[1])
    if frame_width <= 0 or frame_height <= 0:
        return False

    x_min = metrics["x_min"]
    x_max = metrics["x_max"]
    y_min = metrics["y_min"]
    height = metrics["height"]

    return (
        x_min <= frame_width * 0.34
        and x_max <= frame_width * 0.38
        and y_min <= frame_height * 0.24
        and height <= max(28.0, frame_height * 0.075)
    )


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _bbox_metrics(bbox: list[float] | None) -> dict[str, float] | None:
    if not bbox or len(bbox) < 4:
        return None
    xs = [float(value) for value in bbox[0::2]]
    ys = [float(value) for value in bbox[1::2]]
    return {
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "height": max(ys) - min(ys),
    }


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
