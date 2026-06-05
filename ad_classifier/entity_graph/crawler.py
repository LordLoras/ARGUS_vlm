from __future__ import annotations

import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlparse

from ad_classifier.entity_graph import rows
from ad_classifier.entity_graph.crawler_config import EntityCrawlerConfig
from ad_classifier.entity_graph.discovery_vlm import (
    DiscoveryVerifier,
    DiscoveryVLMResult,
    VLMDiscoveryVerifier,
)
from ad_classifier.entity_graph.models import (
    CrawlerItem,
    CrawlerResult,
    EntityNode,
    RelatedAdSummary,
    SubmittedAdObservation,
    SubmittedAdWebTarget,
)
from ad_classifier.entity_graph.repository import EntityGraphRepository
from ad_classifier.entity_graph.submitted_ads import SubmittedAdReadOnlyRepository
from ad_classifier.entity_graph.utils import normalize_name


@dataclass(frozen=True)
class FetchedPage:
    url: str
    final_url: str
    status_code: int
    title: str | None
    description: str | None
    text: str
    fetcher: str


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
    ) -> None:
        self.graph = graph
        self.submitted_ads = submitted_ads
        self.crawler_config = crawler_config
        self.fetcher = fetcher or DefaultPageFetcher()
        self.verifier = verifier
        if verifier is None and crawler_config.vlm_parse.enabled:
            self.verifier = VLMDiscoveryVerifier(crawler_config.vlm_parse)

    def run(
        self,
        *,
        limit: int = 100,
        ad_ids: list[str] | None = None,
        extra_targets: list[SubmittedAdWebTarget] | None = None,
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
                skipped_count=len(targets),
                items=[
                    CrawlerItem(
                        ad_id=target.ad_id,
                        url=target.url,
                        status="skipped",
                        reason="crawler disabled",
                    )
                    for target in targets
                ],
            )

        with self.graph.connect() as conn:
            target_ad_ids = _target_ad_ids(ad_ids, targets)
            _ensure_submitted_product_nodes(
                self.graph,
                self.submitted_ads,
                conn,
                target_ad_ids,
                limit=max(limit, len(target_ad_ids) * 8),
            )
            targets = _with_reference_search_targets(conn, targets, ad_ids, self.crawler_config)
            targets = _dedupe_targets(targets, max_targets=self.crawler_config.crawler.max_targets_per_ad)
            for target in targets:
                if not _domain_allowed(target.domain, self.crawler_config):
                    items.append(
                        CrawlerItem(
                            ad_id=target.ad_id,
                            url=target.url,
                            status="skipped",
                            reason="domain blocked by crawler config",
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
                    )
                    observation_count += written[0]
                    suggestion_count_total += written[1]
                    matched.extend(_matched_vlm_product_names(products, vlm_result))

                items.append(
                    CrawlerItem(
                        ad_id=target.ad_id,
                        url=target.url,
                        status="visited",
                        source_id=source_id,
                        matched_products=matched,
                        title=page.title,
                        final_url=page.final_url,
                        reason=_crawl_reason(vlm_error),
                    )
                )
            conn.commit()

        return CrawlerResult(
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
    by_ad = {target.ad_id for target in targets}
    extra: list[SubmittedAdWebTarget] = []
    queries_used = 0
    for ad_id in ad_ids:
        if queries_used >= config.crawler.max_queries_per_run:
            break
        if ad_id in by_ad:
            continue
        products = _products_for_ad(conn, ad_id)
        for product in products[: max(config.crawler.max_reference_results_per_ad, 1)]:
            if queries_used >= config.crawler.max_queries_per_run:
                break
            query = config.crawler.reference_search_query_template.format(
                product=product.canonical_name,
                ad_id=ad_id,
            )
            try:
                urls = _duckduckgo_urls(query, config)
            except Exception:
                urls = []
            queries_used += 1
            for url in urls[: config.crawler.max_reference_results_per_ad]:
                parsed = urlparse(url)
                extra.append(
                    SubmittedAdWebTarget(
                        ad_id=ad_id,
                        url=url,
                        domain=parsed.netloc.lower() or None,
                        source="reference_search",
                        evidence_text=f"Reference search query: {query}",
                    )
                )
    return _dedupe_targets([*targets, *extra], max_targets=config.crawler.max_targets_per_ad)


def _duckduckgo_urls(query: str, config: EntityCrawlerConfig) -> list[str]:
    endpoint = config.crawler.reference_search_endpoint
    url = f"{endpoint}?{urlencode({'q': query})}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": config.crawler.user_agent},
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
            if key not in by_url:
                by_url[key] = target
        result.extend(list(by_url.values())[:max_targets])
    return result


class DefaultPageFetcher:
    def fetch(self, target: SubmittedAdWebTarget, config: EntityCrawlerConfig) -> FetchedPage:
        if config.crawler.provider == "browser":
            return _fetch_with_browser(target.url, config)
        try:
            page = _fetch_with_http(target.url, config)
        except Exception as http_exc:
            if config.crawler.use_browser_fallback:
                try:
                    return _fetch_with_browser(target.url, config)
                except Exception as browser_exc:
                    raise RuntimeError(
                        f"http fetch failed: {http_exc}; browser fallback failed: {browser_exc}"
                    ) from browser_exc
            raise
        if len(page.text) < 200 and config.crawler.use_browser_fallback:
            try:
                return _fetch_with_browser(target.url, config)
            except Exception:
                return page
        return page


def _fetch_with_http(url: str, config: EntityCrawlerConfig) -> FetchedPage:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": config.crawler.user_agent},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=config.crawler.timeout_s,
            context=_ssl_context(),
        ) as response:
            raw = response.read(500_000)
            final_url = response.geturl()
            status_code = int(getattr(response, "status", 200))
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read(200_000)
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
        text=parsed.text,
        fetcher="http",
    )


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
                wait_until="networkidle",
                timeout=int(config.crawler.timeout_s * 1000),
            )
            html = page.content()
            parsed = _parse_html(html)
            return FetchedPage(
                url=url,
                final_url=page.url,
                status_code=response.status if response else 0,
                title=parsed.title,
                description=parsed.description,
                text=parsed.text,
                fetcher="browser",
            )
        finally:
            browser.close()


