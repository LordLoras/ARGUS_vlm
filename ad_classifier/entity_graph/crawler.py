from __future__ import annotations

import html as html_lib
import re
import ssl
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from ad_classifier.entity_graph import rows
from ad_classifier.entity_graph.crawler_config import (
    EntityCrawlerConfig,
    build_reference_search_queries,
)
from ad_classifier.entity_graph.discovery_vlm import (
    DiscoveryVerifier,
    DiscoveryVLMResult,
    VLMDiscoveryVerifier,
)
from ad_classifier.entity_graph.models import (
    CrawlerItem,
    CrawlerRerunMode,
    CrawlerResult,
    EntityNode,
    EntityStatus,
    RelatedAdSummary,
    SubmittedAdObservation,
    SubmittedAdWebTarget,
)
from ad_classifier.entity_graph.repository import EntityGraphRepository
from ad_classifier.entity_graph.submitted_ads import SubmittedAdReadOnlyRepository
from ad_classifier.entity_graph.taxonomy_alignment import TaxonomyAligner
from ad_classifier.entity_graph.utils import normalize_name


@dataclass(frozen=True)
class PageLink:
    url: str
    text: str


@dataclass(frozen=True)
class FetchedPage:
    url: str
    final_url: str
    status_code: int
    title: str | None
    description: str | None
    text: str
    fetcher: str
    links: list[PageLink] = field(default_factory=list)


class PageFetcher(Protocol):
    def fetch(self, target: SubmittedAdWebTarget, config: EntityCrawlerConfig) -> FetchedPage:
        ...


class EntityWebCrawler:
    def __init__(
        self,
        graph: EntityGraphRepository,
        submitted_ads: SubmittedAdReadOnlyRepository,
        crawler_config: EntityCrawlerConfig,
        *,
        fetcher: PageFetcher | None = None,
        verifier: DiscoveryVerifier | None = None,
        taxonomy_aligner: TaxonomyAligner | None = None,
    ) -> None:
        self.graph = graph
        self.submitted_ads = submitted_ads
        self.crawler_config = crawler_config
        self.fetcher = fetcher or DefaultPageFetcher()
        self.verifier = verifier
        if verifier is None and crawler_config.vlm_parse.enabled:
            self.verifier = VLMDiscoveryVerifier(crawler_config.vlm_parse)
        self.taxonomy_aligner = taxonomy_aligner or TaxonomyAligner(crawler_config)

    def run(
        self,
        *,
        limit: int = 100,
        ad_ids: list[str] | None = None,
        extra_targets: list[SubmittedAdWebTarget] | None = None,
        rerun_mode: CrawlerRerunMode = "rerun_crawled",
    ) -> CrawlerResult:
        targets = [
            *self.submitted_ads.list_web_targets(limit=limit, ad_ids=ad_ids),
            *(extra_targets or []),
        ]
        items: list[CrawlerItem] = []
        observation_count = 0
        suggestion_count_total = 0
        if not self.crawler_config.crawler.enabled or self.crawler_config.crawler.provider == "disabled":
            return CrawlerResult(
                rerun_mode=rerun_mode,
                skipped_count=len(targets),
                items=[
                    CrawlerItem(
                        ad_id=target.ad_id,
                        url=target.url,
                        status="skipped",
                        reason="crawler disabled",
                        target_source=target.source,
                        target_evidence_text=target.evidence_text,
                    )
                    for target in targets
                ],
            )

        with self.graph.connect() as conn:
            target_ad_ids = _target_ad_ids(ad_ids, targets)
            refreshed_ad_count = 0
            if rerun_mode == "refresh":
                refreshed_ad_count = self.graph.clear_crawl_artifacts(conn, target_ad_ids)
            _ensure_submitted_product_nodes(
                self.graph,
                self.submitted_ads,
                conn,
                target_ad_ids,
                limit=max(limit, len(target_ad_ids) * 8),
            )
            search_ad_ids = ad_ids
            if rerun_mode == "skip_crawled":
                targets, skipped_ad_ids = _skip_already_crawled_targets(
                    self.graph,
                    conn,
                    targets,
                    target_ad_ids,
                )
                if skipped_ad_ids:
                    search_ad_ids = [
                        ad_id for ad_id in (ad_ids or target_ad_ids) if ad_id not in skipped_ad_ids
                    ]
                    items.extend(
                        CrawlerItem(
                            ad_id=ad_id,
                            url="",
                            status="skipped",
                            reason="already crawled; choose rerun or refresh mode to crawl again",
                        )
                        for ad_id in sorted(skipped_ad_ids)
                    )
            targets = _with_reference_search_targets(conn, targets, search_ad_ids, self.crawler_config)
            pending_targets = _dedupe_targets(
                targets,
                max_targets=self.crawler_config.crawler.max_targets_per_ad,
            )
            visited_keys: set[str] = set()
            visited_count_by_ad: dict[str, int] = {}
            while pending_targets:
                target = pending_targets.pop(0)
                target_key = f"{target.ad_id}:{_target_key(target.url)}"
                if target_key in visited_keys:
                    continue
                visited_keys.add(target_key)
                visited_count_by_ad[target.ad_id] = visited_count_by_ad.get(target.ad_id, 0) + 1
                if not _domain_allowed(target.domain, self.crawler_config):
                    items.append(
                        CrawlerItem(
                            ad_id=target.ad_id,
                            url=target.url,
                            status="skipped",
                            reason="domain blocked by crawler config",
                            target_source=target.source,
                            target_evidence_text=target.evidence_text,
                        )
                    )
                    continue

                products = _products_for_ad(conn, target.ad_id)
                if not products:
                    items.append(
                        CrawlerItem(
                            ad_id=target.ad_id,
                            url=target.url,
                            status="skipped",
                            reason="no product nodes linked to submitted ad",
                            target_source=target.source,
                            target_evidence_text=target.evidence_text,
                        )
                    )
                    continue

                try:
                    page = self.fetcher.fetch(target, self.crawler_config)
                except Exception as exc:  # pragma: no cover - exception type depends on transport
                    items.append(
                        CrawlerItem(
                            ad_id=target.ad_id,
                            url=target.url,
                            status="failed",
                            reason=str(exc)[:240],
                            target_source=target.source,
                            target_evidence_text=target.evidence_text,
                        )
                    )
                    continue

                deterministic_matches: list[tuple[EntityNode, str]] = []
                for product in products:
                    aliases = _aliases_for_node(conn, product.id)
                    match = _first_match(page, [product.canonical_name, *aliases])
                    if match is None:
                        continue
                    deterministic_matches.append((product, match))

                source_id = None
                matched: list[str] = []
                vlm_result = None
                vlm_error = None
                submitted_ad = _submitted_ad_summary(self.submitted_ads, target.ad_id)
                if self.verifier is not None:
                    try:
                        vlm_result = self.verifier.verify(
                            source_url=target.url,
                            final_url=page.final_url,
                            title=page.title,
                            description=page.description,
                            text=page.text,
                            products=products,
                            submitted_ad=submitted_ad,
                        )
                    except Exception as exc:  # pragma: no cover - provider dependent
                        vlm_error = str(exc)[:500]

                if deterministic_matches or _has_vlm_payload(vlm_result) or vlm_error:
                    source = self.graph.upsert_source(
                        conn,
                        source_type=self.crawler_config.discovery_source_type,
                        label=f"Website discovery for {target.ad_id}",
                        url=target.url,
                        ad_id=target.ad_id,
                        payload={
                            "target_source": target.source,
                            "evidence_text": target.evidence_text,
                            "status": "matched",
                            "title": page.title,
                            "final_url": page.final_url,
                            "fetcher": page.fetcher,
                            "search_only_can_confirm": self.crawler_config.search_only_can_confirm,
                            "vlm_parse": self.crawler_config.vlm_parse.model_dump(mode="json"),
                            "vlm_result": vlm_result.model_dump(mode="json") if vlm_result else None,
                            "vlm_error": vlm_error,
                        },
                    )
                    source_id = source.id

                for product, match in deterministic_matches:
                    self.graph.upsert_observation(
                        conn,
                        node_id=product.id,
                        ad_id=target.ad_id,
                        field="web_discovery",
                        evidence_text=match,
                        source="web_crawl",
                        confidence=0.30,
                        source_id=source_id,
                    )
                    observation_count += 1
                    matched.append(product.canonical_name)
                if vlm_result is not None and source_id is not None:
                    written = _write_vlm_discovery(
                        self.graph,
                        conn,
                        products=products,
                        result=vlm_result,
                        ad_id=target.ad_id,
                        source_id=source_id,
                        submitted_ad=submitted_ad,
                        config=self.crawler_config,
                        taxonomy_aligner=self.taxonomy_aligner,
                    )
                    observation_count += written[0]
                    suggestion_count_total += written[1]
                    matched.extend(_matched_vlm_product_names(products, vlm_result))
                    pending_targets.extend(
                        [
                            *_product_followup_targets(
                                target=target,
                                page=page,
                                products=products,
                                result=vlm_result,
                                config=self.crawler_config,
                                visited_count=visited_count_by_ad[target.ad_id],
                            ),
                            *_brand_context_followup_targets(
                                target=target,
                                page=page,
                                result=vlm_result,
                                config=self.crawler_config,
                                visited_count=visited_count_by_ad[target.ad_id],
                            ),
                        ]
                    )
                    pending_targets = _dedupe_targets(
                        pending_targets,
                        max_targets=self.crawler_config.crawler.max_targets_per_ad,
                    )

                items.append(
                    CrawlerItem(
                        ad_id=target.ad_id,
                        url=target.url,
                        status="visited",
                        source_id=source_id,
                        matched_products=_unique_names(matched),
                        title=page.title,
                        final_url=page.final_url,
                        reason=_crawl_reason(vlm_error),
                        target_source=target.source,
                        target_evidence_text=target.evidence_text,
                    )
                )
            conn.commit()

        return CrawlerResult(
            rerun_mode=rerun_mode,
            refreshed_ad_count=refreshed_ad_count if rerun_mode == "refresh" else 0,
            visited_count=sum(1 for item in items if item.status == "visited"),
            skipped_count=sum(1 for item in items if item.status == "skipped"),
            failed_count=sum(1 for item in items if item.status == "failed"),
            observation_count=observation_count,
            suggestion_count=suggestion_count_total,
            items=items,
        )


