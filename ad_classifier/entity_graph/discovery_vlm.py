from __future__ import annotations

import json
import time
from typing import Literal, Protocol

from pydantic import Field

from ad_classifier._env import resolve_api_key
from ad_classifier.entity_graph.crawler_config import VLMDiscoveryParseConfig
from ad_classifier.entity_graph.models import EntityNode, RelatedAdSummary
from ad_classifier.models.common import StrictModel
from ad_classifier.vlm.http import chat_completion
from ad_classifier.vlm.verifier import _extract_json, _normalize_chat_endpoint


class DiscoveryProductFact(StrictModel):
    matched_submitted_product: str
    product_name: str
    product_description: str | None = None
    brand_name: str | None = None
    brand_description: str | None = None
    owner_name: str | None = None
    owner_description: str | None = None
    category_name: str | None = None
    relation_to_page: Literal[
        "manufacturer_page",
        "brand_page",
        "carrier_offer",
        "retailer_offer",
        "marketplace_offer",
        "reference_page",
        "unknown",
    ] = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_spans: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DiscoveryAlias(StrictModel):
    matched_submitted_product: str
    alias: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_spans: list[str] = Field(default_factory=list)


class DiscoveryTaxonomyHint(StrictModel):
    matched_submitted_product: str
    taxonomy_type: Literal["product", "content", "category"] = "category"
    taxonomy_name: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_spans: list[str] = Field(default_factory=list)


class DiscoveryAdChangeSuggestion(StrictModel):
    field_path: Literal[
        "ads.brand_name",
        "ads.products_text",
        "ads.primary_category",
        "ads.subcategory",
    ]
    current_value: str | None = None
    suggested_value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    evidence_spans: list[str] = Field(default_factory=list)
    apply_safety: Literal["safe_projection_update", "review_only", "do_not_apply"] = "review_only"


class DiscoveryVLMResult(StrictModel):
    source_url: str
    source_kind: Literal[
        "manufacturer",
        "brand",
        "carrier",
        "retailer",
        "marketplace",
        "reference",
        "search_result",
        "unknown",
    ] = "unknown"
    product_facts: list[DiscoveryProductFact] = Field(default_factory=list)
    aliases: list[DiscoveryAlias] = Field(default_factory=list)
    taxonomy_hints: list[DiscoveryTaxonomyHint] = Field(default_factory=list)
    suggested_ad_changes: list[DiscoveryAdChangeSuggestion] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    should_auto_confirm: bool = False


class DiscoveryVerifier(Protocol):
    def verify(
        self,
        *,
        source_url: str,
        final_url: str,
        title: str | None,
        description: str | None,
        text: str,
        products: list[EntityNode],
        submitted_ad: RelatedAdSummary | None = None,
    ) -> DiscoveryVLMResult:
        ...


class VLMDiscoveryVerifier:
    def __init__(self, config: VLMDiscoveryParseConfig) -> None:
        self.config = config
        self.endpoint = _normalize_chat_endpoint(config.endpoint)
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = resolve_api_key(config.api_key_env)
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def verify(
        self,
        *,
        source_url: str,
        final_url: str,
        title: str | None,
        description: str | None,
        text: str,
        products: list[EntityNode],
        submitted_ad: RelatedAdSummary | None = None,
    ) -> DiscoveryVLMResult:
        prompt = _render_discovery_prompt(
            config=self.config,
            source_url=source_url,
            final_url=final_url,
            title=title,
            description=description,
            text=text[: self.config.max_input_chars],
            products=products,
            submitted_ad=submitted_ad,
        )
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a product-entity enrichment verifier. Return only valid JSON. "
                        "Treat web/search/reference pages as discovery signals, not authoritative submitted evidence."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": _response_format(self.config.response_format),
            "chat_template_kwargs": {"enable_thinking": self.config.enable_thinking},
        }
        raw = self._chat_with_retries(payload)
        content = _message_content(raw)
        parsed = json.loads(_extract_json(content))
        result = DiscoveryVLMResult.model_validate(parsed)
        return result.model_copy(update={"should_auto_confirm": False})

    def _chat_with_retries(self, payload: dict) -> dict:
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                return chat_completion(
                    endpoint=self.endpoint,
                    headers=self.headers,
                    json=payload,
                    timeout_s=self.config.timeout_s,
                    stream=self.config.stream,
                )
            except Exception as exc:  # pragma: no cover - transport dependent
                last_error = exc
                if attempt < attempts - 1 and self.config.retry_delay_s:
                    time.sleep(self.config.retry_delay_s)
        raise RuntimeError(f"discovery VLM request failed: {last_error}") from last_error


def _response_format(fmt: str) -> dict:
    if fmt == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "product_discovery_enrichment",
                "schema": DiscoveryVLMResult.model_json_schema(),
            },
        }
    return {"type": "json_object"}


