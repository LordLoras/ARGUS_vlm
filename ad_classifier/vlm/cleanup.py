from __future__ import annotations

import json
from pathlib import Path

import httpx
import structlog

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.vlm.http import chat_completion
from ad_classifier.vlm.verifier import _extract_json, _normalize_chat_endpoint

_logger = structlog.get_logger(__name__)

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
        stream: bool = True,
    ) -> None:
        self._endpoint = _normalize_chat_endpoint(endpoint)
        self._model = model
        self._timeout = timeout_s
        self._max_tokens = max_tokens
        self._enable_thinking = enable_thinking
        self._stream = stream
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
            data = chat_completion(
                endpoint=self._endpoint,
                headers=self._headers,
                json=payload,
                timeout_s=self._timeout,
                stream=self._stream,
            )
            message = data["choices"][0]["message"]
            raw = message.get("content") or message.get("reasoning_content") or ""

            finish_reason = data.get("choices", [{}])[0].get("finish_reason", "")
            if not raw.strip():
                _logger.warning("ocr_cleanup_empty_response", finish_reason=finish_reason)
                return ocr_items
            if finish_reason == "length":
                _logger.warning(
                    "ocr_cleanup_max_tokens_reached",
                    finish_reason=finish_reason,
                    raw_length=len(raw),
                )
            elif finish_reason not in ("stop", "stop_sequence", "eos", ""):
                _logger.warning(
                    "ocr_cleanup_unexpected_finish",
                    finish_reason=finish_reason,
                    raw_length=len(raw),
                )

            return _parse_cleaned(raw, ocr_items)
        except httpx.RequestError as exc:
            _logger.warning("ocr_cleanup_disconnected", error=str(exc)[:300])
            return ocr_items
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:200] if exc.response is not None else ""
            _logger.warning(
                "ocr_cleanup_http_error",
                status=exc.response.status_code if exc.response is not None else None,
                body=body,
            )
            return ocr_items
        except Exception as exc:
            _logger.warning("ocr_cleanup_failed", error=str(exc)[:300])
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