def _target_ad_ids(
    ad_ids: list[str] | None,
    targets: list[SubmittedAdWebTarget],
) -> list[str]:
    values = [*(ad_ids or []), *(target.ad_id for target in targets)]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        ad_id = value.strip()
        if not ad_id or ad_id in seen:
            continue
        seen.add(ad_id)
        result.append(ad_id)
    return result


def _ensure_submitted_product_nodes(
    graph: EntityGraphRepository,
    submitted_ads: SubmittedAdReadOnlyRepository,
    conn,
    ad_ids: list[str],
    *,
    limit: int,
) -> None:
    if not ad_ids:
        return
    observations = submitted_ads.list_product_observations(limit=limit, ad_ids=ad_ids)
    for obs in observations:
        _seed_submitted_product_node(graph, conn, obs)


def _seed_submitted_product_node(
    graph: EntityGraphRepository,
    conn,
    obs: SubmittedAdObservation,
) -> None:
    status = "confirmed_unreviewed" if obs.confidence >= 0.75 else "candidate"
    source = graph.upsert_source(
        conn,
        source_type="submitted_ad",
        label=f"Submitted ad {obs.ad_id}",
        ad_id=obs.ad_id,
        payload={
            "product": obs.product_name,
            "original_products": obs.original_product_names,
            "submitted_brand": obs.brand_name,
            "evidence_source": obs.evidence_source,
            "seeded_by": "crawler_run",
        },
        source_id=f"src_crawler_seed_{obs.ad_id}_{normalize_name(obs.product_name).replace(' ', '_')[:48]}",
    )
    product, _created = graph.upsert_node(
        conn,
        entity_type="product",
        canonical_name=obs.product_name,
        status=status,
        confidence=obs.confidence,
        description=(
            f"{obs.product_name} is a submitted ad product mention seeded for crawler "
            "verification."
        ),
        generated_from={"source": "submitted_ad", "seeded_by": "crawler_run"},
    )
    for alias in [obs.product_name, *obs.original_product_names]:
        if not alias.strip():
            continue
        graph.upsert_alias(
            conn,
            node_id=product.id,
            alias=alias,
            source_id=source.id,
            status=status,
            confidence=obs.confidence,
        )
    graph.upsert_observation(
        conn,
        node_id=product.id,
        ad_id=obs.ad_id,
        field="product",
        evidence_text=obs.evidence_text or obs.product_name,
        source=obs.evidence_source,
        confidence=obs.confidence,
        source_id=source.id,
        time_ms=obs.time_ms,
        frame_index=obs.frame_index,
    )
    ad_node, _ad_created = graph.upsert_node(
        conn,
        entity_type="ad",
        canonical_name=obs.ad_id,
        status="confirmed_unreviewed",
        confidence=1.0,
    )
    graph.upsert_edge(
        conn,
        source_node_id=product.id,
        target_node_id=ad_node.id,
        relation="MENTIONED_IN_AD",
        confidence=obs.confidence,
        status=status,
        source_id=source.id,
    )


