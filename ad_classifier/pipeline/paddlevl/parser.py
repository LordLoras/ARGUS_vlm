from __future__ import annotations

import base64
import io
import json
import mimetypes
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from ad_classifier._env import resolve_api_key
from ad_classifier.pipeline.ocr.models import FrameRef
from ad_classifier.pipeline.paddlevl.models import PaddleVLOutput
from ad_classifier.vlm.http import chat_completion


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, frame: FrameRef) -> PaddleVLOutput:
        """Run PaddleOCR-VL on a frame and return structured output."""


class MockPaddleVLParser(DocumentParser):
    """Returns a fixed PaddleVLOutput for use in tests."""

    def __init__(
        self,
        *,
        parsed: dict | None = None,
        raw_text: str | None = None,
        parse_ok: bool = True,
    ) -> None:
        self._parsed = parsed or {}
        self._raw_text = raw_text or json.dumps(self._parsed)
        self._parse_ok = parse_ok

    def parse(self, frame: FrameRef) -> PaddleVLOutput:
        return PaddleVLOutput(
            frame_index=frame.frame_index,
            time_ms=frame.time_ms,
            raw_text=self._raw_text,
            parsed=self._parsed if self._parse_ok else None,
            parse_ok=self._parse_ok,
            engine="mock_paddlevl",
        )


class PaddleVLParser(DocumentParser):
    """
    Shell adapter for PaddleX PaddleOCR-VL pipeline.

    Runs only when gating rules request it.  Captures stdout/stderr; parses
    JSON from stdout when available.  Fails gracefully so the pipeline can
    continue with PaddleOCR-only evidence.

    Command template variables: ``{image_path}``, ``{output_dir}``.
    """

    def __init__(
        self,
        command_template: str = (
            "paddlex --pipeline PaddleOCR-VL-native.yaml"
            " --input {image_path} --output {output_dir}"
        ),
        timeout_s: float = 60.0,
    ) -> None:
        self._command_template = command_template
        self._timeout_s = timeout_s

    def parse(self, frame: FrameRef) -> PaddleVLOutput:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = self._command_template.format(
                image_path=str(frame.path),
                output_dir=tmpdir,
            )
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_s,
                )
            except subprocess.TimeoutExpired:
                return PaddleVLOutput(
                    frame_index=frame.frame_index,
                    time_ms=frame.time_ms,
                    parse_ok=False,
                    stderr=f"timeout after {self._timeout_s}s",
                )
            except Exception as exc:
                return PaddleVLOutput(
                    frame_index=frame.frame_index,
                    time_ms=frame.time_ms,
                    parse_ok=False,
                    stderr=str(exc),
                )

            raw = proc.stdout.strip() or None
            parsed: dict | None = None
            parse_ok = False

            if raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        parsed = data
                        parse_ok = True
                    else:
                        # Try to find JSON in output dir
                        output_files = list(Path(tmpdir).glob("*.json"))
                        if output_files:
                            data = json.loads(output_files[0].read_text(encoding="utf-8"))
                            if isinstance(data, dict):
                                parsed = data
                                parse_ok = True
                except (json.JSONDecodeError, OSError):
                    pass

            return PaddleVLOutput(
                frame_index=frame.frame_index,
                time_ms=frame.time_ms,
                raw_text=raw,
                parsed=parsed,
                parse_ok=parse_ok,
                stderr=proc.stderr.strip() or None,
            )


class GLMOCRParser(DocumentParser):
    """
    OpenAI-compatible adapter for GLM-OCR served by a local or remote inference
    gateway.

    GLM-OCR does not provide Paddle-style boxes/confidence here; callers should
    store its text under engine="glm_ocr" and keep raw PaddleOCR as the
    grounded OCR source.
    """

    def __init__(
        self,
        *,
        endpoint: str = "http://127.0.0.1:5050/v1",
        model: str = "glm-ocr",
        api_key_env: str | None = None,
        prompt: str = "Text Recognition:",
        timeout_s: float = 120.0,
        max_retries: int = 1,
        retry_delay_s: float = 1.0,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        image_max_dim: int = 1024,
        stream: bool = True,
    ) -> None:
        if not endpoint.strip():
            raise ValueError("GLM-OCR endpoint must be provided")
        if not model.strip():
            raise ValueError("GLM-OCR model must be provided")
        self._endpoint = _normalize_chat_endpoint(endpoint)
        self._model = model
        self._prompt = prompt
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._retry_delay_s = retry_delay_s
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._image_max_dim = image_max_dim
        self._stream = stream
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = resolve_api_key(api_key_env)
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def parse(self, frame: FrameRef) -> PaddleVLOutput:
        try:
            encoded = _encode_image(frame.path, self._image_max_dim)
        except Exception as exc:
            return PaddleVLOutput(
                frame_index=frame.frame_index,
                time_ms=frame.time_ms,
                parse_ok=False,
                stderr=f"image encode failed: {exc}",
                engine="glm_ocr",
            )

        mime = mimetypes.guess_type(frame.path.name)[0] or "image/png"
        payload: dict = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        last_error = "no attempts made"
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                time.sleep(self._retry_delay_s)
            try:
                data = chat_completion(
                    endpoint=self._endpoint,
                    headers=self._headers,
                    json=payload,
                    timeout_s=self._timeout_s,
                    stream=self._stream,
                )
                raw = _extract_chat_text(data).strip()
                return PaddleVLOutput(
                    frame_index=frame.frame_index,
                    time_ms=frame.time_ms,
                    raw_text=raw,
                    parsed={"text": raw} if raw else None,
                    parse_ok=bool(raw),
                    stderr=None if raw else "empty GLM-OCR response",
                    engine="glm_ocr",
                )
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:500] if exc.response is not None else ""
                status = exc.response.status_code if exc.response is not None else "unknown"
                last_error = f"HTTP {status}: {body}"
            except httpx.RequestError as exc:
                last_error = str(exc)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_error = f"response parse failed: {exc}"

        return PaddleVLOutput(
            frame_index=frame.frame_index,
            time_ms=frame.time_ms,
            parse_ok=False,
            stderr=last_error,
            engine="glm_ocr",
        )


def _normalize_chat_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _encode_image(path: Path, max_dim: int) -> str:
    try:
        from PIL import Image as PILImage  # noqa: PLC0415

        img = PILImage.open(path)
        width, height = img.size
        if width > max_dim or height > max_dim:
            ratio = min(max_dim / width, max_dim / height)
            img = img.resize(
                (max(1, int(width * ratio)), max(1, int(height * ratio))),
                PILImage.LANCZOS,
            )
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return base64.b64encode(path.read_bytes()).decode("ascii")


def _extract_chat_text(data: dict) -> str:
    choice = data.get("choices", [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    text = choice.get("text")
    return text if isinstance(text, str) else ""