@dataclass(frozen=True)
class ParsedHtml:
    title: str | None
    description: str | None
    text: str


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self._in_title = False
        self._blocked_depth = 0
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []

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

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript"} and self._blocked_depth:
            self._blocked_depth -= 1
        if tag_name == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        if self._blocked_depth == 0:
            self._text_parts.append(text)

    def result(self) -> ParsedHtml:
        title = " ".join(self._title_parts).strip() or None
        text = re.sub(r"\s+", " ", " ".join(self._text_parts)).strip()
        return ParsedHtml(title=title, description=self.description, text=text[:20_000])


def _parse_html(html: str) -> ParsedHtml:
    parser = _VisibleTextParser()
    parser.feed(html)
    return parser.result()


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
    if href.startswith("/l/"):
        parsed = urlparse(href)
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
) -> tuple[int, int]:
    observations = 0
    suggestions = 0
    by_name = _products_by_name(products)
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
            if fact.owner_name:
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
        if fact.category_name:
            graph.upsert_observation(
                conn,
                node_id=product.id,
                ad_id=ad_id,
                field="web_vlm_category_hint",
                evidence_text=_evidence_text(fact.evidence_spans, fallback=fact.category_name),
                source="web_vlm",
                confidence=min(fact.confidence, 0.55),
                source_id=source_id,
            )
            observations += 1
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
        graph.upsert_ad_change_suggestion(
            conn,
            ad_id=ad_id,
            source_id=source_id,
            field_path=suggestion.field_path,
            current_value=current_value,
            suggested_value=suggestion.suggested_value.strip(),
            confidence=min(suggestion.confidence, 0.75),
            reason=suggestion.reason.strip()[:1000],
            evidence_text=_evidence_text(
                suggestion.evidence_spans,
                fallback=suggestion.suggested_value,
            ),
            apply_safety=suggestion.apply_safety,
            payload={
                "source": "web_vlm",
                "source_kind": result.source_kind,
                "source_url": result.source_url,
                "warnings": result.warnings,
            },
        )
        suggestions += 1
    return observations, suggestions


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