def _with_reference_search_targets(
    conn,
    targets: list[SubmittedAdWebTarget],
    ad_ids: list[str] | None,
    config: EntityCrawlerConfig,
) -> list[SubmittedAdWebTarget]:
    if not ad_ids or not config.crawler.reference_search_enabled:
        return targets
    extra: list[SubmittedAdWebTarget] = []
    queries_used = 0
    for ad_id in ad_ids:
        if queries_used >= config.crawler.max_queries_per_run:
            break
        products = _products_for_ad(conn, ad_id)
        for product in products[: max(config.crawler.max_reference_results_per_ad, 1)]:
            if queries_used >= config.crawler.max_queries_per_run:
                break
            for query in _reference_queries(conn, ad_id, product, config):
                if queries_used >= config.crawler.max_queries_per_run:
                    break
                try:
                    urls = _duckduckgo_urls(query, config)
                except Exception:
                    urls = []
                queries_used += 1
                target_source = "reference_search"
                evidence_text = f"Reference search query: {query}"
                if not urls:
                    context = _submitted_source_context(conn, ad_id)
                    urls = _fallback_reference_urls(
                        product_name=product.canonical_name,
                        brand=_brand_for_product(conn, product.id) or context.get("submitted_brand"),
                        advertiser=context.get("advertiser_name") or context.get("parent_company"),
                    )
                    target_source = "reference_search_fallback"
                    evidence_text = (
                        "DuckDuckGo returned no parseable result URLs; generated local "
                        f"official-domain candidates for query: {query}"
                    )
                for url in urls[: config.crawler.max_reference_results_per_ad]:
                    parsed = urlparse(url)
                    extra.append(
                        SubmittedAdWebTarget(
                            ad_id=ad_id,
                            url=url,
                            domain=parsed.netloc.lower() or None,
                            source=target_source,
                            evidence_text=evidence_text,
                        )
                    )
    return _dedupe_targets([*targets, *extra], max_targets=config.crawler.max_targets_per_ad)


def _skip_already_crawled_targets(
    graph: EntityGraphRepository,
    conn,
    targets: list[SubmittedAdWebTarget],
    ad_ids: list[str],
) -> tuple[list[SubmittedAdWebTarget], set[str]]:
    metadata = graph.crawl_queue_metadata(conn, ad_ids)
    explicit_ad_ids = {target.ad_id for target in targets if target.source == "explicit_reference"}
    skipped_ad_ids = {
        ad_id
        for ad_id in ad_ids
        if int(metadata.get(ad_id, {}).get("crawled_source_count") or 0) > 0
        and ad_id not in explicit_ad_ids
    }
    if not skipped_ad_ids:
        return targets, set()
    return [target for target in targets if target.ad_id not in skipped_ad_ids], skipped_ad_ids


def _reference_queries(
    conn,
    ad_id: str,
    product: EntityNode,
    config: EntityCrawlerConfig,
) -> list[str]:
    context = _submitted_source_context(conn, ad_id)
    brand = _brand_for_product(conn, product.id) or context.get("submitted_brand") or ""
    advertiser = context.get("advertiser_name") or context.get("parent_company") or ""
    return build_reference_search_queries(
        config,
        product_name=product.canonical_name,
        brand=brand,
        advertiser=advertiser,
        ad_id=ad_id,
    )


def _submitted_source_context(conn, ad_id: str) -> dict[str, str]:
    row = conn.execute(
        """
        SELECT payload_json
        FROM entity_sources
        WHERE source_type = 'submitted_ad' AND ad_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (ad_id,),
    ).fetchone()
    payload = rows.loads_dict(row["payload_json"]) if row else {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: str(value)
        for key, value in payload.items()
        if key in {"submitted_brand", "advertiser_name", "parent_company"} and value
    }


def _brand_for_product(conn, product_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT b.canonical_name
        FROM entity_edges e
        JOIN entity_nodes b ON b.id = e.target_node_id
        WHERE e.source_node_id = ?
          AND e.relation = 'BRANDED_BY'
          AND e.status <> 'rejected'
          AND b.status <> 'rejected'
        ORDER BY e.confidence DESC, b.canonical_name
        LIMIT 1
        """,
        (product_id,),
    ).fetchone()
    return str(row["canonical_name"]) if row else None


def _fallback_reference_urls(
    *,
    product_name: str,
    brand: str | None,
    advertiser: str | None,
) -> list[str]:
    domains = _official_domain_candidates(brand) or _official_domain_candidates(advertiser)
    if not domains:
        return []
    product_paths = _product_path_candidates(product_name)
    urls: list[str] = []
    for domain in domains:
        urls.append(f"https://{domain}/")
        for path in product_paths:
            urls.append(f"https://{domain}/{path}/")
    return _unique_names(urls)


def _official_domain_candidates(value: str | None) -> list[str]:
    key = normalize_name(value or "")
    if not key:
        return []
    drop_words = {
        "inc",
        "incorporated",
        "llc",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "company",
        "co",
        "the",
    }
    words = [word for word in key.split() if word not in drop_words]
    compact = "".join(words)
    if len(compact) < 3:
        return []
    return [f"www.{compact}.com", f"{compact}.com"]


def _product_path_candidates(product_name: str) -> list[str]:
    slug = re.sub(r"[^a-z0-9]+", "-", product_name.lower()).strip("-")
    compact = re.sub(r"[^a-z0-9]+", "", product_name.lower()).strip()
    values = [slug, compact]
    return [value for value in _unique_names(values) if value]


