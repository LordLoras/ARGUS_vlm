from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.vlm.verifier import _extract_json

_CLEANUP_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "ocr_cleanup.txt"


def _build_cleanup_payload(
    ocr_items: list[OCRItem],
    transcript: WhisperTranscript,
) -> list[dict]:
    lines: list[str] = []
    lines.append("Raw OCR frames:")
    by_frame: dict[int, list[OCRItem]] = {}
    for item in ocr_items:
        by_frame.setdefault(item.frame_index, []).append(item)
    for fidx in sorted(by_frame):
        items = by_frame[fidx]
        text = " ".join(i.text for i in items if i.text)
        conf = max((i.confidence for i in items if i.confidence is not None), default=0.0)
        lines.append(f"Frame {fidx} ({items[0].time_ms}ms, conf={conf:.2f}): {text}")
    if transcript.text:
        lines.append(f"\nTranscript: {transcript.text}")
    return [{"type": "text", "text": "\n".join(lines)}]


class OCRCleanupPass:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        max_tokens: int = 2048,
        enable_thinking: bool = False,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") + "/chat/completions"
        if not self._endpoint.endswith("/chat/completions"):
            self._endpoint = endpoint.rstrip("/")
            if not self._endpoint.endswith("/v1"):
                self._endpoint += "/v1"
            self._endpoint += "/chat/completions"
        self._model = model
        self._timeout = timeout_s
        self._max_tokens = max_tokens
        self._enable_thinking = enable_thinking
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._prompt = _CLEANUP_PROMPT_PATH.read_text(encoding="utf-8")

    def run(
        self,
        ocr_items: list[OCRItem],
        transcript: WhisperTranscript,
    ) -> list[OCRItem]:
        if not ocr_items:
            return ocr_items

        content = _build_cleanup_payload(ocr_items, transcript)
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.0,
            "max_tokens": self._max_tokens,
        }
        if self._enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": True}

        try:
            resp = httpx.post(
                self._endpoint,
                headers=self._headers,
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            raw = message.get("content") or message.get("reasoning_content") or ""
            return _parse_cleaned(raw, ocr_items)
        except Exception:
            return ocr_items


def _parse_cleaned(raw: str, original: list[OCRItem]) -> list[OCRItem]:
    json_str = _extract_json(raw)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return original

    cleaned = parsed.get("cleaned_frames", [])
    if not cleaned or not isinstance(cleaned, list):
        return original

    original_by_frame: dict[int, list[OCRItem]] = {}
    for item in original:
        original_by_frame.setdefault(item.frame_index, []).append(item)

    result: list[OCRItem] = []
    seen_frames: set[int] = set()
    for entry in cleaned:
        fidx = entry.get("frame_index")
        text = entry.get("text", "")
        if not isinstance(fidx, int) or not text:
            continue
        source_items = original_by_frame.get(fidx, [])
        if not source_items:
            continue
        src = source_items[0]
        result.append(
            OCRItem(
                frame_index=fidx,
                time_ms=entry.get("time_ms", src.time_ms),
                text=text,
                confidence=entry.get("confidence", src.confidence),
                engine="vlm_corrected",
                bbox=src.bbox,
            )
        )
        seen_frames.add(fidx)

    for fidx in sorted(original_by_frame):
        if fidx not in seen_frames:
            result.extend(original_by_frame[fidx])

    result.sort(key=lambda x: (x.frame_index, x.time_ms))
    return result
