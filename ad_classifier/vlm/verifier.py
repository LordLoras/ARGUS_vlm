from __future__ import annotations

import base64
import io
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from ad_classifier._env import resolve_api_key
from ad_classifier.pipeline.evidence.models import EvidenceBundle
from ad_classifier.pipeline.ocr.fine_print import fine_print_notice
from ad_classifier.vlm.http import chat_completion
from ad_classifier.vlm.models import VLMVerificationResult
from ad_classifier.vlm.prompt import get_prompt_version as _get_prompt_version
from ad_classifier.vlm.prompt import render_verifier_prompt
from ad_classifier.vlm.schema import vlm_response_format as _vlm_response_format

PROMPT_VERSION = _get_prompt_version()


class VLMVerifier(ABC):
    @abstractmethod
    def verify(self, bundle: EvidenceBundle) -> VLMVerificationResult: ...


class MockVLMVerifier(VLMVerifier):
    def __init__(self, result: VLMVerificationResult | None = None) -> None:
        self._result = result or VLMVerificationResult(
            primary_category="other",
            confidence=0.8,
            summary="mock verifier result",
        )

    def verify(self, bundle: EvidenceBundle) -> VLMVerificationResult:
        return self._result


_logger = structlog.get_logger(__name__)


def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*", text, re.DOTALL)
    if fenced:
        after = text[fenced.end() :]
        close = after.find("```")
        body = after[:close] if close != -1 else after
        start = body.find("{")
        if start != -1:
            depth = 0
            for i, ch in enumerate(body[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return body[start : i + 1]
        return body.strip()

    start = text.find("{")
    if start == -1:
        return text

    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


_MISSING = object()
_DOMAIN_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z]{2,})(?:/[^\s\"'<>)]*)?",
    re.IGNORECASE,
)
_ALLOWED_WEBSITE_TLDS = {
    "com",
    "net",
    "org",
    "co",
    "us",
    "tv",
    "io",
    "biz",
    "info",
    "edu",
    "gov",
    "app",
    "dev",
    "ai",
    "cloud",
    "me",
    "pro",
    "live",
    "today",
    "store",
    "blog",
    "shop",
    "online",
    "site",
    "tech",
    "xyz",
    "club",
    "media",
    "news",
    "world",
    "social",
}


def _parse_vlm_content(raw: str) -> VLMVerificationResult:
    json_str = _extract_json(raw)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as exc:
        _logger.warning("vlm_parse_failure", error=str(exc), raw_preview=raw[:200])
        return _salvage_vlm_result(json_str, str(exc))
    return VLMVerificationResult.model_validate(parsed)


def _salvage_vlm_result(raw: str, error: str) -> VLMVerificationResult:
    """Recover usable fields when the inference engine emits malformed nested JSON."""
    data: dict[str, object] = {}
    for key in (
        "primary_category",
        "iab_category",
        "iab_content_categories",
        "confidence",
        "ocr_quality",
        "evidence",
        "conflicts",
        "summary",
    ):
        value = _extract_key_value(raw, key)
        if value is not _MISSING:
            data[key] = _clean_placeholders(value)

    marketing_match = re.search(r'"marketing_entities"\s*:', raw)
    if marketing_match:
        marketing_start = marketing_match.end()
        marketing: dict[str, object] = {}
        for key in (
            "brand",
            "promotion_name",
            "products",
            "prices",
            "offers",
            "ctas",
            "social_proof",
            "disclaimers",
            "creative_format",
            "contact_points",
            "advertiser",
            "landing_page",
            "creative_attributes",
            "campaign_suggestions",
        ):
            value = _extract_key_value(raw, key, start=marketing_start)
            if value is not _MISSING:
                marketing[key] = _clean_placeholders(value)

        offer_terms_match = re.search(r'"offer_terms"\s*:', raw[marketing_start:])
        if offer_terms_match:
            offer_terms_start = marketing_start + offer_terms_match.end()
            offer_terms: dict[str, object] = {}
            for key in (
                "promo_codes",
                "financing",
                "trial_terms",
                "guarantees",
                "scarcity_signals",
                "urgency_signals",
            ):
                value = _extract_key_value(raw, key, start=offer_terms_start)
                if value is not _MISSING:
                    offer_terms[key] = _clean_placeholders(value)
            if offer_terms:
                marketing["offer_terms"] = offer_terms

        contact_points = marketing.get("contact_points")
        if isinstance(contact_points, dict):
            contact_points["websites"] = [
                website_normalized
                for website in contact_points.get("websites", [])
                if isinstance(website, dict)
                for website_normalized in [_normalize_website_dict(website)]
                if website_normalized is not None
            ]

        if marketing:
            data["marketing_entities"] = marketing

    try:
        result = VLMVerificationResult.model_validate(data)
    except ValueError:
        return VLMVerificationResult.parse_failure(raw, error)

    result.parse_ok = False
    result.raw_response = raw
    result.parse_error = f"salvaged malformed JSON: {error}"
    return result


def _extract_key_value(raw: str, key: str, *, start: int = 0):
    match = re.search(rf'"{re.escape(key)}"\s*:', raw[start:])
    if not match:
        return _MISSING
    value_start = start + match.end()
    while value_start < len(raw) and raw[value_start].isspace():
        value_start += 1
    if value_start >= len(raw):
        return _MISSING

    first = raw[value_start]
    if first in "{[":
        value_text = _balanced_json_value(raw, value_start)
        if value_text is None:
            return _MISSING
        try:
            return json.loads(value_text)
        except json.JSONDecodeError:
            return _MISSING

    try:
        value, _idx = json.JSONDecoder().raw_decode(raw[value_start:])
        return value
    except json.JSONDecodeError:
        return _MISSING


def _balanced_json_value(raw: str, start: int) -> str | None:
    stack: list[str] = []
    in_string = False
    escape = False
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack or ch != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return raw[start : idx + 1]
    return None


def _clean_placeholders(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {"null", "none", "n/a"} or stripped == "string":
            return None
        return value
    if isinstance(value, list):
        cleaned = [_clean_placeholders(item) for item in value]
        return [item for item in cleaned if item is not None]
    if isinstance(value, dict):
        return {key: _clean_placeholders(item) for key, item in value.items()}
    return value


def _normalize_website_dict(website: dict[str, object]) -> dict[str, object] | None:
    for key in ("url", "display_text", "domain"):
        candidate = _domain_candidate(website.get(key))
        if candidate is None:
            continue
        normalized = dict(website)
        normalized["url"] = candidate["url"]
        normalized["domain"] = candidate["domain"]
        if not normalized.get("display_text"):
            normalized["display_text"] = candidate["display_text"]
        return normalized
    return None


def _domain_candidate(value: object) -> dict[str, str] | None:
    if not isinstance(value, str):
        return None
    text = value.strip().strip(".,;:")
    if text.lower() in {"", "null", "none", "n/a", "string"}:
        return None

    match = _DOMAIN_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(0).rstrip(".,;:")
    url = raw if raw.lower().startswith(("http://", "https://")) else f"https://{raw}"
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain or "." not in domain:
        return None
    tld = domain.rsplit(".", 1)[-1]
    if tld not in _ALLOWED_WEBSITE_TLDS:
        return None

    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return {
        "url": f"{parsed.scheme}://{domain}{path}{query}{fragment}",
        "domain": domain,
        "display_text": raw,
    }


def _looks_like_url_or_domain(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return _domain_candidate(value) is not None


def _encode_image(path: Path, max_dim: int = 512) -> str:
    try:
        from PIL import Image as _PILImage

        img = _PILImage.open(path)
        w, h = img.size
        if w > max_dim or h > max_dim:
            ratio = min(max_dim / w, max_dim / h)
            img = img.resize((int(w * ratio), int(h * ratio)), _PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        data = path.read_bytes()
        return base64.b64encode(data).decode("ascii")


def _normalize_chat_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _dedupe_ocr_text(ocr_texts: list[str], threshold: float = 0.65) -> list[bool]:
    if not ocr_texts:
        return []
    compacted = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in ocr_texts]
    keep: list[bool] = [True] * len(ocr_texts)
    surrogate: list[int | None] = [None] * len(ocr_texts)
    for i in range(len(compacted)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(compacted)):
            if not keep[j]:
                continue
            if _text_overlap(compacted[i], compacted[j]) >= threshold:
                if len(ocr_texts[j]) > len(ocr_texts[i]):
                    keep[i] = False
                    surrogate[j] = i
                    break
                else:
                    keep[j] = False
                    surrogate[j] = i
                    continue
    return keep


def _text_overlap(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _build_content(bundle: EvidenceBundle, image_max_dim: int = 512) -> list[dict]:
    parts: list[dict] = []

    text_parts: list[str] = []
    text_parts.append(f"Ad ID: {bundle.ad_id}")
    if bundle.metadata:
        text_parts.append(f"Metadata: {json.dumps(bundle.metadata)}")
    if bundle.full_transcript.text:
        text_parts.append(f"Full transcript:\n{bundle.full_transcript.text}")

    all_ocr = []
    for fs in bundle.frame_summaries:
        ocr_text = _format_ocr_items(fs.ocr_items)
        all_ocr.append(ocr_text)
    keep = _dedupe_ocr_text(all_ocr)

    for idx, fs in enumerate(bundle.frame_summaries):
        seg = f"[Frame {fs.frame_index} @ {fs.time_ms}ms]"
        if keep[idx]:
            ocr_text = all_ocr[idx]
            if ocr_text:
                seg += f"\nOCR: {ocr_text}"
        else:
            seg += "\nOCR: (repeats above)"
        if fs.paddlevl_output and fs.paddlevl_output.parsed:
            pv_text = fs.paddlevl_output.parsed.get("text", "")
            if pv_text:
                label = fs.paddlevl_output.engine or "paddlevl"
                seg += f"\nDocumentOCR[{label}]: {pv_text}"
        if fs.fine_print_ocr_items:
            fine_print = fine_print_notice(fs.fine_print_ocr_items)
            if fine_print:
                seg += (
                    "\nFinePrintOCR: small/dense legal text tucked away. Use only for "
                    "expiry, APR/financing terms, exclusions, eligibility, fees, or legal "
                    f"disclaimers; do not infer brand/product/category from it: {fine_print}"
                )
        if fs.broadcast_overlay_ocr_items:
            seg += (
                "\nBroadcastOverlayOCR: non-ad TV/weather/radar overlay detected and "
                "excluded from marketing/category extraction. Ignore the matching visible "
                "corner overlay unless the same signal also appears in the main ad creative."
            )
        if fs.transcript_nearby:
            seg += f"\nTranscript: {' | '.join(s.text for s in fs.transcript_nearby)}"
        text_parts.append(seg)

    if bundle.rules_triggered:
        rule_lines = [
            f"  - rule={r.rule_id} severity={r.severity} category={r.category or ''} text={r.evidence_text!r}"
            for r in bundle.rules_triggered
        ]
        text_parts.append("Rule triggers:\n" + "\n".join(rule_lines))

    parts.append({"type": "text", "text": "\n\n".join(text_parts)})

    for img_path in bundle.frame_image_paths:
        path = Path(img_path)
        if not path.exists():
            continue
        suffix = path.suffix.lower().lstrip(".")
        mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
        encoded = _encode_image(path, max_dim=image_max_dim)
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            }
        )

    return parts


def _format_ocr_items(items) -> str:
    by_engine: dict[str, list[str]] = {}
    for item in items:
        if item.text:
            by_engine.setdefault(item.engine or "ocr", []).append(item.text)
    chunks: list[str] = []
    for engine, texts in by_engine.items():
        label = "ocr" if engine in {"paddleocr", "mock"} else engine
        chunks.append(f"{label}: {' '.join(texts)}")
    return " | ".join(chunks)


class HTTPVLMVerifier(VLMVerifier):
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key_env: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        retry_delay_s: float = 2.0,
        temperature: float,
        max_tokens: int,
        prompt_override: str | None = None,
        prompt_profile: str = "standard",
        enable_thinking: bool = False,
        response_format: str = "json_object",
        image_max_dim: int = 512,
        stream: bool = True,
        knowledge_manager: Any | None = None,
    ) -> None:
        if not endpoint.strip():
            raise ValueError("VLM endpoint must be provided")
        if not model.strip():
            raise ValueError("VLM model must be provided")
        self._endpoint = _normalize_chat_endpoint(endpoint)
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._retry_delay_s = retry_delay_s
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._prompt_profile = prompt_profile
        self._enable_thinking = enable_thinking
        self._response_format = response_format
        self._image_max_dim = image_max_dim
        self._stream = stream
        self._system_prompt = prompt_override or render_verifier_prompt(
            prompt_profile=prompt_profile,
            knowledge_manager=knowledge_manager,
        )

        api_key = resolve_api_key(api_key_env)
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def verify(self, bundle: EvidenceBundle) -> VLMVerificationResult:
        content = _build_content(bundle, image_max_dim=self._image_max_dim)
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "response_format": _vlm_response_format(self._response_format),
        }
        if self._enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": True}
        else:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        last_error: str = "no attempts made"
        raw = ""
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
                message = data["choices"][0]["message"]
                raw = message.get("content") or message.get("reasoning_content") or ""

                finish_reason = ""
                choice = data.get("choices", [{}])[0]
                finish_reason = choice.get("finish_reason", "")

                if finish_reason == "length":
                    _logger.warning(
                        "vlm_max_tokens_reached",
                        finish_reason=finish_reason,
                        attempt=attempt + 1,
                        max_tokens=self._max_tokens,
                        raw_length=len(raw),
                    )
                elif finish_reason not in ("stop", "stop_sequence", "eos", ""):
                    _logger.warning(
                        "vlm_unexpected_finish",
                        finish_reason=finish_reason,
                        attempt=attempt + 1,
                        raw_length=len(raw),
                    )

                if not raw.strip():
                    last_error = (
                        f"VLM returned empty response on attempt {attempt + 1} "
                        f"(finish_reason={finish_reason})"
                    )
                    _logger.warning(
                        "vlm_empty_response", attempt=attempt + 1, finish_reason=finish_reason
                    )
                    continue

                _logger.info(
                    "vlm_response_ok",
                    attempt=attempt + 1,
                    finish_reason=finish_reason,
                    raw_length=len(raw),
                )
                return _parse_vlm_content(raw)
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:1000] if exc.response is not None else ""
                last_error = (
                    f"HTTP error on attempt {attempt + 1}: "
                    f"status={exc.response.status_code if exc.response is not None else 'unknown'} "
                    f"body={body!r}"
                )
                _logger.warning(
                    "vlm_http_error",
                    attempt=attempt + 1,
                    status=exc.response.status_code if exc.response is not None else None,
                    body=body[:200],
                )
            except httpx.RequestError as exc:
                last_error = f"HTTP error on attempt {attempt + 1}: {exc}"
                _logger.warning("vlm_request_error", attempt=attempt + 1, error=str(exc)[:300])
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                raw_text = raw if "raw" in dir() else ""
                return VLMVerificationResult.parse_failure(raw_text, str(exc))

        return VLMVerificationResult.parse_failure("", last_error)
