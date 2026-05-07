from __future__ import annotations

import base64
import json
import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from ad_classifier.pipeline.evidence.models import EvidenceBundle
from ad_classifier.vlm.models import VLMVerificationResult
from ad_classifier.vlm.prompt import render_verifier_prompt


class VLMVerifier(ABC):
    @abstractmethod
    def verify(self, bundle: EvidenceBundle) -> VLMVerificationResult: ...


class MockVLMVerifier(VLMVerifier):
    def __init__(self, result: VLMVerificationResult | None = None) -> None:
        self._result = result or VLMVerificationResult(
            primary_category="other",
            confidence=0.8,
            decision="allow",
            needs_human_review=False,
            summary="mock verifier result",
        )

    def verify(self, bundle: EvidenceBundle) -> VLMVerificationResult:
        return self._result


def _extract_json(text: str) -> str:
    # Strip markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    # Find the outermost JSON object
    start = text.find("{")
    if start == -1:
        return text
    # Walk forward tracking brace depth
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _encode_image(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


def _normalize_chat_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _build_content(bundle: EvidenceBundle) -> list[dict]:
    parts: list[dict] = []

    text_parts: list[str] = []
    text_parts.append(f"Ad ID: {bundle.ad_id}")
    if bundle.metadata:
        text_parts.append(f"Metadata: {json.dumps(bundle.metadata)}")
    if bundle.full_transcript.text:
        text_parts.append(f"Full transcript:\n{bundle.full_transcript.text}")

    for fs in bundle.frame_summaries:
        seg = f"[Frame {fs.frame_index} @ {fs.time_ms}ms]"
        ocr_text = " ".join(item.text for item in fs.ocr_items if item.text)
        if ocr_text:
            seg += f"\nOCR: {ocr_text}"
        if fs.paddlevl_output and fs.paddlevl_output.parsed:
            pv_text = fs.paddlevl_output.parsed.get("text", "")
            if pv_text:
                seg += f"\nPaddleVL: {pv_text}"
        if fs.transcript_nearby:
            seg += f"\nTranscript: {' | '.join(s.text for s in fs.transcript_nearby)}"
        text_parts.append(seg)

    if bundle.rules_triggered:
        rule_lines = [
            f"  - rule={r.rule_id} severity={r.severity} label={r.risk_label or r.category or ''} text={r.evidence_text!r}"
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
        encoded = _encode_image(path)
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            }
        )

    return parts


