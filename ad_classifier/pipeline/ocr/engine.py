from __future__ import annotations

import sys
from abc import ABC, abstractmethod

from ad_classifier.pipeline.ocr.models import FrameRef, OCRItem


class OCREngine(ABC):
    @abstractmethod
    def extract(self, frame: FrameRef) -> list[OCRItem]:
        """Extract OCR items from a single frame. Never normalises raw text."""


class MockOCREngine(OCREngine):
    """Returns a fixed list of OCRItems, re-tagged with the given frame's coords."""

    def __init__(self, items: list[OCRItem] | None = None) -> None:
        self._items = items or []

    def extract(self, frame: FrameRef) -> list[OCRItem]:
        return [
            OCRItem(
                frame_index=frame.frame_index,
                time_ms=frame.time_ms,
                text=item.text,
                confidence=item.confidence,
                bbox=item.bbox,
                engine="mock",
            )
            for item in self._items
        ]


class PaddleOCREngine(OCREngine):
    """
    PaddleOCR-based OCR engine.  Lazy-imports PaddleOCR so tests run without it.
    Always defaults to CPU on Windows (AMD GPU unsupported by Paddle).
    """

    def __init__(self, device: str = "cpu", lang: str = "en") -> None:
        self._device = device
        self._lang = lang
        self._ocr = None  # initialised on first use

    def _get_ocr(self):
        if self._ocr is not None:
            return self._ocr
        try:
            import paddle  # noqa: PLC0415
            from paddleocr import PaddleOCR  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "PaddleOCR is not installed. Install with:\n"
                "  pip install paddlepaddle paddleocr\n"
                "Note: use the CPU wheel on Windows AMD GPU systems."
            ) from exc

        # Windows AMD GPU is not supported by PaddlePaddle; force CPU.
        use_gpu = self._device != "cpu" and sys.platform != "win32"
        if use_gpu:
            try:
                paddle.set_device(self._device)
            except Exception:
                use_gpu = False  # best-effort; fall back to CPU

        self._ocr = PaddleOCR(
            use_angle_cls=False,
            lang=self._lang,
            use_gpu=use_gpu,
            show_log=False,
        )
        return self._ocr

    def extract(self, frame: FrameRef) -> list[OCRItem]:
        ocr = self._get_ocr()
        raw = ocr.ocr(str(frame.path), cls=False)
        items: list[OCRItem] = []
        if not raw:
            return items
        for page in raw:
            if not page:
                continue
            for detection in page:
                if not isinstance(detection, (list, tuple)) or len(detection) < 2:
                    continue
                bbox_raw, text_conf = detection[0], detection[1]
                if not isinstance(text_conf, (list, tuple)) or len(text_conf) < 2:
                    continue
                text = str(text_conf[0] or "")
                conf_raw = text_conf[1]
                conf = float(conf_raw) if conf_raw is not None else None
                bbox: list[float] | None = None
                if isinstance(bbox_raw, (list, tuple)):
                    flat: list[float] = []
                    for pt in bbox_raw:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            flat.extend([float(pt[0]), float(pt[1])])
                    bbox = flat if flat else None
                items.append(
                    OCRItem(
                        frame_index=frame.frame_index,
                        time_ms=frame.time_ms,
                        text=text,
                        confidence=conf,
                        bbox=bbox,
                        engine="paddleocr",
                    )
                )
        return items
