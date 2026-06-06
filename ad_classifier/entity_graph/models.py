from __future__ import annotations

from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel

EntityType = Literal["product", "brand", "company", "category", "taxonomy", "ad"]
EntityStatus = Literal["candidate", "confirmed_unreviewed", "confirmed_reviewed", "rejected"]
AdChangeSuggestionStatus = Literal["pending", "approved", "rejected", "applied"]
SourceType = Literal["submitted_ad", "taxonomy", "discovery_only", "user", "resolver"]
IngestAssistMode = Literal["keep_initial_metadata", "use_graph", "crawl_reinforce"]
CrawlQueueStatus = Literal["ready", "done", "needs_review", "no_targets"]
RelationType = Literal[
    "BRANDED_BY",
    "OWNED_BY",
    "IN_CATEGORY",
    "MAPS_TO_TAXONOMY",
    "MENTIONED_IN_AD",
]


class EntitySource(StrictModel):
    id: str
    source_type: SourceType
    label: str
    url: str | None = None
    ad_id: str | None = None
    payload: dict | None = None
    created_at: str | None = None


class EntityNode(StrictModel):
    id: str
    type: EntityType
    canonical_name: str
    normalized_name: str
    description: str | None = None
    status: EntityStatus = "candidate"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    generated_from: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


class EntityAlias(StrictModel):
    id: int | None = None
    node_id: str
    alias: str
    normalized_alias: str
    source_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: EntityStatus = "candidate"
    created_at: str | None = None


class EntityEdge(StrictModel):
    id: str
    source_node_id: str
    target_node_id: str
    relation: RelationType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: EntityStatus = "candidate"
    source_id: str | None = None
    evidence: dict | None = None
    created_at: str | None = None


class EntityObservation(StrictModel):
    id: str
    node_id: str
    ad_id: str
    field: str
    evidence_text: str
    source: str
    time_ms: int | None = Field(default=None, ge=0)
    frame_index: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_id: str | None = None
    created_at: str | None = None


class TaxonomyMapping(StrictModel):
    id: str
    entity_id: str
    taxonomy_type: Literal["product", "content", "category"]
    taxonomy_id: str
    taxonomy_name: str | None = None
    relation: str = "maps_to"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: EntityStatus = "candidate"
    source_id: str | None = None
    evidence_text: str | None = None
    created_at: str | None = None


class SubmittedAdObservation(StrictModel):
    ad_id: str
    product_name: str
    original_product_names: list[str] = Field(default_factory=list)
    brand_name: str | None = None
    advertiser_name: str | None = None
    parent_company: str | None = None
    primary_category: str | None = None
    subcategory: str | None = None
    iab_product_id: str | None = None
    iab_product_name: str | None = None
    iab_content_ids: list[str] = Field(default_factory=list)
    iab_content_names: list[str] = Field(default_factory=list)
    evidence_text: str | None = None
    evidence_source: str = "submitted_ad"
    time_ms: int | None = Field(default=None, ge=0)
    frame_index: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SubmittedAdWebTarget(StrictModel):
    ad_id: str
    url: str
    domain: str | None = None
    source: str
    evidence_text: str | None = None


class RelatedAdSummary(StrictModel):
    ad_id: str
    brand_name: str | None = None
    products_text: str | None = None
    primary_category: str | None = None
    subcategory: str | None = None
    ingested_at: str | None = None
    evidence_count: int = 0
    first_evidence_text: str | None = None


class SubmittedAdCrawlQueueItem(RelatedAdSummary):
    has_web_targets: bool = False
    web_targets: list[str] = Field(default_factory=list)
    has_search_targets: bool = False
    search_queries: list[str] = Field(default_factory=list)
    product_count: int = 0
    pending_suggestion_count: int = 0
    last_crawled_at: str | None = None
    crawled_source_count: int = 0
    crawl_status: CrawlQueueStatus = "ready"


class ProductSummary(StrictModel):
    node: EntityNode
    brand: EntityNode | None = None
    owner: EntityNode | None = None
    category: EntityNode | None = None
    aliases_count: int = 0
    evidence_count: int = 0
    related_ads_count: int = 0
    taxonomy_mappings_count: int = 0


class ProductPage(ProductSummary):
    aliases: list[EntityAlias] = Field(default_factory=list)
    taxonomy_mappings: list[TaxonomyMapping] = Field(default_factory=list)
    observations: list[EntityObservation] = Field(default_factory=list)
    related_ads: list[RelatedAdSummary] = Field(default_factory=list)


class GraphPayload(StrictModel):
    nodes: list[EntityNode]
    edges: list[EntityEdge]


class TaxonomyMappingSummary(StrictModel):
    mapping: TaxonomyMapping
    entity: EntityNode


class ResolverItem(StrictModel):
    ad_id: str
    product_name: str
    status: EntityStatus
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    brand_name: str | None = None
    owner_name: str | None = None
    category_name: str | None = None


class ResolverResult(StrictModel):
    preview: bool
    mode: Literal["minimal_review", "fully_automatic"] = "minimal_review"
    source_ad_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    candidate_count: int = 0
    confirmed_unreviewed_count: int = 0
    items: list[ResolverItem] = Field(default_factory=list)


class CrawlerItem(StrictModel):
    ad_id: str
    url: str
    status: Literal["visited", "skipped", "failed"]
    target_source: str | None = None
    target_evidence_text: str | None = None
    source_id: str | None = None
    matched_products: list[str] = Field(default_factory=list)
    title: str | None = None
    final_url: str | None = None
    reason: str | None = None


class CrawlerResult(StrictModel):
    visited_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    observation_count: int = 0
    suggestion_count: int = 0
    items: list[CrawlerItem] = Field(default_factory=list)


class CrawlerTraceItem(StrictModel):
    source_id: str
    ad_id: str | None = None
    url: str | None = None
    final_url: str | None = None
    target_source: str | None = None
    source_kind: str | None = None
    fetcher: str | None = None
    status: str | None = None
    title: str | None = None
    vlm_error: str | None = None
    product_fact_count: int = 0
    taxonomy_hint_count: int = 0
    suggested_change_count: int = 0
    evidence_text: str | None = None
    created_at: str | None = None


class AdChangeSuggestion(StrictModel):
    id: str
    ad_id: str
    source_id: str | None = None
    field_path: Literal["ads.brand_name", "ads.products_text", "ads.primary_category", "ads.subcategory"]
    current_value: str | None = None
    suggested_value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    evidence_text: str | None = None
    status: AdChangeSuggestionStatus = "pending"
    apply_safety: Literal["safe_projection_update", "review_only", "do_not_apply"] = "review_only"
    payload: dict | None = None
    created_at: str | None = None
    reviewed_at: str | None = None
    applied_at: str | None = None


class DiscoveryCandidateRequest(StrictModel):
    entity_type: EntityType = "product"
    name: str
    aliases: list[str] = Field(default_factory=list)
    source_url: str | None = None
    notes: str | None = None
    confidence: float = Field(default=0.35, ge=0.0, le=1.0)


class IngestAssistRequest(StrictModel):
    mode: IngestAssistMode | None = None
    products: list[str] = Field(default_factory=list, max_length=50)
    brand_name: str | None = None
    category_name: str | None = None


class IngestAssistCandidate(StrictModel):
    input_value: str
    node: EntityNode
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str


class IngestAssistResult(StrictModel):
    mode: IngestAssistMode
    recommendation: str
    product_candidates: list[IngestAssistCandidate] = Field(default_factory=list)
    brand_candidates: list[IngestAssistCandidate] = Field(default_factory=list)
    category_candidates: list[IngestAssistCandidate] = Field(default_factory=list)
