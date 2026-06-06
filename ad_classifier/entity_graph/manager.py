from __future__ import annotations

from pathlib import Path

from ad_classifier.entity_graph import targets as target_utils
from ad_classifier.entity_graph.crawler import EntityWebCrawler
from ad_classifier.entity_graph.crawler_config import load_entity_crawler_config
from ad_classifier.entity_graph.models import (
    AdChangeSuggestion,
    AdChangeSuggestionStatus,
    CrawlerResult,
    CrawlerTraceItem,
    DiscoveryCandidateRequest,
    EntityNode,
    EntityStatus,
    EntityType,
    GraphPayload,
    IngestAssistCandidate,
    IngestAssistMode,
    IngestAssistRequest,
    IngestAssistResult,
    ProductPage,
    ProductSummary,
    ResolverResult,
    SubmittedAdCrawlQueueItem,
    TaxonomyMappingSummary,
)
from ad_classifier.entity_graph.repository import EntityGraphRepository
from ad_classifier.entity_graph.resolver import EntityResolver
from ad_classifier.entity_graph.submitted_ads import SubmittedAdReadOnlyRepository
from ad_classifier.entity_graph.submitted_repairs import SubmittedAdRepairRepository


class EntityGraphManager:
    def __init__(
        self,
        graph_db_path: Path,
        submitted_db_path: Path,
        *,
        crawler_config_path: Path | None = None,
        knowledge_db_path: Path | None = None,
    ) -> None:
        self.crawler_config = load_entity_crawler_config(crawler_config_path)
        if knowledge_db_path is not None:
            self.crawler_config = self.crawler_config.model_copy(
                update={
                    "taxonomy_alignment": self.crawler_config.taxonomy_alignment.model_copy(
                        update={"knowledge_db_path": knowledge_db_path.expanduser().resolve()}
                    )
                }
            )
        self.graph = EntityGraphRepository(graph_db_path)
        self.submitted_ads = SubmittedAdReadOnlyRepository(
            submitted_db_path, crawler_config=self.crawler_config
        )
        self.submitted_repairs = SubmittedAdRepairRepository(
            submitted_db_path,
            self.crawler_config.submitted_db_repairs,
        )
        self.resolver = EntityResolver(self.graph, self.submitted_ads, self.crawler_config)
        self.web_crawler = EntityWebCrawler(
            self.graph,
            self.submitted_ads,
            self.crawler_config,
        )

    def list_products(
        self, *, status: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[ProductSummary]:
        with self.graph.connect(readonly=True) as conn:
            return self.graph.list_products(
                conn,
                status=status,
                q=q,
                limit=limit,
                offset=offset,
                crawler_config=self.crawler_config,
            )

    def get_product(self, product_id: str) -> ProductPage | None:
        with self.graph.connect(readonly=True) as conn:
            page = self.graph.get_product_page(conn, product_id)
        if page is None:
            return None
        related_ads = self.submitted_ads.related_ads(
            sorted({item.ad_id for item in page.observations})
        )
        evidence_counts = {item.ad_id: 0 for item in page.observations}
        first_evidence: dict[str, str] = {}
        for obs in page.observations:
            evidence_counts[obs.ad_id] = evidence_counts.get(obs.ad_id, 0) + 1
            first_evidence.setdefault(obs.ad_id, obs.evidence_text)
        related = [
            item.model_copy(
                update={
                    "evidence_count": evidence_counts.get(item.ad_id, 0),
                    "first_evidence_text": first_evidence.get(item.ad_id),
                }
            )
            for item in related_ads
        ]
        return page.model_copy(update={"related_ads": related})

    def graph_payload(self, *, limit: int = 400) -> GraphPayload:
        with self.graph.connect(readonly=True) as conn:
            return self.graph.graph(conn, limit=limit)

    def product_crawler_trace(self, product_id: str, *, limit: int = 50) -> list[CrawlerTraceItem]:
        with self.graph.connect(readonly=True) as conn:
            self.graph.get_node(conn, product_id)
            return self.graph.list_product_crawl_trace(conn, product_id, limit=limit)

    def taxonomy_mappings(self, *, limit: int = 200) -> list[TaxonomyMappingSummary]:
        with self.graph.connect(readonly=True) as conn:
            return self.graph.list_taxonomy_mappings(conn, limit=limit)

    def preview_resolver(
        self, *, mode: str = "minimal_review", fully_automatic: bool = False, limit: int = 1000
    ) -> ResolverResult:
        return self.resolver.preview(mode=mode, fully_automatic=fully_automatic, limit=limit)

    def run_resolver(
        self, *, mode: str = "minimal_review", fully_automatic: bool = False, limit: int = 1000
    ) -> ResolverResult:
        return self.resolver.run(mode=mode, fully_automatic=fully_automatic, limit=limit)

    def run_crawler(
        self,
        *,
        limit: int = 100,
        ad_ids: list[str] | None = None,
        target_urls: dict[str, list[str]] | None = None,
    ) -> CrawlerResult:
        extra_targets = target_utils.from_ad_url_mapping(target_urls or {})
        return self.web_crawler.run(limit=limit, ad_ids=ad_ids, extra_targets=extra_targets)

    def crawl_queue(
        self,
        *,
        limit: int = 1000,
        q: str | None = None,
    ) -> list[SubmittedAdCrawlQueueItem]:
        items = self.submitted_ads.list_crawl_queue(limit=limit, q=q)
        ad_ids = [item.ad_id for item in items]
        with self.graph.connect(readonly=True) as conn:
            metadata = self.graph.crawl_queue_metadata(conn, ad_ids)
        return [
            item.model_copy(
                update={
                    "pending_suggestion_count": int(
                        metadata.get(item.ad_id, {}).get("pending_suggestion_count") or 0
                    ),
                    "last_crawled_at": metadata.get(item.ad_id, {}).get("last_crawled_at"),
                    "crawled_source_count": int(
                        metadata.get(item.ad_id, {}).get("crawled_source_count") or 0
                    ),
                    "crawl_status": _crawl_status(
                        item,
                        pending_suggestion_count=int(
                            metadata.get(item.ad_id, {}).get("pending_suggestion_count") or 0
                        ),
                        crawled_source_count=int(
                            metadata.get(item.ad_id, {}).get("crawled_source_count") or 0
                        ),
                    ),
                }
            )
            for item in items
        ]

    def lookup_nodes(
        self,
        *,
        entity_type: EntityType,
        q: str | None = None,
        limit: int = 20,
    ) -> list[EntityNode]:
        with self.graph.connect(readonly=True) as conn:
            return self.graph.lookup_nodes(conn, entity_type=entity_type, q=q, limit=limit)

    def update_product(
        self,
        product_id: str,
        *,
        canonical_name: str | None = None,
        description: str | None = None,
        status: EntityStatus | None = None,
        confidence: float | None = None,
        brand_name: str | None = None,
        owner_name: str | None = None,
        category_name: str | None = None,
        brand_name_provided: bool = False,
        owner_name_provided: bool = False,
        category_name_provided: bool = False,
    ) -> ProductPage:
        with self.graph.connect() as conn:
            source = self.graph.upsert_source(
                conn,
                source_type="user",
                label="Product entity manual edit",
                payload={
                    "product_id": product_id,
                    "fields": {
                        "canonical_name": canonical_name,
                        "description": description,
                        "status": status,
                        "confidence": confidence,
                        "brand_name": brand_name,
                        "owner_name": owner_name,
                        "category_name": category_name,
                    },
                },
            )
            product = self.graph.update_node_fields(
                conn,
                product_id,
                canonical_name=canonical_name,
                description=description,
                status=status,
                confidence=confidence,
                generated_from={"source": "user_edit"},
            )
            brand = None
            if brand_name_provided:
                brand = self.graph.replace_relation(
                    conn,
                    source_node_id=product.id,
                    relation="BRANDED_BY",
                    entity_type="brand",
                    canonical_name=brand_name,
                    source_id=source.id,
                )
            if owner_name_provided and brand is None:
                brand = self.graph.first_related(conn, product.id, "BRANDED_BY")
            if owner_name_provided and brand is not None:
                self.graph.replace_relation(
                    conn,
                    source_node_id=brand.id,
                    relation="OWNED_BY",
                    entity_type="company",
                    canonical_name=owner_name,
                    source_id=source.id,
                )
            if category_name_provided:
                self.graph.replace_relation(
                    conn,
                    source_node_id=product.id,
                    relation="IN_CATEGORY",
                    entity_type="category",
                    canonical_name=category_name,
                    source_id=source.id,
                )
            conn.commit()
        updated = self.get_product(product_id)
        if updated is None:
            raise KeyError(product_id)
        return updated

    def ingest_assist_preview(self, payload: IngestAssistRequest) -> IngestAssistResult:
        mode: IngestAssistMode = (
            payload.mode or self.crawler_config.ingest_assist.default_mode
        )
        product_candidates: list[IngestAssistCandidate] = []
        brand_candidates: list[IngestAssistCandidate] = []
        category_candidates: list[IngestAssistCandidate] = []
        with self.graph.connect(readonly=True) as conn:
            for product in payload.products:
                product_candidates.extend(
                    _ingest_candidates(
                        product,
                        self.graph.lookup_nodes(
                            conn,
                            entity_type="product",
                            q=product,
                            limit=5,
                        ),
                    )
                )
            if payload.brand_name:
                brand_candidates = _ingest_candidates(
                    payload.brand_name,
                    self.graph.lookup_nodes(
                        conn,
                        entity_type="brand",
                        q=payload.brand_name,
                        limit=5,
                    ),
                )
            if payload.category_name:
                category_candidates = _ingest_candidates(
                    payload.category_name,
                    self.graph.lookup_nodes(
                        conn,
                        entity_type="category",
                        q=payload.category_name,
                        limit=5,
                    ),
                )
        return IngestAssistResult(
            mode=mode,
            recommendation=_ingest_recommendation(
                mode,
                product_candidates,
                brand_candidates,
                category_candidates,
                min_confidence=self.crawler_config.ingest_assist.min_graph_confidence,
            ),
            product_candidates=product_candidates,
            brand_candidates=brand_candidates,
            category_candidates=category_candidates,
        )

    def list_ad_change_suggestions(
        self,
        *,
        status: AdChangeSuggestionStatus | None = None,
        ad_id: str | None = None,
        limit: int = 200,
    ) -> list[AdChangeSuggestion]:
        with self.graph.connect(readonly=True) as conn:
            return self.graph.list_ad_change_suggestions(
                conn,
                status=status,
                ad_id=ad_id,
                limit=limit,
            )

    def approve_ad_change_suggestion(self, suggestion_id: str) -> AdChangeSuggestion:
        with self.graph.connect() as conn:
            suggestion = self.graph.set_ad_change_suggestion_status(
                conn,
                suggestion_id,
                "approved",
            )
            conn.commit()
            return suggestion

    def reject_ad_change_suggestion(self, suggestion_id: str) -> AdChangeSuggestion:
        with self.graph.connect() as conn:
            suggestion = self.graph.set_ad_change_suggestion_status(
                conn,
                suggestion_id,
                "rejected",
            )
            conn.commit()
            return suggestion

    def apply_ad_change_suggestion(
        self,
        suggestion_id: str,
        *,
        value: str | None = None,
    ) -> AdChangeSuggestion:
        with self.graph.connect() as conn:
            suggestion = self.graph.get_ad_change_suggestion(conn, suggestion_id)
            applied_value = self.submitted_repairs.apply_suggestion(suggestion, value=value)
            applied = self.graph.mark_ad_change_suggestion_applied(
                conn,
                suggestion_id,
                applied_value,
            )
            conn.commit()
            return applied

    def reset_graph(self) -> dict[str, bool]:
        with self.graph.connect() as conn:
            self.graph.clear_experimental_graph(conn)
            conn.commit()
        return {"reset": True}

    def set_status(self, entity_id: str, status: EntityStatus) -> EntityNode:
        with self.graph.connect() as conn:
            node = self.graph.set_node_status(conn, entity_id, status)
            if node.type == "product" and status == "confirmed_reviewed":
                self.graph.promote_product_context(conn, entity_id, status)
                node = self.graph.get_node(conn, entity_id)
            conn.commit()
            return node

    def add_discovery_candidate(self, payload: DiscoveryCandidateRequest) -> EntityNode:
        with self.graph.connect() as conn:
            source = self.graph.upsert_source(
                conn,
                source_type="discovery_only",
                label=payload.source_url or "External discovery candidate",
                url=payload.source_url,
                payload={"notes": payload.notes},
            )
            node, _created = self.graph.upsert_node(
                conn,
                entity_type=payload.entity_type,
                canonical_name=payload.name,
                status="candidate",
                confidence=payload.confidence,
                generated_from={"source": "discovery_only"},
            )
            self.graph.upsert_alias(
                conn,
                node_id=node.id,
                alias=payload.name,
                source_id=source.id,
                status="candidate",
                confidence=payload.confidence,
            )
            for alias in payload.aliases:
                self.graph.upsert_alias(
                    conn,
                    node_id=node.id,
                    alias=alias,
                    source_id=source.id,
                    status="candidate",
                    confidence=min(payload.confidence, 0.4),
                )
            conn.commit()
            return self.graph.get_node(conn, node.id)

    def submitted_db_is_readonly(self) -> bool:
        return self.submitted_ads.query_only_enabled()


def _crawl_status(
    item: SubmittedAdCrawlQueueItem,
    *,
    pending_suggestion_count: int,
    crawled_source_count: int,
) -> str:
    if pending_suggestion_count > 0:
        return "needs_review"
    if crawled_source_count > 0:
        return "done"
    if not item.has_web_targets and not item.has_search_targets:
        return "no_targets"
    return "ready"


def _ingest_candidates(input_value: str, nodes: list[EntityNode]) -> list[IngestAssistCandidate]:
    input_key = input_value.casefold().strip()
    candidates: list[IngestAssistCandidate] = []
    for node in nodes:
        exact = int(node.canonical_name.casefold().strip() == input_key)
        score = min(max(node.confidence + (0.1 if exact else 0.0), 0.0), 1.0)
        candidates.append(
            IngestAssistCandidate(
                input_value=input_value,
                node=node,
                score=score,
                reason="exact graph match" if exact else "similar graph node",
            )
        )
    return sorted(candidates, key=lambda item: item.score, reverse=True)


def _ingest_recommendation(
    mode: IngestAssistMode,
    product_candidates: list[IngestAssistCandidate],
    brand_candidates: list[IngestAssistCandidate],
    category_candidates: list[IngestAssistCandidate],
    *,
    min_confidence: float,
) -> str:
    if mode == "keep_initial_metadata":
        return "Keep submitted ingest metadata and record graph matches as optional context."
    candidates = [*product_candidates, *brand_candidates, *category_candidates]
    strongest = max((item.score for item in candidates), default=0.0)
    if mode == "use_graph" and strongest >= min_confidence:
        return "Use matching reviewed/high-confidence graph entities during ingest."
    if mode == "crawl_reinforce":
        return "Use graph matches when strong and send weak or missing entities to crawler/VLM reinforcement."
    return "Graph confidence is below threshold; keep initial metadata unless crawler reinforcement is requested."