def _message_content(response: dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("discovery VLM response did not include choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        content = "\n".join(parts)
    if not isinstance(content, str) or not content.strip():
        text = choices[0].get("text")
        if isinstance(text, str):
            content = text
    if not isinstance(content, str) or not content.strip():
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str):
            content = reasoning
    if not isinstance(content, str) or not content.strip():
        raise ValueError("discovery VLM response did not include text content")
    return content


def _render_discovery_prompt(
    *,
    config: VLMDiscoveryParseConfig,
    source_url: str,
    final_url: str,
    title: str | None,
    description: str | None,
    text: str,
    products: list[EntityNode],
    submitted_ad: RelatedAdSummary | None,
) -> str:
    product_lines = "\n".join(
        f"- {product.canonical_name} | current_status={product.status} | current_confidence={product.confidence:.2f}"
        for product in products
    )
    schema_hint = {
        "source_url": source_url,
        "source_kind": "manufacturer|brand|carrier|retailer|marketplace|reference|search_result|unknown",
        "product_facts": [
            {
                "matched_submitted_product": "one submitted product name from the list",
                "product_name": "canonical product name found or verified on the page",
                "product_description": (
                    "optional 20-35 word synthesized product-page style sentence: "
                    "what the product is, what it does, and key supported traits; "
                    "not seller/offer/submitted-ad metadata"
                ),
                "brand_name": "manufacturer/brand if directly supported, not just the seller",
                "brand_description": "optional one-sentence synthesized brand description from page facts",
                "owner_name": "parent company/manufacturer owner only if directly supported",
                "owner_description": "optional one-sentence synthesized company description from page facts",
                "category_name": "plain product category if supported",
                "relation_to_page": "manufacturer_page|brand_page|carrier_offer|retailer_offer|marketplace_offer|reference_page|unknown",
                "confidence": 0.0,
                "evidence_spans": ["short snippets copied from the fetched page only"],
                "warnings": ["web_only", "seller_not_manufacturer", "conflict_with_submitted_brand"],
            }
        ],
        "aliases": [],
        "taxonomy_hints": [],
        "suggested_ad_changes": [
            {
                "field_path": "ads.products_text|ads.brand_name|ads.primary_category|ads.subcategory",
                "current_value": "current submitted value or null",
                "suggested_value": "corrected submitted value",
                "confidence": 0.0,
                "reason": "why this submitted DB projection appears wrong or missing",
                "evidence_spans": ["short snippets copied from the fetched page only"],
                "apply_safety": "safe_projection_update|review_only|do_not_apply",
            }
        ],
        "conflicts": [],
        "warnings": [],
        "should_auto_confirm": False,
    }
    submitted_payload = submitted_ad.model_dump(mode="json") if submitted_ad else None
    values = {
        "submitted_ad_json": json.dumps(submitted_payload, indent=2),
        "product_lines": product_lines,
        "source_url": source_url,
        "final_url": final_url,
        "title": title or "",
        "description": description or "",
        "page_text": text,
        "schema_hint_json": json.dumps(schema_hint, indent=2),
    }
    template = _prompt_template(config)
    try:
        return template.format(**values)
    except KeyError:
        return _default_prompt_template().format(**values)


def _prompt_template(config: VLMDiscoveryParseConfig) -> str:
    prompt_path = config.prompt_path
    if prompt_path is not None and prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return _default_prompt_template()


def _default_prompt_template() -> str:
    return (
        "Verify product entity facts and submitted-ad field mismatches from a fetched webpage.\n"
        "Return only valid JSON matching the supplied schema. Web pages are discovery signals only.\n"
        "Do not infer that a carrier, retailer, dealer, or marketplace is the product brand/manufacturer.\n"
        "Do not set owner_name from copyright-only, script, plugin, analytics, privacy, payment, or "
        "infrastructure vendor snippets unless the evidence also says owned by, operated by, legal name, "
        "or parent company.\n"
        "Do not mark product-field changes safe when a webpage only narrows a submitted base product "
        "into a year, trim, package, or variant; use review_only unless submitted ad evidence supports it.\n"
        "Emit product_description as a 20-35 word neutral ecommerce-style summary of what the product is and does, "
        "when directly supported by page text. It should answer what the item/service is, what it is used for, "
        "and concrete supported traits. Do not summarize the seller, offer terms, or submitted ad metadata. "
        "Do not copy marketing text verbatim.\n"
        "Emit suggested_ad_changes only for submitted DB fields that are wrong, missing, or generic.\n\n"
        "Submitted ad:\n{submitted_ad_json}\n\n"
        "Submitted product candidates:\n{product_lines}\n\n"
        "Source URL: {source_url}\nFinal URL: {final_url}\nTitle: {title}\n"
        "Meta description: {description}\n\nFetched page text:\n{page_text}\n\n"
        "Return JSON matching this shape:\n{schema_hint_json}"
    )
