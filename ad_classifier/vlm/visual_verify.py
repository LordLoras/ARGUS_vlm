from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from ad_classifier.vlm.models import VLMConflict, VLMVerificationResult
from ad_classifier.vlm.verifier import _extract_json, _normalize_chat_endpoint

_VISUAL_VERIFY_PROMPT = """\
You verify ad-analysis claims against actual video frames. You receive 2-3 key frames and a list of claims.

For each claim, answer true or false based ONLY on what you see in the frames.

Claims to verify:
{claims}

Return JSON:
{{"verified": {{"brand_visible": true, "products_visible": true, "logo_present": true}}, "notes": "optional explanation"}}
"""


class VisualVerificationPass:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        max_tokens: int = 512,
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
        frame_paths: list[Path],
    ) -> VLMVerificationResult:
        if not frame_paths or len(frame_paths) < 2:
            return result

        key_frames = frame_paths[:3]
        claims = _build_claims(result)
        if not claims:
            return result

        system_prompt = _VISUAL_VERIFY_PROMPT.format(claims=claims)
        content = _build_visual_content(key_frames, system_prompt)

        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
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
            return _apply_visual_corrections(result, raw)
        except Exception:
            return result


def _build_claims(result: VLMVerificationResult) -> str:
    lines: list[str] = []
    me = result.marketing_entities
    if me.brand and me.brand.name:
        lines.append(f"- Brand name: {me.brand.name}")
    if me.brand and me.brand.logo_present:
        lines.append("- Logo is visible on screen")
    for p in me.products[:3]:
        lines.append(f"- Product: {p}")
    lines.append(f"- Category: {result.primary_category}")
    return "\n".join(lines)


def _build_visual_content(frame_paths: list[Path], system_prompt: str) -> list[dict]:
    parts: list[dict] = [{"type": "text", "text": "Verify the claims against these frames:"}]
    for path in frame_paths:
        if not path.exists():
            continue
        suffix = path.suffix.lower().lstrip(".")
        mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            }
        )
    return parts


def _apply_visual_corrections(result: VLMVerificationResult, raw: str) -> VLMVerificationResult:
    json_str = _extract_json(raw)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return result

    verified = parsed.get("verified", {})
    if not isinstance(verified, dict):
        return result

    result = result.model_copy(deep=True)
    me = result.marketing_entities
    notes = parsed.get("notes", "")

    if verified.get("brand_visible") is False and me.brand and me.brand.name:
        result.conflicts.append(
            VLMConflict(
                description=f"Visual verify: brand_visible=False but VLM extracted brand={me.brand.name!r}",
                sources=["vlm_verifier", "visual_verify"],
                resolution=notes or "Visual verify disagrees on brand visibility (preserving VLM extraction with low confidence)",
            )
        )

    if verified.get("logo_present") is False and me.brand and me.brand.logo_present:
        result.conflicts.append(
            VLMConflict(
                description="Visual verify: logo_present=False but VLM reported logo as visible",
                sources=["vlm_verifier", "visual_verify"],
                resolution=notes or "Visual verify disagrees on logo presence",
            )
        )

    if verified.get("products_visible") is False and me.products:
        result.conflicts.append(
            VLMConflict(
                description=f"Visual verify: products_visible=False but VLM extracted products={me.products!r}",
                sources=["vlm_verifier", "visual_verify"],
                resolution=notes or "Visual verify disagrees on product visibility (preserving VLM extraction)",
            )
        )

    return result
