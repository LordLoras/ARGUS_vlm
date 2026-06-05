from __future__ import annotations

import uuid
from collections import Counter

from ad_classifier.entity_graph.crawler_config import EntityCrawlerConfig
from ad_classifier.entity_graph.models import (
    EntityStatus,
    ResolverItem,
    ResolverResult,
    SubmittedAdObservation,
)
from ad_classifier.entity_graph.repository import EntityGraphRepository
from ad_classifier.entity_graph.submitted_ads import SubmittedAdReadOnlyRepository
from ad_classifier.entity_graph.utils import normalize_name


class EntityResolver:
    def __init__(
        self,
        graph: EntityGraphRepository,
        submitted_ads: SubmittedAdReadOnlyRepository,
        crawler_config: EntityCrawlerConfig | None = None,
    ) -> None:
        self.graph = graph
        self.submitted_ads = submitted_ads
        self.crawler_config = crawler_config or EntityCrawlerConfig()

    def preview(
        self,
        *,
        mode: str = "minimal_review",
        fully_automatic: bool = False,
        limit: int = 1000,
    ) -> ResolverResult:
        observations = self.submitted_ads.list_product_observations(limit=limit)
        return _result_for_observations(
            observations,
            preview=True,
            mode=mode,
            fully_automatic=fully_automatic,
            crawler_config=self.crawler_config,
        )

    def run(
        self,
        *,
        mode: str = "minimal_review",
        fully_automatic: bool = False,
        limit: int = 1000,
    ) -> ResolverResult:
        observations = self.submitted_ads.list_product_observations(limit=limit)
        result = _result_for_observations(
            observations,
            preview=False,
            mode=mode,
            fully_automatic=fully_automatic,
            crawler_config=self.crawler_config,
        )
        product_counts = Counter(normalize_name(obs.product_name) for obs in observations)
        run_id = f"resolver_{uuid.uuid4().hex[:12]}"
        created = 0
        updated = 0
        with self.graph.connect() as conn:
            self.graph.upsert_source(
                conn,
                source_type="resolver",
                label=f"Entity resolver run {run_id}",
                payload={"mode": mode, "fully_automatic": fully_automatic},
                source_id=f"src_{run_id}",
            )
            for obs in observations:
                status, _reason = _status_for_observation(obs, fully_automatic=fully_automatic)
                source = self.graph.upsert_source(
                    conn,
                    source_type="submitted_ad",
                    label=f"Submitted ad {obs.ad_id}",
                    ad_id=obs.ad_id,
                    payload={
                        "product": obs.product_name,
                        "original_products": obs.original_product_names,
                        "submitted_brand": obs.brand_name,
                        "submitted_brand_role": _submitted_brand_role(obs),
                        "advertiser_name": obs.advertiser_name,
                        "parent_company": obs.parent_company,
                        "evidence_source": obs.evidence_source,
                    },
                    source_id=_submitted_source_id(obs),
                )
                product, was_created = self.graph.upsert_node(
                    conn,
                    entity_type="product",
                    canonical_name=obs.product_name,
                    status=status,
                    confidence=obs.confidence,
                    description=_description(
                        obs,
                        product_counts[normalize_name(obs.product_name)],
                    ),
                    generated_from={"source": "submitted_ad", "resolver_run_id": run_id},
                )
                created += int(was_created)
                updated += int(not was_created)
                for alias in _aliases_for_observation(obs):
                    self.graph.upsert_alias(
                        conn,
                        node_id=product.id,
                        alias=alias,
                        source_id=source.id,
                        status=status,
                        confidence=obs.confidence,
                    )
                self.graph.upsert_observation(
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
                created += self._upsert_related_nodes(conn, obs, product.id, status, source.id)
            self.graph.record_resolver_run(
                conn,
                run_id=run_id,
                mode=mode,
                fully_automatic=fully_automatic,
                source_ad_count=len({obs.ad_id for obs in observations}),
                created_count=created,
                candidate_count=result.candidate_count,
                confirmed_unreviewed_count=result.confirmed_unreviewed_count,
            )
            conn.commit()
        return result.model_copy(update={"created_count": created, "updated_count": updated})

    def _upsert_related_nodes(
        self,
        conn,
        obs: SubmittedAdObservation,
        product_id: str,
        status: EntityStatus,
        source_id: str,
    ) -> int:
        created = 0
        if obs.brand_name and _submitted_brand_role(obs) == "product_brand":
            brand, was_created = self.graph.upsert_node(
                conn,
                entity_type="brand",
                canonical_name=obs.brand_name,
                status=status,
                confidence=max(obs.confidence, 0.75),
            )
            created += int(was_created)
            self.graph.upsert_edge(
                conn,
                source_node_id=product_id,
                target_node_id=brand.id,
                relation="BRANDED_BY",
                confidence=obs.confidence,
                status=status,
                source_id=source_id,
            )
            owner_name = obs.parent_company or obs.advertiser_name
            if owner_name:
                owner, owner_created = self.graph.upsert_node(
                    conn,
                    entity_type="company",
                    canonical_name=owner_name,
                    status=status,
                    confidence=0.72,
                )
                created += int(owner_created)
                self.graph.upsert_edge(
                    conn,
                    source_node_id=brand.id,
                    target_node_id=owner.id,
                    relation="OWNED_BY",
                    confidence=0.72,
                    status=status,
                    source_id=source_id,
                )
        category_name = _iab_product_category_name(obs)
        if category_name and obs.iab_product_id:
            category_status = status
            category_confidence = 0.72
            category, category_created = self.graph.upsert_node(
                conn,
                entity_type="category",
                canonical_name=category_name,
                status=category_status,
                confidence=category_confidence,
                generated_from={
                    "source": "iab_product_taxonomy",
                    "taxonomy_type": "product",
                    "taxonomy_id": obs.iab_product_id,
                    "taxonomy_name": obs.iab_product_name,
                },
            )
            created += int(category_created)
            self.graph.upsert_edge(
                conn,
                source_node_id=product_id,
                target_node_id=category.id,
                relation="IN_CATEGORY",
                confidence=category_confidence,
                status=category_status,
                source_id=source_id,
                evidence={
                    "source": "iab_product_taxonomy",
                    "taxonomy_type": "product",
                    "taxonomy_id": obs.iab_product_id,
                    "taxonomy_name": obs.iab_product_name,
                    "note": "IAB product taxonomy is the canonical graph category source",
                },
            )
        elif obs.subcategory or obs.primary_category:
            self.graph.upsert_observation(
                conn,
                node_id=product_id,
                ad_id=obs.ad_id,
                field="unmapped_category_hint",
                evidence_text=obs.subcategory or obs.primary_category or "",
                source="submitted_ad_context",
                confidence=0.2,
                source_id=source_id,
            )
        ad_node, ad_created = self.graph.upsert_node(
            conn,
            entity_type="ad",
            canonical_name=obs.ad_id,
            status="confirmed_unreviewed",
            confidence=1.0,
        )
        created += int(ad_created)
        self.graph.upsert_edge(
            conn,
            source_node_id=product_id,
            target_node_id=ad_node.id,
            relation="MENTIONED_IN_AD",
            confidence=obs.confidence,
            status=status,
            source_id=source_id,
        )
        created += self._upsert_taxonomy(conn, obs, product_id, status, source_id)
        return created

    def _upsert_taxonomy(
        self,
        conn,
        obs: SubmittedAdObservation,
        product_id: str,
        status: EntityStatus,
        source_id: str,
    ) -> int:
        created = 0
        if obs.iab_product_id:
            taxonomy_name = obs.iab_product_name or obs.iab_product_id
            taxonomy, was_created = self.graph.upsert_node(
                conn,
                entity_type="taxonomy",
                canonical_name=f"IAB Product {obs.iab_product_id}: {taxonomy_name}",
                status=status,
                confidence=0.74,
            )
            created += int(was_created)
            self.graph.upsert_taxonomy_mapping(
                conn,
                entity_id=product_id,
                taxonomy_type="product",
                taxonomy_id=obs.iab_product_id,
                taxonomy_name=taxonomy_name,
                confidence=0.74,
                status=status,
                source_id=source_id,
                evidence_text=obs.evidence_text,
            )
            self.graph.upsert_edge(
                conn,
                source_node_id=product_id,
                target_node_id=taxonomy.id,
                relation="MAPS_TO_TAXONOMY",
                confidence=0.74,
                status=status,
                source_id=source_id,
            )
        for idx, content_id in enumerate(obs.iab_content_ids):
            taxonomy_name = obs.iab_content_names[idx] if idx < len(obs.iab_content_names) else content_id
            taxonomy, was_created = self.graph.upsert_node(
                conn,
                entity_type="taxonomy",
                canonical_name=f"IAB Content {content_id}: {taxonomy_name}",
                status=status,
                confidence=0.68,
            )
            created += int(was_created)
            self.graph.upsert_taxonomy_mapping(
                conn,
                entity_id=product_id,
                taxonomy_type="content",
                taxonomy_id=content_id,
                taxonomy_name=taxonomy_name,
                confidence=0.68,
                status=status,
                source_id=source_id,
                evidence_text=obs.evidence_text,
            )
            self.graph.upsert_edge(
                conn,
                source_node_id=product_id,
                target_node_id=taxonomy.id,
                relation="MAPS_TO_TAXONOMY",
                confidence=0.68,
                status=status,
                source_id=source_id,
            )
        return created


def _result_for_observations(
    observations: list[SubmittedAdObservation],
    *,
    preview: bool,
    mode: str,
    fully_automatic: bool,
    crawler_config: EntityCrawlerConfig,
) -> ResolverResult:
    items: list[ResolverItem] = []
    for obs in observations:
        status, reason = _status_for_observation(obs, fully_automatic=fully_automatic)
        items.append(
            ResolverItem(
                ad_id=obs.ad_id,
                product_name=obs.product_name,
                status=status,
                confidence=obs.confidence,
                reason=reason,
                brand_name=obs.brand_name
                if _submitted_brand_role(obs) == "product_brand"
                else None,
                owner_name=(obs.parent_company or obs.advertiser_name)
                if _submitted_brand_role(obs) == "product_brand"
                else None,
                category_name=_iab_product_category_name(obs),
            )
        )
    return ResolverResult(
        preview=preview,
        mode="fully_automatic" if fully_automatic else "minimal_review",
        source_ad_count=len({obs.ad_id for obs in observations}),
        candidate_count=sum(1 for item in items if item.status == "candidate"),
        confirmed_unreviewed_count=sum(
            1 for item in items if item.status == "confirmed_unreviewed"
        ),
        items=items,
    )


def _status_for_observation(
    obs: SubmittedAdObservation, *, fully_automatic: bool
) -> tuple[EntityStatus, str]:
    if fully_automatic and obs.confidence >= 0.5:
        return "confirmed_unreviewed", "fully automatic mode; grounded in submitted ad evidence"
    if obs.confidence >= 0.75:
        return "confirmed_unreviewed", "strong submitted ad product evidence"
    return "candidate", "weak or ambiguous submitted evidence; kept as candidate"


def _description(obs: SubmittedAdObservation, ad_count: int) -> str:
    parts: list[str] = [obs.product_name]
    brand_role = _submitted_brand_role(obs)
    if obs.brand_name and brand_role == "product_brand":
        parts.append(f"is observed as a product for {obs.brand_name}")
    else:
        parts.append("is observed as a product mention")
    category_name = _iab_product_category_name(obs)
    if category_name:
        parts.append(f"in product category {category_name}")
    elif obs.subcategory or obs.primary_category:
        parts.append(f"with submitted ad category context {obs.subcategory or obs.primary_category}")
    parts.append(f"across {ad_count} submitted ad observation{'s' if ad_count != 1 else ''}")
    variants = [
        item
        for item in obs.original_product_names
        if normalize_name(item) != normalize_name(obs.product_name)
    ]
    if variants:
        parts.append(f"with observed variant text {', '.join(variants[:3])}")
    if obs.brand_name and brand_role != "product_brand":
        parts.append(f"with submitted ad brand/advertiser context {obs.brand_name}")
    if obs.parent_company or obs.advertiser_name:
        parts.append(f"with owner/advertiser context {obs.parent_company or obs.advertiser_name}")
    return ", ".join(parts) + "."


def _iab_product_category_name(obs: SubmittedAdObservation) -> str | None:
    if obs.iab_product_id and obs.iab_product_name:
        return f"IAB Product {obs.iab_product_id}: {obs.iab_product_name}"
    if obs.iab_product_id:
        return f"IAB Product {obs.iab_product_id}"
    return None


def _submitted_brand_role(obs: SubmittedAdObservation) -> str | None:
    if not obs.brand_name:
        return None
    brand_key = normalize_name(obs.brand_name)
    if not brand_key:
        return None
    product_values = [obs.product_name, *obs.original_product_names]
    for value in product_values:
        normalized = normalize_name(value)
        if normalized == brand_key or normalized.startswith(f"{brand_key} "):
            return "product_brand"
    evidence = normalize_name(obs.evidence_text or "")
    product_key = normalize_name(obs.product_name)
    if brand_key and product_key and brand_key in evidence and product_key in evidence:
        return "product_brand"
    return "advertiser_context"


def _aliases_for_observation(obs: SubmittedAdObservation) -> list[str]:
    seen: set[str] = set()
    aliases: list[str] = []
    for alias in [obs.product_name, *obs.original_product_names]:
        key = normalize_name(alias)
        if not key or key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
    return aliases


def _submitted_source_id(obs: SubmittedAdObservation) -> str:
    product_key = normalize_name(obs.product_name).replace(" ", "_")[:48]
    return f"src_submitted_{obs.ad_id}_{product_key}"