def _product_followup_targets(
    *,
    target: SubmittedAdWebTarget,
    page: FetchedPage,
    products: list[EntityNode],
    result: DiscoveryVLMResult,
    config: EntityCrawlerConfig,
    visited_count: int,
) -> list[SubmittedAdWebTarget]:
    if not config.crawler.follow_product_links:
        return []
    if config.crawler.max_pages_per_entity <= 0:
        return []
    if visited_count >= config.crawler.max_pages_per_entity:
        return []
    if result.source_kind not in set(config.crawler.recursive_source_kinds):
        return []

    base_domain = _normalize_domain(page.final_url or target.url)
    followups: list[SubmittedAdWebTarget] = []
    seen: set[str] = set()
    for link in page.links:
        resolved = urljoin(page.final_url or target.url, link.url)
        parsed = urlparse(resolved)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if _normalize_domain(parsed.netloc) != base_domain:
            continue
        if not _link_matches_product(link, resolved, products):
            continue
        key = _target_key(resolved)
        if key in seen or key == _target_key(page.final_url or target.url):
            continue
        seen.add(key)
        followups.append(
            SubmittedAdWebTarget(
                ad_id=target.ad_id,
                url=resolved,
                domain=parsed.netloc.lower() or None,
                source="product_page_followup",
                evidence_text=(
                    f"Product page follow-up from {page.final_url or target.url}: "
                    f"{link.text or parsed.path}"
                ),
            )
        )
        if len(followups) >= config.crawler.max_followup_links_per_page:
            break
    return followups


def _brand_context_followup_targets(
    *,
    target: SubmittedAdWebTarget,
    page: FetchedPage,
    result: DiscoveryVLMResult,
    config: EntityCrawlerConfig,
    visited_count: int,
) -> list[SubmittedAdWebTarget]:
    if not config.crawler.follow_brand_context_links:
        return []
    if config.crawler.max_pages_per_entity <= 0:
        return []
    if visited_count >= config.crawler.max_pages_per_entity:
        return []
    if result.source_kind not in set(config.crawler.recursive_source_kinds):
        return []

    base_domain = _normalize_domain(page.final_url or target.url)
    followups: list[SubmittedAdWebTarget] = []
    seen: set[str] = set()
    for link in page.links:
        resolved = urljoin(page.final_url or target.url, link.url)
        parsed = urlparse(resolved)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if _normalize_domain(parsed.netloc) != base_domain:
            continue
        if not _link_matches_brand_context(link, resolved, config):
            continue
        key = _target_key(resolved)
        if key in seen or key == _target_key(page.final_url or target.url):
            continue
        seen.add(key)
        followups.append(
            SubmittedAdWebTarget(
                ad_id=target.ad_id,
                url=resolved,
                domain=parsed.netloc.lower() or None,
                source="brand_context_followup",
                evidence_text=(
                    f"Brand context follow-up from {page.final_url or target.url}: "
                    f"{link.text or parsed.path}"
                ),
            )
        )
        if len(followups) >= config.crawler.max_brand_context_links_per_page:
            break
    return followups


def _link_matches_product(link: PageLink, url: str, products: list[EntityNode]) -> bool:
    parsed = urlparse(url)
    link_context = normalize_name(" ".join([link.text, parsed.path.replace("-", " ")]))
    if not link_context:
        return False
    for product in products:
        product_key = normalize_name(product.canonical_name)
        if product_key and (product_key in link_context or link_context in product_key):
            return True
    return False


def _link_matches_brand_context(
    link: PageLink, url: str, config: EntityCrawlerConfig
) -> bool:
    parsed = urlparse(url)
    link_context = normalize_name(" ".join([link.text, parsed.path.replace("-", " ")]))
    if not link_context:
        return False
    terms = [normalize_name(term) for term in config.crawler.brand_context_link_terms]
    return any(term and term in link_context for term in terms)


def _duckduckgo_urls(query: str, config: EntityCrawlerConfig) -> list[str]:
    endpoint = config.crawler.reference_search_endpoint
    url = f"{endpoint}?{urlencode({'q': query})}"
    request = urllib.request.Request(
        url,
        headers=_http_headers(config),
        method="GET",
    )
    with urllib.request.urlopen(
        request,
        timeout=config.crawler.timeout_s,
        context=_ssl_context(),
    ) as response:
        html = response.read(250_000).decode("utf-8", errors="replace")
    parser = _SearchResultParser()
    parser.feed(html)
    return parser.urls


def _dedupe_targets(
    targets: list[SubmittedAdWebTarget], *, max_targets: int
) -> list[SubmittedAdWebTarget]:
    grouped: dict[str, list[SubmittedAdWebTarget]] = {}
    for target in targets:
        grouped.setdefault(target.ad_id, []).append(target)
    result: list[SubmittedAdWebTarget] = []
    for ad_targets in grouped.values():
        by_url: dict[str, SubmittedAdWebTarget] = {}
        for target in ad_targets:
            key = _target_key(target.url)
            current = by_url.get(key)
            if current is None or _crawler_target_priority(target.source) < _crawler_target_priority(
                current.source
            ):
                by_url[key] = target
        ordered = sorted(
            by_url.values(),
            key=lambda target: (
                _crawler_target_priority(target.source),
                _target_key(target.url),
            ),
        )
        result.extend(ordered[:max_targets])
    return result


def _crawler_target_priority(source: str) -> int:
    priorities = {
        "explicit_reference": 0,
        "product_page_followup": 1,
        "reference_search": 2,
        "reference_search_fallback": 3,
        "landing_page_json": 4,
        "ads.landing_page_domain": 5,
        "ads.website_domain": 6,
        "contact_points_json": 7,
        "brand_context_followup": 8,
    }
    return priorities.get(source, 20)


