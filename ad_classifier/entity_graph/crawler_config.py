from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ad_classifier.entity_graph.utils import normalize_name


class ProductResolverConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strip_leading_model_year: bool = True
    strip_context_brand_prefix: bool = True
    collapse_variants_when_base_observed: bool = True
    min_unmatched_name_chars: int = Field(default=1, ge=1)
    context_prefix_min_chars: int = Field(default=3, ge=1)
    drop_exact: list[str] = Field(default_factory=list)
    drop_regex: list[str] = Field(default_factory=list)
    context_prefix_stopwords: list[str] = Field(default_factory=list)
    ad_context_category_exact: list[str] = Field(default_factory=list)
    ad_context_category_regex: list[str] = Field(default_factory=list)


class EntityCrawlerSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    provider: Literal["disabled", "duckduckgo", "http", "browser"] = "disabled"
    max_queries_per_run: int = Field(default=25, ge=1)
    max_results_per_query: int = Field(default=5, ge=1, le=25)
    max_pages_per_entity: int = Field(default=3, ge=0, le=10)
    max_targets_per_ad: int = Field(default=3, ge=1, le=20)
    follow_product_links: bool = True
    max_followup_links_per_page: int = Field(default=3, ge=0, le=10)
    follow_brand_context_links: bool = True
    max_brand_context_links_per_page: int = Field(default=2, ge=0, le=5)
    recursive_source_kinds: list[str] = Field(default_factory=lambda: ["manufacturer", "brand"])
    brand_context_link_terms: list[str] = Field(
        default_factory=lambda: [
            "about",
            "about us",
            "our story",
            "story",
            "company",
            "who we are",
        ]
    )
    reference_search_enabled: bool = False
    max_reference_results_per_ad: int = Field(default=2, ge=0, le=10)
    reference_search_endpoint: str = "https://duckduckgo.com/html/"
    reference_search_query_template: str = "{product} official product"
    reference_search_query_templates: list[str] = Field(
        default_factory=lambda: [
            '"{brand}" "{product}" official product',
            '"{product}" "{brand}" product details',
            "{brand} {product} official product page",
            "{product} manufacturer official",
            "{advertiser} {product} official",
            '"{brand}" official website',
            '"{brand}" product catalog',
        ]
    )
    timeout_s: float = Field(default=10.0, ge=0.1)
    max_page_bytes: int = Field(default=1_500_000, ge=50_000, le=5_000_000)
    rate_limit_per_minute: int = Field(default=30, ge=1)
    cache_dir: Path = Path("./data/entity_crawler_cache")
    user_agent: str = "ARGUS-EntityCrawler/0.1"
    use_browser_fallback: bool = False
    respect_robots_txt: bool = True
    store_raw_html: bool = False
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    require_context_match_for_ad_targets: bool = True
    allow_cta_evidence_targets: bool = True
    target_context_min_chars: int = Field(default=3, ge=1)
    target_context_stopwords: list[str] = Field(
        default_factory=lambda: [
            "ad",
            "ads",
            "auto",
            "car",
            "cars",
            "com",
            "deal",
            "dealer",
            "dealership",
            "model",
            "models",
            "new",
            "offer",
            "sale",
            "sales",
            "shop",
            "suv",
            "suvs",
            "truck",
            "trucks",
            "vehicle",
            "vehicles",
            "www",
        ]
    )
    target_evidence_cta_phrases: list[str] = Field(
        default_factory=lambda: [
            "visit",
            "go to",
            "shop",
            "buy",
            "order",
            "learn more",
            "get started",
            "schedule",
            "book",
            "apply",
        ]
    )


class VLMDiscoveryParseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    write_mode: Literal["candidate_only"] = "candidate_only"
    prompt_path: Path | None = Path("./crawler_prompt.txt")
    max_input_chars: int = Field(default=6000, ge=500)
    endpoint: str = "https://ai.ipdy.io/llm/v1"
    model: str = "model"
    api_key_env: str | None = "VLM_API_KEY"
    timeout_s: float = Field(default=120.0, ge=1.0)
    max_retries: int = Field(default=2, ge=0)
    retry_delay_s: float = Field(default=2.0, ge=0.0)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=256)
    response_format: Literal["json_object", "json_schema"] = "json_schema"
    stream: bool = True
    enable_thinking: bool = False


class TaxonomyAliasRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    terms: list[str] = Field(default_factory=list)
    product_taxonomy_id: str | None = None
    content_taxonomy_id: str | None = None
    confidence: float = Field(default=0.62, ge=0.0, le=1.0)


class TaxonomyAlignmentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    knowledge_db_path: Path = Path("./knowledge.db")
    create_iab_category_edges: bool = True
    min_product_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    min_content_confidence: float = Field(default=0.45, ge=0.0, le=1.0)
    aliases: list[TaxonomyAliasRule] = Field(
        default_factory=lambda: [
            TaxonomyAliasRule(
                terms=[
                    "vehicle",
                    "vehicles",
                    "car",
                    "cars",
                    "auto",
                    "automotive",
                    "suv",
                    "sport utility",
                    "crossover",
                    "truck",
                    "pickup",
                    "sedan",
                    "coupe",
                    "van",
                    "luxury suv",
                    "full-size suv",
                ],
                product_taxonomy_id="1551",
                content_taxonomy_id="6",
                confidence=0.66,
            ),
            TaxonomyAliasRule(
                terms=[
                    "smartphone",
                    "smartphones",
                    "mobile phone",
                    "cell phone",
                    "iphone",
                    "android phone",
                ],
                product_taxonomy_id="1114",
                content_taxonomy_id="635",
                confidence=0.68,
            ),
            TaxonomyAliasRule(
                terms=[
                    "mobile service",
                    "cellular service",
                    "wireless plan",
                    "phone plan",
                    "mobile plan",
                ],
                product_taxonomy_id="1471",
                confidence=0.63,
            ),
            TaxonomyAliasRule(
                terms=[
                    "cosmetic",
                    "cosmetics",
                    "makeup",
                    "foundation",
                    "foundation stick",
                    "lipstick",
                    "blush",
                    "mascara",
                    "beauty product",
                ],
                product_taxonomy_id="1138",
                content_taxonomy_id="555",
                confidence=0.66,
            ),
            TaxonomyAliasRule(
                terms=[
                    "skin care",
                    "skincare",
                    "sunscreen",
                    "serum",
                    "cleanser",
                    "lotion",
                ],
                product_taxonomy_id="1244",
                content_taxonomy_id="553",
                confidence=0.63,
            ),
        ]
    )


class SubmittedDbRepairConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    allowed_fields: list[str] = Field(
        default_factory=lambda: [
            "ads.brand_name",
            "ads.products_text",
            "ads.primary_category",
            "ads.subcategory",
        ]
    )


class IngestAssistConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    default_mode: Literal[
        "keep_initial_metadata",
        "use_graph",
        "crawl_reinforce",
    ] = "keep_initial_metadata"
    min_graph_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    crawl_on_low_confidence: bool = False


class EntityCrawlerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    crawler: EntityCrawlerSettings = Field(default_factory=EntityCrawlerSettings)
    vlm_parse: VLMDiscoveryParseConfig = Field(default_factory=VLMDiscoveryParseConfig)
    taxonomy_alignment: TaxonomyAlignmentConfig = Field(default_factory=TaxonomyAlignmentConfig)
    resolver: ProductResolverConfig = Field(default_factory=ProductResolverConfig)
    discovery_source_type: Literal["discovery_only"] = "discovery_only"
    discovery_status: Literal["candidate"] = "candidate"
    search_only_can_confirm: bool = False
    submitted_db_repairs: SubmittedDbRepairConfig = Field(default_factory=SubmittedDbRepairConfig)
    ingest_assist: IngestAssistConfig = Field(default_factory=IngestAssistConfig)


@dataclass(frozen=True)
class ResolvedProductCandidate:
    canonical_name: str
    original_name: str
    original_names: tuple[str, ...]
    brand_name: str | None
    dropped: bool = False


def load_entity_crawler_config(path: Path | None) -> EntityCrawlerConfig:
    if path is None:
        return EntityCrawlerConfig()
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return EntityCrawlerConfig()
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    config = EntityCrawlerConfig.model_validate(data)
    prompt_path = config.vlm_parse.prompt_path
    if prompt_path is not None and not prompt_path.is_absolute():
        config = config.model_copy(
            update={
                "vlm_parse": config.vlm_parse.model_copy(
                    update={"prompt_path": (resolved.parent / prompt_path).resolve()}
                )
            }
        )
    knowledge_path = config.taxonomy_alignment.knowledge_db_path
    if not knowledge_path.is_absolute():
        config = config.model_copy(
            update={
                "taxonomy_alignment": config.taxonomy_alignment.model_copy(
                    update={"knowledge_db_path": (resolved.parent / knowledge_path).resolve()}
                )
            }
        )
    return config


