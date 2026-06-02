from __future__ import annotations

from pathlib import Path

from ad_classifier.entity_graph.models import (
    DiscoveryCandidateRequest,
    EntityNode,
    EntityStatus,
    GraphPayload,
    ProductPage,
    ProductSummary,
    ResolverResult,
    TaxonomyMappingSummary,
)
from ad_classifier.entity_graph.repository import EntityGraphRepository
from ad_classifier.entity_graph.resolver import EntityResolver
from ad_classifier.entity_graph.submitted_ads import SubmittedAdReadOnlyRepository


class EntityGraphManager:
    def __init__(self, graph_db_path: Path, submitted_db_path: Path) -> None:
        self.graph = EntityGraphRepository(graph_db_path)
        self.submitted_ads = SubmittedAdReadOnlyRepository(submitted_db_path)
        self.resolver = EntityResolver(self.graph, self.submitted_ads)

    def list_products(
        self, *, status: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[ProductSummary]:
        with self.graph.connect(readonly=True) as conn:
            return self.graph.list_products(conn, status=status, q=q, limit=limit, offset=offset)

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

    def set_status(self, entity_id: str, status: EntityStatus) -> EntityNode:
        with self.graph.connect() as conn:
            node = self.graph.set_node_status(conn, entity_id, status)
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