class DefaultPageFetcher:
    def fetch(self, target: SubmittedAdWebTarget, config: EntityCrawlerConfig) -> FetchedPage:
        if config.crawler.provider == "browser":
            page = _fetch_with_browser(target.url, config)
            _raise_if_unusable_page(page)
            return page
        try:
            page = _fetch_with_http(target.url, config)
        except Exception as http_exc:
            if config.crawler.use_browser_fallback:
                try:
                    page = _fetch_with_browser(target.url, config)
                    _raise_if_unusable_page(page)
                    return page
                except Exception as browser_exc:
                    raise RuntimeError(
                        f"http fetch failed: {http_exc}; browser fallback failed: {browser_exc}"
                    ) from browser_exc
            raise
        needs_fallback = len(page.text) < 200 or _looks_blocked_or_challenged(page) or _is_4xx_page(page)
        if needs_fallback and config.crawler.use_browser_fallback:
            try:
                browser_page = _fetch_with_browser(target.url, config)
                _raise_if_unusable_page(browser_page)
                return browser_page
            except Exception as browser_exc:
                if _looks_blocked_or_challenged(page):
                    raise RuntimeError(
                        "http fetch returned a blocked/challenge page; "
                        f"browser fallback failed: {browser_exc}"
                    ) from browser_exc
                if _is_4xx_page(page):
                    raise RuntimeError(
                        f"http fetch returned HTTP {page.status_code}; "
                        f"browser fallback failed: {browser_exc}"
                    ) from browser_exc
                return page
        _raise_if_unusable_page(page)
        return page


def _fetch_with_http(url: str, config: EntityCrawlerConfig) -> FetchedPage:
    request = urllib.request.Request(
        url,
        headers=_http_headers(config),
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=config.crawler.timeout_s,
            context=_ssl_context(),
        ) as response:
            raw = response.read(config.crawler.max_page_bytes)
            final_url = response.geturl()
            status_code = int(getattr(response, "status", 200))
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read(min(config.crawler.max_page_bytes, 500_000))
        final_url = exc.geturl()
        status_code = int(exc.code)
        content_type = exc.headers.get("content-type", "")
    encoding = "utf-8"
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.I)
    if match:
        encoding = match.group(1)
    html = raw.decode(encoding, errors="replace")
    parsed = _parse_html(html)
    return FetchedPage(
        url=url,
        final_url=final_url,
        status_code=status_code,
        title=parsed.title,
        description=parsed.description,
        text=_augment_page_text(parsed.text, html),
        fetcher="http",
        links=parsed.links,
    )


def _http_headers(config: EntityCrawlerConfig) -> dict[str, str]:
    return {
        "User-Agent": config.crawler.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    }


def _looks_blocked_or_challenged(page: FetchedPage) -> bool:
    if page.status_code in {401, 403, 429}:
        return True
    haystack = normalize_name(
        " ".join(
            [
                page.title or "",
                page.description or "",
                page.text[:2000],
            ]
        )
    )
    blocked_markers = [
        "access denied",
        "attention required",
        "bot detection",
        "captcha",
        "browser challenge",
        "security challenge",
        "challenge page",
        "cloudflare",
        "forbidden",
        "permission to access",
        "request blocked",
        "temporarily unavailable due to security",
        "verify you are human",
    ]
    return any(marker in haystack for marker in blocked_markers)


def _is_4xx_page(page: FetchedPage) -> bool:
    return 400 <= page.status_code < 500


def _raise_if_unusable_page(page: FetchedPage) -> None:
    if _looks_blocked_or_challenged(page):
        title = page.title or f"HTTP {page.status_code}"
        raise RuntimeError(f"fetch returned a blocked/challenge page: {title}")
    if _is_4xx_page(page):
        title = page.title or ""
        suffix = f" ({title})" if title else ""
        raise RuntimeError(f"fetch returned HTTP {page.status_code}{suffix}")


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _fetch_with_browser(url: str, config: EntityCrawlerConfig) -> FetchedPage:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("browser fallback requested but Playwright is not installed") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=config.crawler.user_agent)
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(config.crawler.timeout_s * 1000),
            )
            with suppress(Exception):
                page.wait_for_load_state(
                    "load",
                    timeout=min(5000, max(1000, int(config.crawler.timeout_s * 1000 / 2))),
                )
            page.wait_for_timeout(750)
            html = page.content()
            parsed = _parse_html(html)
            return FetchedPage(
                url=url,
                final_url=page.url,
                status_code=response.status if response else 0,
                title=parsed.title,
                description=parsed.description,
                text=_augment_page_text(parsed.text, html),
                fetcher="browser",
                links=parsed.links,
            )
        finally:
            browser.close()


@dataclass(frozen=True)
class ParsedHtml:
    title: str | None
    description: str | None
    text: str
    links: list[PageLink]


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self._in_title = False
        self._blocked_depth = 0
        self._active_href: str | None = None
        self._active_link_text: list[str] = []
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._links: list[PageLink] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript"}:
            self._blocked_depth += 1
        if tag_name == "title":
            self._in_title = True
        if tag_name == "meta":
            values = {name.lower(): value or "" for name, value in attrs}
            if values.get("name", "").lower() == "description" and values.get("content"):
                self.description = values["content"].strip()
        if tag_name == "a":
            values = {name.lower(): value or "" for name, value in attrs}
            href = values.get("href")
            if href:
                self._active_href = href
                self._active_link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript"} and self._blocked_depth:
            self._blocked_depth -= 1
        if tag_name == "title":
            self._in_title = False
        if tag_name == "a" and self._active_href:
            text = re.sub(r"\s+", " ", " ".join(self._active_link_text)).strip()
            self._links.append(PageLink(url=self._active_href, text=text))
            self._active_href = None
            self._active_link_text = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        if self._blocked_depth == 0:
            self._text_parts.append(text)
            if self._active_href is not None:
                self._active_link_text.append(text)

    def result(self) -> ParsedHtml:
        title = " ".join(self._title_parts).strip() or None
        text = re.sub(r"\s+", " ", " ".join(self._text_parts)).strip()
        return ParsedHtml(
            title=title,
            description=self.description,
            text=text[:20_000],
            links=self._links[:500],
        )


def _parse_html(html: str) -> ParsedHtml:
    parser = _VisibleTextParser()
    parser.feed(html)
    return parser.result()


_CONTEXT_SNIPPET_TERMS = [
    "founded by",
    "founder",
    "co-founder",
    "co-owner",
    "owned by",
    "operated by",
    "legal name",
    "parent company",
    "copyright",
    "&copy;",
    "©",
]


def _augment_page_text(visible_text: str, raw_html: str) -> str:
    snippets = _html_context_snippets(raw_html)
    if not snippets:
        return visible_text
    sections = ["Context snippets:", *snippets, "Page text:", visible_text]
    return re.sub(r"\s+", " ", " ".join(sections)).strip()[:30_000]