def build_reference_search_queries(
    config: EntityCrawlerConfig,
    *,
    product_name: str | None,
    brand: str | None,
    advertiser: str | None,
    ad_id: str,
) -> list[str]:
    values = {
        "product": product_name or "",
        "brand": brand or "",
        "advertiser": advertiser or "",
        "ad_id": ad_id,
    }
    templates = config.crawler.reference_search_query_templates or [
        config.crawler.reference_search_query_template
    ]
    queries: list[str] = []
    for template in templates:
        if not _template_context_available(template, values):
            continue
        query = template.format(**values)
        query = re.sub(r"\s+", " ", query).strip()
        if normalize_name(query):
            queries.append(query)
    if not queries and product_name:
        fallback_template = config.crawler.reference_search_query_template
        if _template_context_available(fallback_template, values):
            queries.append(fallback_template.format(**values))
        else:
            queries.append(f"{product_name} official product")
    if not queries and brand:
        queries.append(f"{brand} official website")
    return _unique_queries(queries)


def _template_context_available(template: str, values: dict[str, str]) -> bool:
    required = set(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", template))
    return all(values.get(name, "").strip() for name in required)


def _unique_queries(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        query = re.sub(r"\s+", " ", value).strip()
        key = normalize_name(query)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(query)
    return result


def resolve_product_candidate(
    raw: str,
    *,
    row_brand: str | None,
    context_names: list[str] | None = None,
    config: EntityCrawlerConfig,
) -> ResolvedProductCandidate | None:
    original = _clean_spaces(raw)
    if not original:
        return None

    candidates = _candidate_texts(original, config.resolver)
    inferred_brand, stripped = _strip_context_brand_prefix(
        candidates[-1],
        row_brand=row_brand,
        context_names=context_names or [],
        resolver=config.resolver,
    )
    candidate_name = _clean_spaces(stripped)
    if (
        not candidate_name
        or _is_dropped_term(candidate_name, config.resolver.drop_exact)
        or _matches_drop_regex(candidate_name, config.resolver.drop_regex)
        or len(normalize_name(candidate_name).replace(" ", "")) < config.resolver.min_unmatched_name_chars
    ):
        return ResolvedProductCandidate(
            canonical_name=candidate_name or original,
            original_name=original,
            original_names=(original,),
            brand_name=inferred_brand or row_brand,
            dropped=True,
        )

    return ResolvedProductCandidate(
        canonical_name=candidate_name,
        original_name=original,
        original_names=(original,),
        brand_name=inferred_brand or row_brand,
    )


def collapse_product_candidates(
    candidates: list[ResolvedProductCandidate],
    config: EntityCrawlerConfig,
) -> list[ResolvedProductCandidate]:
    active = [candidate for candidate in candidates if not candidate.dropped]
    if not config.resolver.collapse_variants_when_base_observed:
        return _merge_duplicate_candidates(active)

    collapsed: list[ResolvedProductCandidate] = []
    for candidate in active:
        collapsed.append(_collapse_to_observed_base(candidate, active, config.resolver))
    return _merge_duplicate_candidates(collapsed)


def product_resolution_key(value: str, config: EntityCrawlerConfig) -> str:
    resolved = resolve_product_candidate(value, row_brand=None, config=config)
    if resolved is None or resolved.dropped:
        return ""
    return normalize_name(resolved.canonical_name)


def is_product_variant_of_base(
    candidate_name: str, base_name: str, config: EntityCrawlerConfig
) -> bool:
    candidate_key = normalize_name(candidate_name)
    base_key = normalize_name(base_name)
    if not candidate_key or not base_key or candidate_key == base_key:
        return False
    if len(base_key.replace(" ", "")) < config.resolver.min_unmatched_name_chars:
        return False
    if len(base_key) >= len(candidate_key):
        return False
    if _is_dropped_term(base_name, config.resolver.drop_exact):
        return False
    if candidate_key.startswith(f"{base_key} "):
        return True
    candidate_tokens = candidate_key.split()
    base_tokens = base_key.split()
    return _base_tokens_match_variant(candidate_tokens, base_tokens)


def _candidate_texts(value: str, resolver: ProductResolverConfig) -> list[str]:
    candidates = [_clean_spaces(value)]
    if resolver.strip_leading_model_year:
        candidates.append(_strip_model_year(candidates[-1]))
    return [item for item in dict.fromkeys(candidates) if item]


def _strip_context_brand_prefix(
    value: str,
    *,
    row_brand: str | None,
    context_names: list[str],
    resolver: ProductResolverConfig,
) -> tuple[str | None, str]:
    if not resolver.strip_context_brand_prefix:
        return row_brand, value
    normalized = normalize_name(value)
    for prefix in _context_prefixes(row_brand, context_names, resolver):
        key = normalize_name(prefix)
        if not key:
            continue
        if normalized == key:
            return prefix, ""
        if normalized.startswith(f"{key} "):
            return prefix, _remove_display_prefix(value, prefix)
    return None, value


def _context_prefixes(
    row_brand: str | None, context_names: list[str], resolver: ProductResolverConfig
) -> list[str]:
    prefixes: list[str] = []
    if row_brand:
        prefixes.append(row_brand)
    for context in context_names:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9&'-]*", context or ""):
            if len(normalize_name(token).replace(" ", "")) < resolver.context_prefix_min_chars:
                continue
            if _is_dropped_term(token, resolver.drop_exact) or _is_dropped_term(
                token, resolver.context_prefix_stopwords
            ):
                continue
            prefixes.append(token)
    return _unique_sorted(prefixes)


def _remove_display_prefix(value: str, prefix: str) -> str:
    words = value.split()
    prefix_words = prefix.split()
    if len(words) >= len(prefix_words):
        return " ".join(words[len(prefix_words) :])
    return ""


def _collapse_to_observed_base(
    candidate: ResolvedProductCandidate,
    observed: list[ResolvedProductCandidate],
    resolver: ProductResolverConfig,
) -> ResolvedProductCandidate:
    bases = [
        other
        for other in observed
        if _can_be_base_product(candidate, other, resolver)
        and _brand_compatible(candidate.brand_name, other.brand_name)
    ]
    if not bases:
        return candidate
    base = max(bases, key=lambda item: len(normalize_name(item.canonical_name)))
    return ResolvedProductCandidate(
        canonical_name=base.canonical_name,
        original_name=candidate.original_name,
        original_names=_unique_tuple([*base.original_names, *candidate.original_names]),
        brand_name=base.brand_name or candidate.brand_name,
        dropped=False,
    )


def _can_be_base_product(
    candidate: ResolvedProductCandidate,
    base: ResolvedProductCandidate,
    resolver: ProductResolverConfig,
) -> bool:
    config = EntityCrawlerConfig(
        resolver=resolver,
        crawler=EntityCrawlerSettings(),
        vlm_parse=VLMDiscoveryParseConfig(),
    )
    return is_product_variant_of_base(candidate.canonical_name, base.canonical_name, config)


def _base_tokens_match_variant(candidate_tokens: list[str], base_tokens: list[str]) -> bool:
    if len(candidate_tokens) <= len(base_tokens):
        return False
    candidate_index = 0
    base_index = 0
    while candidate_index < len(candidate_tokens) and base_index < len(base_tokens):
        base_token = base_tokens[base_index]
        candidate_token = candidate_tokens[candidate_index]
        if candidate_token == base_token:
            candidate_index += 1
            base_index += 1
            continue
        acronym_len = len(base_token)
        acronym_tokens = candidate_tokens[candidate_index : candidate_index + acronym_len]
        if acronym_len >= 2 and _acronym(acronym_tokens) == base_token:
            candidate_index += acronym_len
            base_index += 1
            continue
        candidate_index += 1
    return base_index == len(base_tokens)


def _acronym(tokens: list[str]) -> str:
    return "".join(token[:1] for token in tokens if token)


def _brand_compatible(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    return normalize_name(left) == normalize_name(right)


def _merge_duplicate_candidates(
    candidates: list[ResolvedProductCandidate],
) -> list[ResolvedProductCandidate]:
    by_key: dict[tuple[str, str], ResolvedProductCandidate] = {}
    for candidate in candidates:
        key = (normalize_name(candidate.canonical_name), normalize_name(candidate.brand_name))
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = candidate
            continue
        by_key[key] = ResolvedProductCandidate(
            canonical_name=existing.canonical_name,
            original_name=existing.original_name,
            original_names=_unique_tuple([*existing.original_names, *candidate.original_names]),
            brand_name=existing.brand_name or candidate.brand_name,
            dropped=False,
        )
    return list(by_key.values())


def _is_dropped_term(value: str, drop_exact: list[str]) -> bool:
    normalized = normalize_name(value)
    return normalized in {normalize_name(item) for item in drop_exact}


def _matches_drop_regex(value: str, drop_regex: list[str]) -> bool:
    for pattern in drop_regex:
        try:
            if re.search(pattern, value):
                return True
        except re.error:
            continue
    return False


def _strip_model_year(value: str) -> str:
    return re.sub(r"^(?:19|20)\d{2}\s+", "", value).strip()


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).strip(" ,;:-")


def _unique_tuple(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_unique_sorted(values, preserve_order=True))


def _unique_sorted(values: list[str] | tuple[str, ...], *, preserve_order: bool = False) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _clean_spaces(value)
        key = normalize_name(clean)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(clean)
    if preserve_order:
        return result
    return sorted(result, key=lambda item: (-len(item), item.lower()))
