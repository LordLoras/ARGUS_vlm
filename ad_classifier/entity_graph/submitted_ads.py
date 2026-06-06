from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from ad_classifier.db.connection import open_readonly_database
from ad_classifier.entity_graph.crawler_config import (
    EntityCrawlerConfig,
    build_reference_search_queries,
    collapse_product_candidates,
    is_product_variant_of_base,
    resolve_product_candidate,
)
from ad_classifier.entity_graph.models import (
    RelatedAdSummary,
    SubmittedAdCrawlQueueItem,
    SubmittedAdObservation,
    SubmittedAdWebTarget,
)
from ad_classifier.entity_graph.utils import normalize_name


@dataclass(frozen=True)
class _ProductCandidate:
    name: str
    original_names: tuple[str, ...]
    brand_name: str | None


class SubmittedAdReadOnlyRepository:
    def __init__(
        self, db_path: Path, *, crawler_config: EntityCrawlerConfig | None = None
    ) -> None:
        self.db_path = db_path.expanduser().resolve()
        self.crawler_config = crawler_config or EntityCrawlerConfig()

    def list_product_observations(
        self,
        *,
        limit: int = 1000,
        ad_ids: list[str] | None = None,
    ) -> list[SubmittedAdObservation]:
        conn = open_readonly_database(self.db_path)
        try:
            clauses = ["coalesce(m.products_json, a.products_text, '') <> ''"]
            params: list[object] = []
            cleaned_ad_ids = [item.strip() for item in ad_ids or [] if item.strip()]
            if cleaned_ad_ids:
                placeholders = ",".join("?" for _ in cleaned_ad_ids)
                clauses.append(f"a.id IN ({placeholders})")
                params.extend(cleaned_ad_ids)
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT
                  a.id,
                  a.brand_name,
                  a.advertiser_name,
                  a.products_text,
                  a.primary_category,
                  a.subcategory,
                  a.iab_unique_id,
                  a.iab_selected_category,
                  a.iab_full_path,
                  a.iab_content_ids,
                  a.iab_content_paths,
                  m.brand_json,
                  m.products_json,
                  m.advertiser_json
                FROM ads a
                LEFT JOIN marketing_entities m ON m.ad_id = a.id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.ingested_at DESC, a.id
                LIMIT ?
                """,
                params,
            ).fetchall()
            observations: list[SubmittedAdObservation] = []
            for row in rows:
                for product in _product_candidates(row, self.crawler_config):
                    evidence = _best_evidence(conn, row["id"], [*product.original_names, product.name])
                    observations.append(
                        SubmittedAdObservation(
                            ad_id=row["id"],
                            product_name=product.name,
                            original_product_names=list(product.original_names),
                            brand_name=product.brand_name,
                            advertiser_name=_advertiser(row),
                            parent_company=_parent_company(row),
                            primary_category=row["primary_category"],
                            subcategory=row["subcategory"],
                            iab_product_id=row["iab_unique_id"],
                            iab_product_name=row["iab_selected_category"] or row["iab_full_path"],
                            iab_content_ids=_csv(row["iab_content_ids"]),
                            iab_content_names=_content_names(row["iab_content_paths"]),
                            evidence_text=evidence["text"],
                            evidence_source=evidence["source"],
                            time_ms=evidence["time_ms"],
                            frame_index=evidence["frame_index"],
                            confidence=_observation_confidence(row, evidence),
                        )
                    )
            return _collapse_global_observation_variants(observations, self.crawler_config)
        finally:
            conn.close()

    def list_web_targets(
        self, *, limit: int = 1000, ad_ids: list[str] | None = None
    ) -> list[SubmittedAdWebTarget]:
        conn = open_readonly_database(self.db_path)
        try:
            clauses = [
                """
                coalesce(
                  a.website_domain,
                  a.landing_page_domain,
                  m.contact_points_json,
                  m.landing_page_json,
                  ''
                ) <> ''
                """
            ]
            params: list[object] = []
            cleaned_ad_ids = [item.strip() for item in ad_ids or [] if item.strip()]
            if cleaned_ad_ids:
                placeholders = ",".join("?" for _ in cleaned_ad_ids)
                clauses.append(f"a.id IN ({placeholders})")
                params.extend(cleaned_ad_ids)
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT
                  a.id,
                  a.brand_name,
                  a.advertiser_name,
                  a.products_text,
                  a.website_domain,
                  a.landing_page_domain,
                  m.brand_json,
                  m.products_json,
                  m.advertiser_json,
                  m.contact_points_json,
                  m.landing_page_json
                FROM ads a
                LEFT JOIN marketing_entities m ON m.ad_id = a.id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.ingested_at DESC, a.id
                LIMIT ?
                """,
                params,
            ).fetchall()
            targets: list[SubmittedAdWebTarget] = []
            by_ad: dict[str, list[SubmittedAdWebTarget]] = {}
            for row in rows:
                for target in _web_targets(row, self.crawler_config):
                    by_ad.setdefault(target.ad_id, []).append(target)
            for ad_targets in by_ad.values():
                targets.extend(
                    _dedupe_targets_for_ad(
                        ad_targets,
                        max_targets=self.crawler_config.crawler.max_targets_per_ad,
                    )
                )
            return targets
        finally:
            conn.close()

    def list_crawl_queue(
        self,
        *,
        limit: int = 1000,
        q: str | None = None,
    ) -> list[SubmittedAdCrawlQueueItem]:
        conn = open_readonly_database(self.db_path)
        try:
            clauses = ["coalesce(a.products_text, m.products_json, '') <> ''"]
            params: list[object] = []
            if q:
                clauses.append(
                    """
                    (
                      a.id LIKE ?
                      OR coalesce(a.brand_name, '') LIKE ?
                      OR coalesce(a.products_text, '') LIKE ?
                      OR coalesce(a.primary_category, '') LIKE ?
                      OR coalesce(a.subcategory, '') LIKE ?
                    )
                    """
                )
                like = f"%{q}%"
                params.extend([like, like, like, like, like])
            params.append(limit)
            result = conn.execute(
                f"""
                SELECT
                  a.id,
                  a.brand_name,
                  a.advertiser_name,
                  a.products_text,
                  a.primary_category,
                  a.subcategory,
                  a.ingested_at,
                  a.website_domain,
                  a.landing_page_domain,
                  m.brand_json,
                  m.products_json,
                  m.advertiser_json,
                  m.contact_points_json,
                  m.landing_page_json
                FROM ads a
                LEFT JOIN marketing_entities m ON m.ad_id = a.id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.ingested_at DESC, a.id
                LIMIT ?
                """,
                params,
            ).fetchall()
            items: list[SubmittedAdCrawlQueueItem] = []
            for row in result:
                targets = _web_targets(row, self.crawler_config)
                products = _raw_products(row)
                search_queries = _reference_search_queries_for_row(row, products, self.crawler_config)
                items.append(
                    SubmittedAdCrawlQueueItem(
                        ad_id=row["id"],
                        brand_name=row["brand_name"],
                        products_text=row["products_text"],
                        primary_category=row["primary_category"],
                        subcategory=row["subcategory"],
                        ingested_at=str(row["ingested_at"]) if row["ingested_at"] else None,
                        has_web_targets=bool(targets),
                        web_targets=[target.url for target in targets],
                        has_search_targets=bool(search_queries),
                        search_queries=search_queries,
                        product_count=len(products),
                    )
                )
            return items
        finally:
            conn.close()

    def related_ads(self, ad_ids: list[str]) -> list[RelatedAdSummary]:
        if not ad_ids:
            return []
        conn = open_readonly_database(self.db_path)
        try:
            placeholders = ",".join("?" for _ in ad_ids)
            rows = conn.execute(
                f"""
                SELECT id, brand_name, products_text, primary_category, subcategory, ingested_at
                FROM ads
                WHERE id IN ({placeholders})
                ORDER BY ingested_at DESC, id
                """,
                ad_ids,
            ).fetchall()
            return [
                RelatedAdSummary(
                    ad_id=row["id"],
                    brand_name=row["brand_name"],
                    products_text=row["products_text"],
                    primary_category=row["primary_category"],
                    subcategory=row["subcategory"],
                    ingested_at=str(row["ingested_at"]) if row["ingested_at"] else None,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def query_only_enabled(self) -> bool:
        conn = open_readonly_database(self.db_path)
        try:
            return bool(conn.execute("PRAGMA query_only").fetchone()[0])
        finally:
            conn.close()


def _product_candidates(
    row: sqlite3.Row, crawler_config: EntityCrawlerConfig
) -> list[_ProductCandidate]:
    base_brand = _brand(row)
    context_names = _context_names(row)
    resolved_products = []
    for raw_product in _raw_products(row):
        resolved = resolve_product_candidate(
            raw_product,
            row_brand=base_brand,
            context_names=context_names,
            config=crawler_config,
        )
        if resolved is not None:
            resolved_products.append(resolved)

    by_key: dict[tuple[str, str], _ProductCandidate] = {}
    for resolved in collapse_product_candidates(resolved_products, crawler_config):
        key = (normalize_name(resolved.canonical_name), normalize_name(resolved.brand_name))
        existing = by_key.get(key)
        original_names = _unique(
            [*(existing.original_names if existing else ()), *resolved.original_names]
        )
        by_key[key] = _ProductCandidate(
            name=resolved.canonical_name,
            original_names=tuple(original_names),
            brand_name=resolved.brand_name,
        )
    return list(by_key.values())


def _raw_products(row: sqlite3.Row) -> list[str]:
    raw = _loads(row["products_json"])
    if isinstance(raw, list):
        items = [str(item).strip() for item in raw if str(item).strip()]
        if items:
            return _unique(items)
    return _unique([item.strip() for item in (row["products_text"] or "").split(",") if item.strip()])


def _reference_search_queries_for_row(
    row: sqlite3.Row,
    products: list[str],
    crawler_config: EntityCrawlerConfig,
) -> list[str]:
    if not crawler_config.crawler.reference_search_enabled:
        return []
    brand = _brand(row)
    advertiser = _advertiser(row) or _parent_company(row)
    queries: list[str] = []
    product_values = products or [""]
    for product in product_values[: max(crawler_config.crawler.max_reference_results_per_ad, 1)]:
        queries.extend(
            build_reference_search_queries(
                crawler_config,
                product_name=product or None,
                brand=brand,
                advertiser=advertiser,
                ad_id=str(row["id"]),
            )
        )
    return _unique(queries)[: crawler_config.crawler.max_queries_per_run]


def _web_targets(
    row: sqlite3.Row, crawler_config: EntityCrawlerConfig
) -> list[SubmittedAdWebTarget]:
    ad_id = str(row["id"])
    targets: list[SubmittedAdWebTarget] = []
    landing = _loads(row["landing_page_json"])
    if isinstance(landing, dict):
        targets.extend(
            _target_from_value(
                ad_id,
                landing.get("url") or landing.get("domain"),
                "landing_page_json",
                _first_evidence_text(landing),
            )
        )
    contact_points = _loads(row["contact_points_json"])
    websites = contact_points.get("websites") if isinstance(contact_points, dict) else None
    if isinstance(websites, list):
        for website in websites:
            if not isinstance(website, dict):
                continue
            targets.extend(
                _target_from_value(
                    ad_id,
                    website.get("url") or website.get("domain"),
                    "contact_points_json",
                    _first_evidence_text(website),
                )
            )
    targets.extend(_target_from_value(ad_id, row["website_domain"], "ads.website_domain", None))
    targets.extend(
        _target_from_value(ad_id, row["landing_page_domain"], "ads.landing_page_domain", None)
    )
    return [
        target
        for target in targets
        if _target_matches_ad_context(target, row, crawler_config)
    ]


def _target_from_value(
    ad_id: str, value: object, source: str, evidence_text: str | None
) -> list[SubmittedAdWebTarget]:
    url = _normalize_url(str(value or ""))
    if url is None:
        return []
    parsed = urlparse(url)
    return [
        SubmittedAdWebTarget(
            ad_id=ad_id,
            url=url,
            domain=parsed.netloc.lower() or None,
            source=source,
            evidence_text=evidence_text,
        )
    ]


def _dedupe_targets_for_ad(
    targets: list[SubmittedAdWebTarget], *, max_targets: int
) -> list[SubmittedAdWebTarget]:
    best_by_key: dict[str, SubmittedAdWebTarget] = {}
    for target in targets:
        key = _target_dedupe_key(target.url)
        current = best_by_key.get(key)
        if current is None or _target_source_priority(target.source) < _target_source_priority(
            current.source
        ):
            best_by_key[key] = target
    return sorted(
        best_by_key.values(),
        key=lambda target: (
            _target_source_priority(target.source),
            _target_dedupe_key(target.url),
        ),
    )[:max_targets]


def _target_dedupe_key(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{domain}{path}".lower()


def _target_source_priority(source: str) -> int:
    priorities = {
        "ads.landing_page_domain": 0,
        "landing_page_json": 1,
        "ads.website_domain": 2,
        "contact_points_json": 3,
    }
    return priorities.get(source, 10)


def _target_matches_ad_context(
    target: SubmittedAdWebTarget,
    row: sqlite3.Row,
    crawler_config: EntityCrawlerConfig,
) -> bool:
    if not crawler_config.crawler.require_context_match_for_ad_targets:
        return True
    domain_key = _domain_key(target.domain or target.url)
    if not domain_key:
        return False
    context_keys = _target_context_keys(row, crawler_config)
    if any(key in domain_key or domain_key in key for key in context_keys):
        return True
    return _evidence_has_ad_cta(target.evidence_text or "", crawler_config)


def _target_context_keys(
    row: sqlite3.Row, crawler_config: EntityCrawlerConfig
) -> set[str]:
    values = [
        _brand(row),
        _advertiser(row),
        *_raw_products(row),
    ]
    keys: set[str] = set()
    for value in values:
        normalized = normalize_name(value or "")
        compact = normalized.replace(" ", "")
        if _usable_target_key(compact, crawler_config):
            keys.add(compact)
        for token in normalized.split():
            if _usable_target_key(token, crawler_config):
                keys.add(token)
    return keys


def _usable_target_key(value: str, crawler_config: EntityCrawlerConfig) -> bool:
    if len(value) < crawler_config.crawler.target_context_min_chars:
        return False
    stopwords = {normalize_name(item).replace(" ", "") for item in crawler_config.crawler.target_context_stopwords}
    return value not in stopwords


def _domain_key(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    domain = (parsed.netloc or value).lower().removeprefix("www.")
    without_suffix = domain.split(":")[0]
    parts = without_suffix.split(".")
    if len(parts) > 1:
        without_suffix = ".".join(parts[:-1])
    return normalize_name(without_suffix).replace(" ", "")


def _evidence_has_ad_cta(text: str, crawler_config: EntityCrawlerConfig) -> bool:
    if not crawler_config.crawler.allow_cta_evidence_targets:
        return False
    normalized = normalize_name(text)
    if not normalized:
        return False
    phrases = [normalize_name(item) for item in crawler_config.crawler.target_evidence_cta_phrases]
    return any(phrase and phrase in normalized for phrase in phrases)


def _normalize_url(value: str) -> str | None:
    text = value.strip().strip('"').strip("'").strip()
    if not text:
        return None
    if not text.lower().startswith(("http://", "https://")):
        text = f"https://{text}"
    parsed = urlparse(text)
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _first_evidence_text(value: dict[str, Any]) -> str | None:
    evidence = value.get("evidence")
    if not isinstance(evidence, list):
        return None
    for item in evidence:
        if isinstance(item, dict) and item.get("text"):
            return str(item["text"])
    return None


def _brand(row: sqlite3.Row) -> str | None:
    if row["brand_name"]:
        return str(row["brand_name"])
    brand = _loads(row["brand_json"])
    if isinstance(brand, dict) and brand.get("name"):
        return str(brand["name"])
    return None


def _context_names(row: sqlite3.Row) -> list[str]:
    values = [
        _brand(row),
        _advertiser(row),
        _parent_company(row),
    ]
    return _unique([str(value) for value in values if value])


def _collapse_global_observation_variants(
    observations: list[SubmittedAdObservation], crawler_config: EntityCrawlerConfig
) -> list[SubmittedAdObservation]:
    if not crawler_config.resolver.collapse_variants_when_base_observed:
        return observations
    collapsed: list[SubmittedAdObservation] = []
    for observation in observations:
        base = _best_global_base_observation(observation, observations, crawler_config)
        if base is None:
            collapsed.append(observation)
            continue
        aliases = _unique(
            [
                *base.original_product_names,
                base.product_name,
                *observation.original_product_names,
                observation.product_name,
            ]
        )
        collapsed.append(
            observation.model_copy(
                update={
                    "product_name": base.product_name,
                    "original_product_names": aliases,
                    "brand_name": base.brand_name or observation.brand_name,
                }
            )
        )
    return _merge_duplicate_observations(collapsed)


def _best_global_base_observation(
    observation: SubmittedAdObservation,
    observations: list[SubmittedAdObservation],
    crawler_config: EntityCrawlerConfig,
) -> SubmittedAdObservation | None:
    candidates = [
        candidate
        for candidate in observations
        if _can_be_global_base(observation, candidate, crawler_config)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(normalize_name(item.product_name)))


def _can_be_global_base(
    observation: SubmittedAdObservation,
    candidate: SubmittedAdObservation,
    crawler_config: EntityCrawlerConfig,
) -> bool:
    if not _brand_compatible(observation.brand_name, candidate.brand_name):
        return False
    return is_product_variant_of_base(observation.product_name, candidate.product_name, crawler_config)


def _merge_duplicate_observations(
    observations: list[SubmittedAdObservation],
) -> list[SubmittedAdObservation]:
    by_key: dict[tuple[str, str], SubmittedAdObservation] = {}
    for observation in observations:
        key = (observation.ad_id, normalize_name(observation.product_name))
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = observation
            continue
        aliases = _unique(
            [
                *existing.original_product_names,
                existing.product_name,
                *observation.original_product_names,
                observation.product_name,
            ]
        )
        by_key[key] = existing.model_copy(update={"original_product_names": aliases})
    return list(by_key.values())


def _brand_compatible(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    return normalize_name(left) == normalize_name(right)


def _advertiser(row: sqlite3.Row) -> str | None:
    if row["advertiser_name"]:
        return str(row["advertiser_name"])
    advertiser = _loads(row["advertiser_json"])
    if isinstance(advertiser, dict) and advertiser.get("advertiser_name"):
        return str(advertiser["advertiser_name"])
    return None


def _parent_company(row: sqlite3.Row) -> str | None:
    advertiser = _loads(row["advertiser_json"])
    if isinstance(advertiser, dict) and advertiser.get("parent_company"):
        return str(advertiser["parent_company"])
    return None


def _best_evidence(conn: sqlite3.Connection, ad_id: str, products: list[str]) -> dict[str, Any]:
    for product in _unique([item for item in products if item]):
        evidence = _best_evidence_for_product(conn, ad_id, product)
        if evidence:
            return evidence
    fallback = products[0] if products else "unknown product"
    return {
        "source": "marketing_entities",
        "text": f"Product extracted from submitted ad record: {fallback}",
        "time_ms": None,
        "frame_index": None,
    }


def _best_evidence_for_product(conn: sqlite3.Connection, ad_id: str, product: str) -> dict[str, Any] | None:
    pattern = f"%{product}%"
    ocr = conn.execute(
        """
        SELECT f.time_ms, f.frame_index, o.text, o.confidence
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE f.ad_id = ? AND o.text LIKE ?
        ORDER BY coalesce(o.confidence, 0) DESC, f.time_ms
        LIMIT 1
        """,
        (ad_id, pattern),
    ).fetchone()
    if ocr:
        return {
            "source": "ocr",
            "text": ocr["text"],
            "time_ms": ocr["time_ms"],
            "frame_index": ocr["frame_index"],
        }
    transcript = conn.execute(
        """
        SELECT start_ms, text, confidence
        FROM transcript_segments
        WHERE ad_id = ? AND text LIKE ?
        ORDER BY coalesce(confidence, 0) DESC, start_ms
        LIMIT 1
        """,
        (ad_id, pattern),
    ).fetchone()
    if transcript:
        return {
            "source": "transcript",
            "text": transcript["text"],
            "time_ms": transcript["start_ms"],
            "frame_index": None,
        }
    return None


def _observation_confidence(row: sqlite3.Row, evidence: dict[str, Any]) -> float:
    if evidence["source"] in {"ocr", "transcript"} and _brand(row):
        return 0.88
    if _brand(row):
        return 0.78
    return 0.52


def _content_names(raw: str | None) -> list[str]:
    if not raw:
        return []
    return _unique([item.strip() for item in raw.split("|") if item.strip()])


def _csv(raw: str | None) -> list[str]:
    return _unique([item.strip() for item in (raw or "").split(",") if item.strip()])


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