def _html_context_snippets(raw_html: str) -> list[str]:
    snippets: list[str] = []
    seen: set[str] = set()
    for term in _CONTEXT_SNIPPET_TERMS:
        for match in re.finditer(re.escape(term), raw_html, flags=re.I):
            start = max(match.start() - 500, 0)
            end = min(match.end() + 700, len(raw_html))
            snippet = _strip_html_fragment(raw_html[start:end])
            key = normalize_name(snippet[:180])
            if not key or key in seen:
                continue
            seen.add(key)
            snippets.append(snippet[:700])
            if len(snippets) >= 8:
                return snippets
    return snippets


def _strip_html_fragment(fragment: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", fragment)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class _SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = {name.lower(): value or "" for name, value in attrs}
        href = values.get("href")
        if not href:
            return
        url = _clean_search_url(href)
        if url is None:
            return
        key = _target_key(url)
        if key in self._seen:
            return
        self._seen.add(key)
        self.urls.append(url)


def _clean_search_url(value: str) -> str | None:
    href = value.strip()
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    normalized_domain = _normalize_domain(parsed.netloc) if parsed.netloc else ""
    if href.startswith("/l/") or (normalized_domain in {"duckduckgo.com", "duck.com"} and parsed.path == "/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        href = target or href
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if _normalize_domain(parsed.netloc) in {"duckduckgo.com", "duck.com"}:
        return None
    return href


def _target_key(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc.lower().removeprefix('www.')}{parsed.path}".rstrip("/")


def _domain_allowed(domain: str | None, config: EntityCrawlerConfig) -> bool:
    if not domain:
        return False
    normalized = domain.lower().removeprefix("www.")
    blocked = [_normalize_domain(item) for item in config.crawler.blocked_domains]
    if any(normalized == item or normalized.endswith(f".{item}") for item in blocked):
        return False
    allowed = [_normalize_domain(item) for item in config.crawler.allowed_domains]
    if not allowed:
        return True
    return any(normalized == item or normalized.endswith(f".{item}") for item in allowed)


def _normalize_domain(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.netloc or value).lower().removeprefix("www.")


def _products_for_ad(conn, ad_id: str) -> list[EntityNode]:
    result = conn.execute(
        """
        SELECT DISTINCT p.*
        FROM entity_edges e
        JOIN entity_nodes p ON p.id = e.source_node_id
        JOIN entity_nodes ad ON ad.id = e.target_node_id
        WHERE e.relation = 'MENTIONED_IN_AD'
          AND p.type = 'product'
          AND p.status <> 'rejected'
          AND ad.type = 'ad'
          AND ad.canonical_name = ?
        ORDER BY p.canonical_name
        """,
        (ad_id,),
    ).fetchall()
    return [rows.node(row) for row in result]


def _has_vlm_payload(result: DiscoveryVLMResult | None) -> bool:
    if result is None:
        return False
    return bool(
        result.product_facts
        or result.aliases
        or result.taxonomy_hints
        or result.suggested_ad_changes
        or result.conflicts
        or result.warnings
    )


def _write_vlm_discovery(
    graph: EntityGraphRepository,
    conn,
    *,
    products: list[EntityNode],
    result: DiscoveryVLMResult,
    ad_id: str,
    source_id: str,
    submitted_ad: RelatedAdSummary | None,
    config: EntityCrawlerConfig,
    taxonomy_aligner: TaxonomyAligner,
) -> tuple[int, int]:
    observations = 0
    suggestions = 0
    by_name = _products_by_name(products)
    taxonomy_reset_keys: set[tuple[str, str]] = set()
    for fact in result.product_facts:
        product = _match_product(by_name, fact.matched_submitted_product, fact.product_name)
        if product is None:
            continue
        evidence_text = _evidence_text(fact.evidence_spans, fallback=fact.product_name)
        graph.upsert_observation(
            conn,
            node_id=product.id,
            ad_id=ad_id,
            field="web_vlm_product_fact",
            evidence_text=evidence_text,
            source="web_vlm",
            confidence=min(fact.confidence, 0.65),
            source_id=source_id,
        )
        observations += 1
        if fact.product_description:
            graph.upsert_observation(
                conn,
                node_id=product.id,
                ad_id=ad_id,
                field="web_vlm_product_description",
                evidence_text=_clean_description(fact.product_description) or fact.product_description,
                source="web_vlm",
                confidence=min(fact.confidence, 0.68),
                source_id=source_id,
            )
            observations += 1
        if normalize_name(fact.product_name) != normalize_name(product.canonical_name):
            graph.upsert_alias(
                conn,
                node_id=product.id,
                alias=fact.product_name,
                source_id=source_id,
                status="candidate",
                confidence=min(fact.confidence, 0.65),
            )
        if fact.brand_name:
            brand, _created = graph.upsert_node(
                conn,
                entity_type="brand",
                canonical_name=fact.brand_name,
                status="candidate",
                confidence=min(fact.confidence, 0.65),
                description=_clean_description(fact.brand_description),
                generated_from={"source": "discovery_only", "source_url": result.source_url},
            )
            graph.upsert_edge(
                conn,
                source_node_id=product.id,
                target_node_id=brand.id,
                relation="BRANDED_BY",
                confidence=min(fact.confidence, 0.65),
                status="candidate",
                source_id=source_id,
                evidence={
                    "source": "web_vlm",
                    "source_kind": result.source_kind,
                    "relation_to_page": fact.relation_to_page,
                    "warnings": fact.warnings,
                    "evidence_spans": fact.evidence_spans[:3],
                },
            )
            if fact.owner_name and _owner_supported_by_evidence(
                owner_name=fact.owner_name,
                brand_name=fact.brand_name,
                evidence_spans=fact.evidence_spans,
                source_url=result.source_url,
            ):
                owner, _owner_created = graph.upsert_node(
                    conn,
                    entity_type="company",
                    canonical_name=fact.owner_name,
                    status="candidate",
                    confidence=min(fact.confidence, 0.6),
                    description=_clean_description(fact.owner_description),
                    generated_from={"source": "discovery_only", "source_url": result.source_url},
                )
                graph.upsert_edge(
                    conn,
                    source_node_id=brand.id,
                    target_node_id=owner.id,
                    relation="OWNED_BY",
                    confidence=min(fact.confidence, 0.6),
                    status="candidate",
                    source_id=source_id,
                    evidence={
                        "source": "web_vlm",
                        "source_kind": result.source_kind,
                        "evidence_spans": fact.evidence_spans[:3],
                    },
                )
            else:
                _reject_owner_edges_for_source(conn, brand_id=brand.id, source_id=source_id)
        if fact.category_name:
            category_evidence = _category_evidence_text(fact.category_name, fact.evidence_spans)
            graph.upsert_observation(
                conn,
                node_id=product.id,
                ad_id=ad_id,
                field="web_vlm_category_hint",
                evidence_text=category_evidence,
                source="web_vlm",
                confidence=min(fact.confidence, 0.55),
                source_id=source_id,
            )
            observations += 1
            _write_taxonomy_alignments(
                graph,
                conn,
                product=product,
                fact=fact,
                source_id=source_id,
                category_evidence=category_evidence,
                taxonomy_aligner=taxonomy_aligner,
                config=config,
                reset_keys=taxonomy_reset_keys,
            )
    for alias in result.aliases:
        product = _match_product(by_name, alias.matched_submitted_product, alias.alias)
        if product is None:
            continue
        graph.upsert_alias(
            conn,
            node_id=product.id,
            alias=alias.alias,
            source_id=source_id,
            status="candidate",
            confidence=min(alias.confidence, 0.6),
        )
    for hint in result.taxonomy_hints:
        product = _match_product(by_name, hint.matched_submitted_product, hint.taxonomy_name)
        if product is None:
            continue
        graph.upsert_observation(
            conn,
            node_id=product.id,
            ad_id=ad_id,
            field="web_vlm_taxonomy_hint",
            evidence_text=_evidence_text(hint.evidence_spans, fallback=hint.taxonomy_name),
            source="web_vlm",
            confidence=min(hint.confidence, 0.55),
            source_id=source_id,
        )
        observations += 1
    for suggestion in result.suggested_ad_changes:
        current_value = suggestion.current_value
        if current_value is None and submitted_ad is not None:
            current_value = _submitted_field_value(submitted_ad, suggestion.field_path)
        if not _should_store_ad_suggestion(
            field_path=suggestion.field_path,
            current_value=current_value,
            suggested_value=suggestion.suggested_value,
            config=config,
        ):
            continue
        if not suggestion.suggested_value.strip():
            continue
        apply_safety = _ad_suggestion_apply_safety(
            field_path=suggestion.field_path,
            current_value=current_value,
            suggested_value=suggestion.suggested_value,
            apply_safety=suggestion.apply_safety,
            config=config,
        )
        reason = suggestion.reason.strip()[:1000]
        if apply_safety == "review_only" and suggestion.apply_safety == "safe_projection_update":
            reason = (
                "Review-only: discovery evidence may be narrowing a submitted product to a "
                f"web-only variant. {reason}"
            )[:1000]
        graph.upsert_ad_change_suggestion(
            conn,
            ad_id=ad_id,
            source_id=source_id,
            field_path=suggestion.field_path,
            current_value=current_value,
            suggested_value=suggestion.suggested_value.strip(),
            confidence=min(suggestion.confidence, 0.75 if apply_safety != "review_only" else 0.45),
            reason=reason,
            evidence_text=_evidence_text(
                suggestion.evidence_spans,
                fallback=suggestion.suggested_value,
            ),
            apply_safety=apply_safety,
            payload={
                "source": "web_vlm",
                "source_kind": result.source_kind,
                "source_url": result.source_url,
                "warnings": result.warnings,
            },
        )
        suggestions += 1
    return observations, suggestions


def _write_taxonomy_alignments(
    graph: EntityGraphRepository,
    conn,
    *,
    product: EntityNode,
    fact,
    source_id: str,
    category_evidence: str,
    taxonomy_aligner: TaxonomyAligner,
    config: EntityCrawlerConfig,
    reset_keys: set[tuple[str, str]],
) -> int:
    count = 0
    reset_key = (product.id, source_id)
    if reset_key not in reset_keys:
        graph.reject_taxonomy_context_for_source(conn, product_id=product.id, source_id=source_id)
        reset_keys.add(reset_key)
    alignments = taxonomy_aligner.align(
        category_name=fact.category_name,
        product_name=fact.product_name,
        brand_name=fact.brand_name,
        evidence_text=category_evidence,
    )
    for alignment in alignments:
        status: EntityStatus = "candidate"
        graph.upsert_taxonomy_mapping(
            conn,
            entity_id=product.id,
            taxonomy_type=alignment.taxonomy_type,
            taxonomy_id=alignment.taxonomy_id,
            taxonomy_name=alignment.taxonomy_name,
            confidence=min(alignment.confidence, 0.72),
            status=status,
            source_id=source_id,
            evidence_text=alignment.evidence_text,
        )
        taxonomy_node, _created = graph.upsert_node(
            conn,
            entity_type="taxonomy",
            canonical_name=_taxonomy_node_name(alignment),
            status=status,
            confidence=min(alignment.confidence, 0.72),
            generated_from={
                "source": alignment.source,
                "taxonomy_type": alignment.taxonomy_type,
                "taxonomy_id": alignment.taxonomy_id,
            },
        )
        graph.upsert_edge(
            conn,
            source_node_id=product.id,
            target_node_id=taxonomy_node.id,
            relation="MAPS_TO_TAXONOMY",
            confidence=min(alignment.confidence, 0.72),
            status=status,
            source_id=source_id,
            evidence={
                "source": alignment.source,
                "evidence_text": alignment.evidence_text,
            },
        )
        if (
            alignment.taxonomy_type == "product"
            and config.taxonomy_alignment.create_iab_category_edges
            and alignment.confidence >= config.taxonomy_alignment.min_product_confidence
        ):
            category, _category_created = graph.upsert_node(
                conn,
                entity_type="category",
                canonical_name=f"IAB Product {alignment.taxonomy_id}: {alignment.taxonomy_name}",
                status=status,
                confidence=min(alignment.confidence, 0.72),
                generated_from={
                    "source": alignment.source,
                    "taxonomy_type": "product",
                    "taxonomy_id": alignment.taxonomy_id,
                    "taxonomy_name": alignment.taxonomy_name,
                },
            )
            graph.upsert_edge(
                conn,
                source_node_id=product.id,
                target_node_id=category.id,
                relation="IN_CATEGORY",
                confidence=min(alignment.confidence, 0.72),
                status=status,
                source_id=source_id,
                evidence={
                    "source": alignment.source,
                    "taxonomy_type": "product",
                    "taxonomy_id": alignment.taxonomy_id,
                    "taxonomy_name": alignment.taxonomy_name,
                    "free_text_category": fact.category_name,
                },
            )
        count += 1
    return count


def _owner_supported_by_evidence(
    *,
    owner_name: str,
    brand_name: str | None,
    evidence_spans: list[str],
    source_url: str,
) -> bool:
    owner_key = normalize_name(owner_name)
    brand_key = normalize_name(brand_name or "")
    domain_key = normalize_name(_normalize_domain(source_url).split(".", 1)[0])
    if not owner_key:
        return False
    if brand_key and (owner_key in brand_key or brand_key in owner_key):
        return True
    if domain_key and (owner_key in domain_key or domain_key in owner_key):
        return True
    joined = normalize_name(" ".join(evidence_spans))
    if owner_key not in joined:
        return False
    strong_owner_terms = [
        "owned by",
        "owner",
        "co owner",
        "co owned",
        "operated by",
        "legal name",
        "legal entity",
        "parent company",
        "holding company",
        "company behind",
        "subsidiary",
        "division of",
        "part of",
    ]
    return any(term in joined for term in strong_owner_terms)


def _reject_owner_edges_for_source(conn, *, brand_id: str, source_id: str) -> None:
    conn.execute(
        """
        UPDATE entity_edges
        SET status = 'rejected'
        WHERE source_node_id = ?
          AND source_id = ?
          AND relation = 'OWNED_BY'
          AND status <> 'rejected'
        """,
        (brand_id, source_id),
    )


def _taxonomy_node_name(alignment) -> str:
    label = "IAB Product" if alignment.taxonomy_type == "product" else "IAB Content"
    return f"{label} {alignment.taxonomy_id}: {alignment.taxonomy_name}"


def _category_evidence_text(category_name: str, spans: list[str]) -> str:
    evidence = _evidence_text(spans, fallback=category_name)
    if normalize_name(category_name) == normalize_name(evidence):
        return evidence
    return f"{category_name}: {evidence}"


def _should_store_ad_suggestion(
    *,
    field_path: str,
    current_value: str | None,
    suggested_value: str,
    config: EntityCrawlerConfig,
) -> bool:
    if field_path != "ads.brand_name":
        return True
    current_key = normalize_name(current_value)
    suggested_key = normalize_name(suggested_value)
    if not current_key or current_key == suggested_key:
        return True
    return current_key in {normalize_name(item) for item in config.resolver.drop_exact}


def _ad_suggestion_apply_safety(
    *,
    field_path: str,
    current_value: str | None,
    suggested_value: str,
    apply_safety: str,
    config: EntityCrawlerConfig,
) -> str:
    if apply_safety != "safe_projection_update":
        return apply_safety
    if field_path != "ads.products_text":
        return apply_safety
    current_key = normalize_name(current_value)
    suggested_key = normalize_name(suggested_value)
    if not current_key or not suggested_key or current_key == suggested_key:
        return apply_safety
    dropped = {normalize_name(item) for item in config.resolver.drop_exact}
    if current_key in dropped:
        return apply_safety
    if current_key in suggested_key or suggested_key in current_key:
        return "review_only"
    return apply_safety


def _submitted_ad_summary(
    submitted_ads: SubmittedAdReadOnlyRepository,
    ad_id: str,
) -> RelatedAdSummary | None:
    items = submitted_ads.related_ads([ad_id])
    return items[0] if items else None


def _submitted_field_value(ad: RelatedAdSummary, field_path: str) -> str | None:
    values = {
        "ads.brand_name": ad.brand_name,
        "ads.products_text": ad.products_text,
        "ads.primary_category": ad.primary_category,
        "ads.subcategory": ad.subcategory,
    }
    return values.get(field_path)


def _clean_description(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) < 12:
        return None
    return text[:300]


def _products_by_name(products: list[EntityNode]) -> dict[str, EntityNode]:
    by_name: dict[str, EntityNode] = {}
    for product in products:
        by_name[normalize_name(product.canonical_name)] = product
    return by_name


def _match_product(
    by_name: dict[str, EntityNode],
    submitted_name: str,
    fact_name: str,
) -> EntityNode | None:
    for value in (submitted_name, fact_name):
        key = normalize_name(value)
        if key in by_name:
            return by_name[key]
    fact_key = normalize_name(fact_name)
    for key, product in by_name.items():
        if key and fact_key and (key in fact_key or fact_key in key):
            return product
    return None


def _matched_vlm_product_names(
    products: list[EntityNode], result: DiscoveryVLMResult
) -> list[str]:
    by_name = _products_by_name(products)
    matched: list[str] = []
    seen: set[str] = set()
    for fact in result.product_facts:
        product = _match_product(by_name, fact.matched_submitted_product, fact.product_name)
        if product is None or product.id in seen:
            continue
        seen.add(product.id)
        matched.append(product.canonical_name)
    return matched


def _unique_names(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_name(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _evidence_text(spans: list[str], *, fallback: str) -> str:
    text = " | ".join(item.strip() for item in spans if item.strip())
    return (text or fallback).strip()[:1200]


def _crawl_reason(vlm_error: str | None) -> str:
    if vlm_error:
        return f"discovery-only crawl; VLM verifier failed: {vlm_error}"
    return "discovery-only crawl; VLM/web facts are candidate-only and no submitted records were written"


def _aliases_for_node(conn, node_id: str) -> list[str]:
    return [
        str(row["alias"])
        for row in conn.execute(
            "SELECT alias FROM entity_aliases WHERE node_id = ? ORDER BY alias",
            (node_id,),
        ).fetchall()
    ]


def _first_match(page: FetchedPage, names: list[str]) -> str | None:
    haystack = " ".join(
        item for item in [page.title, page.description, page.text] if item
    )
    normalized_haystack = normalize_name(haystack)
    for name in names:
        needle = normalize_name(name)
        if not needle or needle not in normalized_haystack:
            continue
        return _snippet(haystack, name) or f"Website discovery mention: {name}"
    return None


def _snippet(text: str, raw_needle: str) -> str | None:
    if not text:
        return None
    match = re.search(re.escape(raw_needle), text, flags=re.I)
    if match is None:
        return None
    start = max(match.start() - 140, 0)
    end = min(match.end() + 180, len(text))
    return re.sub(r"\s+", " ", text[start:end]).strip()
