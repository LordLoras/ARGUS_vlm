from __future__ import annotations

import json
import logging

import httpx
import structlog

logger = logging.getLogger(__name__)
_log = structlog.get_logger(__name__)

from ad_classifier.vlm.models import VLMVerificationResult
from ad_classifier.vlm.verifier import _extract_json, _normalize_chat_endpoint

_CORRECTION_PROMPT = """\
You are an ad-analysis quality checker. You receive an analysis of a TV ad and the raw evidence it was based on.

Check for these inconsistencies:
1. Brand name that does not appear in any OCR text or transcript
2. Products listed that have no evidence in the raw text
3. Category that contradicts the products/brand (e.g., category "food_beverage" with car products)
4. Offers that are clearly garbled OCR artifacts, not real offers
5. Prices that are obvious OCR fragments (e.g., "$3" from "$3,839"), monthly payments, or per-unit rates (e.g., "$27.78 per $1,000")
6. CTAs that are fabricated or not grounded in evidence
7. Advertiser parent_company inferred from fine print rather than prominently displayed

If you find inconsistencies, return ONLY a JSON object with corrected fields.
If the analysis looks correct, return: {"corrections": {}}

Output JSON only. No markdown. No explanation.

Example corrections:
{"corrections": {"primary_category": "automotive", "products": ["Grand Cherokee"], "offers_to_remove": [0], "prices_to_remove": [1], "parent_company": null}}

If no corrections needed:
{"corrections": {}}
"""


class SelfCorrectionPass:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        max_tokens: int = 1024,
        enable_thinking: bool = False,
    ) -> None:
        self._endpoint = _normalize_chat_endpoint(endpoint)
        self._model = model
        self._timeout = timeout_s
        self._max_tokens = max_tokens
        self._enable_thinking = enable_thinking
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def run(
        self,
        result: VLMVerificationResult,
        evidence_texts: list[str],
    ) -> VLMVerificationResult:
        if not evidence_texts:
            return result

        evidence_blob = "\n".join(evidence_texts)[:4000]
        analysis = json.dumps(
            result.model_dump(exclude={"parse_ok", "raw_response", "parse_error"})
        )[:3000]

        user_text = f"Raw evidence:\n{evidence_blob}\n\nAnalysis:\n{analysis}"
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _CORRECTION_PROMPT},
                {"role": "user", "content": user_text},
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

            finish_reason = data.get("choices", [{}])[0].get("finish_reason", "")
            if not raw.strip():
                _log.warning("self_correction_empty_response", finish_reason=finish_reason)
                return result
            if finish_reason == "length":
                _log.warning("self_correction_max_tokens_reached", finish_reason=finish_reason, raw_length=len(raw))
            elif finish_reason not in ("stop", "stop_sequence", "eos", ""):
                _log.warning("self_correction_unexpected_finish", finish_reason=finish_reason, raw_length=len(raw))

            return _apply_corrections(result, raw)
        except httpx.RequestError as exc:
            _log.warning("self_correction_disconnected", error=str(exc)[:300])
            return result
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:200] if exc.response is not None else ""
            _log.warning("self_correction_http_error", status=exc.response.status_code if exc.response is not None else None, body=body)
            return result
        except Exception as exc:
            logger.warning("self_correction_failed: %s", exc)
            return result


def _apply_corrections(result: VLMVerificationResult, raw: str) -> VLMVerificationResult:
    json_str = _extract_json(raw)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return result

    corrections = parsed.get("corrections", {})
    if not corrections or not isinstance(corrections, dict):
        return result

    result = result.model_copy(deep=True)
    me = result.marketing_entities

    if "primary_category" in corrections and isinstance(corrections["primary_category"], str):
        result.primary_category = corrections["primary_category"]
    if "products" in corrections and isinstance(corrections["products"], list):
        me.products = [str(p) for p in corrections["products"]]
    if "brand_name" in corrections and isinstance(corrections["brand_name"], str):
        me.brand.name = corrections["brand_name"]

    if "prices_to_remove" in corrections and isinstance(corrections["prices_to_remove"], list):
        indices = {i for i in corrections["prices_to_remove"] if isinstance(i, int) and 0 <= i < len(me.prices)}
        me.prices = [p for i, p in enumerate(me.prices) if i not in indices]

    if "offers_to_remove" in corrections and isinstance(corrections["offers_to_remove"], list):
        indices = {i for i in corrections["offers_to_remove"] if isinstance(i, int) and 0 <= i < len(me.offers)}
        me.offers = [o for i, o in enumerate(me.offers) if i not in indices]

    if "ctas_to_remove" in corrections and isinstance(corrections["ctas_to_remove"], list):
        indices = {i for i in corrections["ctas_to_remove"] if isinstance(i, int) and 0 <= i < len(me.ctas)}
        me.ctas = [c for i, c in enumerate(me.ctas) if i not in indices]

    if "parent_company" in corrections:
        me.advertiser.parent_company = corrections["parent_company"]

    return result