def _vlm_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ad_verification_result",
            "schema": {
                "type": "object",
                "properties": {
                    "primary_category": {"type": "string"},
                    "risk_labels": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "decision": {
                        "type": "string",
                        "enum": ["allow", "flag", "review"],
                    },
                    "needs_human_review": {"type": "boolean"},
                    "ocr_quality": {
                        "type": "object",
                        "properties": {
                            "overall": {
                                "type": "string",
                                "enum": ["good", "mixed", "poor"],
                            },
                            "possible_errors": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "time_ms": {"type": "integer"},
                                        "frame_index": {"type": "integer"},
                                        "raw_ocr": {"type": "string"},
                                        "corrected_text": {"type": "string"},
                                        "confidence": {
                                            "anyOf": [
                                                {"type": "number", "minimum": 0, "maximum": 1},
                                                {"type": "null"},
                                            ]
                                        },
                                        "reason": {"type": "string"},
                                    },
                                    "required": [
                                        "time_ms",
                                        "frame_index",
                                        "raw_ocr",
                                        "corrected_text",
                                        "confidence",
                                        "reason",
                                    ],
                                },
                            },
                            "missed_text": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "time_ms": {"type": "integer"},
                                        "frame_index": {"type": "integer"},
                                        "text": {"type": "string"},
                                        "location": {
                                            "anyOf": [{"type": "string"}, {"type": "null"}]
                                        },
                                        "confidence": {
                                            "anyOf": [
                                                {"type": "number", "minimum": 0, "maximum": 1},
                                                {"type": "null"},
                                            ]
                                        },
                                        "reason": {"type": "string"},
                                    },
                                    "required": [
                                        "time_ms",
                                        "frame_index",
                                        "text",
                                        "location",
                                        "confidence",
                                        "reason",
                                    ],
                                },
                            },
                        },
                        "required": ["overall", "possible_errors", "missed_text"],
                    },
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "time_ms": {"type": "integer"},
                                "frame_index": {"type": "integer"},
                                "source": {"type": "string"},
                                "text": {"type": "string"},
                                "reason": {"type": "string"},
                                "confidence": {
                                    "anyOf": [
                                        {"type": "number", "minimum": 0, "maximum": 1},
                                        {"type": "null"},
                                    ]
                                },
                            },
                            "required": [
                                "time_ms",
                                "frame_index",
                                "source",
                                "text",
                                "reason",
                                "confidence",
                            ],
                        },
                    },
                    "marketing_entities": {
                        "type": "object",
                        "properties": {
                            "brand": {
                                "type": "object",
                                "properties": {
                                    "name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                    "logo_present": {"type": "boolean"},
                                    "logo_evidence": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "time_ms": {"type": "integer"},
                                                "frame_index": {"type": "integer"},
                                                "reason": {"type": "string"},
                                            },
                                            "required": ["time_ms", "frame_index", "reason"],
                                        },
                                    },
                                    "tagline": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                },
                                "required": [
                                    "name",
                                    "logo_present",
                                    "logo_evidence",
                                    "tagline",
                                ],
                            },
                            "products": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "prices": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "amount": {"type": "number"},
                                        "currency": {
                                            "anyOf": [{"type": "string"}, {"type": "null"}]
                                        },
                                        "frame_index": {"type": "integer"},
                                        "time_ms": {"type": "integer"},
                                        "discounted_from": {
                                            "anyOf": [{"type": "number"}, {"type": "null"}]
                                        },
                                        "discount_pct": {
                                            "anyOf": [{"type": "number"}, {"type": "null"}]
                                        },
                                    },
                                    "required": [
                                        "amount",
                                        "currency",
                                        "frame_index",
                                        "time_ms",
                                        "discounted_from",
                                        "discount_pct",
                                    ],
                                },
                            },
                            "offers": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string"},
                                        "value": {"type": "string"},
                                        "expiry_text": {
                                            "anyOf": [{"type": "string"}, {"type": "null"}]
                                        },
                                        "expiry_resolved": {
                                            "anyOf": [{"type": "string"}, {"type": "null"}]
                                        },
                                        "promo_code": {
                                            "anyOf": [{"type": "string"}, {"type": "null"}]
                                        },
                                        "scarcity_signals": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "urgency_signals": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": [
                                        "type",
                                        "value",
                                        "expiry_text",
                                        "expiry_resolved",
                                        "promo_code",
                                        "scarcity_signals",
                                        "urgency_signals",
                                    ],
                                },
                            },
                            "ctas": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "destination_hint": {
                                            "anyOf": [{"type": "string"}, {"type": "null"}]
                                        },
                                        "time_ms": {"type": "integer"},
                                        "frame_index": {"type": "integer"},
                                    },
                                    "required": [
                                        "text",
                                        "destination_hint",
                                        "time_ms",
                                        "frame_index",
                                    ],
                                },
                            },
                            "social_proof": {
                                "type": "object",
                                "properties": {
                                    "rating": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                                    "rating_count": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}]
                                    },
                                    "testimonials": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "badges": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["rating", "rating_count", "testimonials", "badges"],
                            },
                            "disclaimers": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "time_ms": {"type": "integer"},
                                        "frame_index": {"type": "integer"},
                                        "is_small_print": {"type": "boolean"},
                                    },
                                    "required": [
                                        "text",
                                        "time_ms",
                                        "frame_index",
                                        "is_small_print",
                                    ],
                                },
                            },
                            "creative_format": {
                                "type": "object",
                                "properties": {
                                    "aspect_ratio": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}]
                                    },
                                    "duration_ms": {"type": "integer"},
                                    "has_voiceover": {"type": "boolean"},
                                    "has_on_screen_text": {"type": "boolean"},
                                },
                                "required": [
                                    "aspect_ratio",
                                    "duration_ms",
                                    "has_voiceover",
                                    "has_on_screen_text",
                                ],
                            },
                        },
                        "required": [
                            "brand",
                            "products",
                            "prices",
                            "offers",
                            "ctas",
                            "social_proof",
                            "disclaimers",
                            "creative_format",
                        ],
                    },
                    "conflicts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "resolution": {"type": "string"},
                            },
                            "required": ["description", "sources", "resolution"],
                        },
                    },
                    "summary": {"type": "string"},
                },
                "required": [
                    "primary_category",
                    "risk_labels",
                    "confidence",
                    "decision",
                    "needs_human_review",
                    "ocr_quality",
                    "evidence",
                    "marketing_entities",
                    "conflicts",
                    "summary",
                ],
            },
        },
    }


class HTTPVLMVerifier(VLMVerifier):
    def __init__(
        self,
        *,
        endpoint: str = "http://localhost:1234/v1/chat/completions",
        model: str = "google/gemma-4-26b-a4b",
        api_key_env: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        retry_delay_s: float = 2.0,
        prompt_override: str | None = None,
    ) -> None:
        self._endpoint = _normalize_chat_endpoint(endpoint)
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._retry_delay_s = retry_delay_s
        self._system_prompt = prompt_override or render_verifier_prompt()

        api_key: str | None = None
        if api_key_env:
            api_key = os.environ.get(api_key_env)
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def verify(self, bundle: EvidenceBundle) -> VLMVerificationResult:
        content = _build_content(bundle)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": _vlm_response_format(),
        }

        last_error: str = "no attempts made"
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                time.sleep(self._retry_delay_s)
            try:
                resp = httpx.post(
                    self._endpoint,
                    headers=self._headers,
                    json=payload,
                    timeout=self._timeout_s,
                )
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                raw = message.get("content") or message.get("reasoning_content") or ""
                json_str = _extract_json(raw)
                parsed = json.loads(json_str)
                return VLMVerificationResult.model_validate(parsed)
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:1000] if exc.response is not None else ""
                last_error = (
                    f"HTTP error on attempt {attempt + 1}: "
                    f"status={exc.response.status_code if exc.response is not None else 'unknown'} "
                    f"body={body!r}"
                )
            except httpx.RequestError as exc:
                last_error = f"HTTP error on attempt {attempt + 1}: {exc}"
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                raw_text = raw if "raw" in dir() else ""
                return VLMVerificationResult.parse_failure(raw_text, str(exc))

        return VLMVerificationResult.parse_failure("", last_error)
