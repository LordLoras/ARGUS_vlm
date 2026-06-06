from __future__ import annotations

from dataclasses import dataclass

from ad_classifier.entity_graph.crawler_config import EntityCrawlerConfig, TaxonomyAliasRule
from ad_classifier.entity_graph.utils import normalize_name
from ad_classifier.knowledge.manager import KnowledgeManager
from ad_classifier.knowledge.models import IABTaxonomyEntry


@dataclass(frozen=True)
class TaxonomyAlignment:
    taxonomy_type: str
    taxonomy_id: str
    taxonomy_name: str
    confidence: float
    evidence_text: str
    source: str


class TaxonomyAligner:
    def __init__(self, config: EntityCrawlerConfig) -> None:
        self.config = config
        self.kb = KnowledgeManager(config.taxonomy_alignment.knowledge_db_path)

    def align(
        self,
        *,
        category_name: str | None,
        product_name: str,
        brand_name: str | None,
        evidence_text: str,
    ) -> list[TaxonomyAlignment]:
        if not self.config.taxonomy_alignment.enabled:
            return []
        category_text = category_name or ""
        alias_text = " ".join(item for item in [category_name, product_name, brand_name] if item)
        if not normalize_name(alias_text):
            return []
        alignments: list[TaxonomyAlignment] = []
        if normalize_name(category_text):
            alignments.extend(
                self._direct_product_matches(
                    category_text,
                    evidence_text=evidence_text,
                    confidence=0.74,
                )
            )
            alignments.extend(
                self._direct_content_matches(
                    category_text,
                    evidence_text=evidence_text,
                    confidence=0.58,
                )
            )
        alignments.extend(self._alias_matches(alias_text, evidence_text=evidence_text))
        return _dedupe_alignments(alignments)

    def _direct_product_matches(
        self, text: str, *, evidence_text: str, confidence: float
    ) -> list[TaxonomyAlignment]:
        results: list[TaxonomyAlignment] = []
        for query in _phrase_queries(text):
            for entry in self.kb.search_product_taxonomy(query, limit=5):
                if not _entry_matches(entry, query):
                    continue
                results.append(
                    _alignment(
                        entry,
                        taxonomy_type="product",
                        confidence=confidence,
                        evidence_text=evidence_text,
                        source="iab_product_search",
                    )
                )
        return results

    def _direct_content_matches(
        self, text: str, *, evidence_text: str, confidence: float
    ) -> list[TaxonomyAlignment]:
        results: list[TaxonomyAlignment] = []
        for query in _phrase_queries(text) + _token_queries(text):
            for entry in self.kb.search_content_taxonomy(query, limit=5):
                if not _entry_matches(entry, query):
                    continue
                results.append(
                    _alignment(
                        entry,
                        taxonomy_type="content",
                        confidence=confidence,
                        evidence_text=evidence_text,
                        source="iab_content_search",
                    )
                )
        return results

    def _alias_matches(self, text: str, *, evidence_text: str) -> list[TaxonomyAlignment]:
        key = normalize_name(text)
        results: list[TaxonomyAlignment] = []
        for rule in self.config.taxonomy_alignment.aliases:
            if not _rule_matches(rule, key):
                continue
            if rule.product_taxonomy_id:
                entry = self.kb.get_product_entry(rule.product_taxonomy_id)
                if entry and rule.confidence >= self.config.taxonomy_alignment.min_product_confidence:
                    results.append(
                        _alignment(
                            entry,
                            taxonomy_type="product",
                            confidence=rule.confidence,
                            evidence_text=evidence_text,
                            source="configured_alias",
                        )
                    )
            if rule.content_taxonomy_id:
                entry = self.kb.get_content_entry(rule.content_taxonomy_id)
                if entry and rule.confidence >= self.config.taxonomy_alignment.min_content_confidence:
                    results.append(
                        _alignment(
                            entry,
                            taxonomy_type="content",
                            confidence=max(rule.confidence - 0.08, 0.0),
                            evidence_text=evidence_text,
                            source="configured_alias",
                        )
                    )
        return results


def _alignment(
    entry: IABTaxonomyEntry,
    *,
    taxonomy_type: str,
    confidence: float,
    evidence_text: str,
    source: str,
) -> TaxonomyAlignment:
    return TaxonomyAlignment(
        taxonomy_type=taxonomy_type,
        taxonomy_id=entry.unique_id,
        taxonomy_name=entry.name,
        confidence=max(min(confidence, 1.0), 0.0),
        evidence_text=evidence_text,
        source=source,
    )


_TOKEN_STOPWORDS = {
    "all",
    "and",
    "bold",
    "full",
    "large",
    "medium",
    "new",
    "powerful",
    "premium",
    "size",
    "sized",
    "small",
    "sport",
    "trim",
    "turbo",
}


def _phrase_queries(text: str) -> list[str]:
    normalized = normalize_name(text)
    values = [text.strip(), normalized]
    if "sport utility" in normalized:
        values.append("sport utility")
    if "mobile phone" in normalized:
        values.append("mobile phone")
    return _unique(values)[:5]


def _token_queries(text: str) -> list[str]:
    normalized = normalize_name(text)
    tokens = [
        token
        for token in normalized.split()
        if len(token) >= 3 and token not in _TOKEN_STOPWORDS
    ]
    values = tokens
    if "suv" in tokens:
        values.append("SUV")
    return _unique(values)[:8]


def _entry_matches(entry: IABTaxonomyEntry, query: str) -> bool:
    query_key = normalize_name(query)
    if not query_key:
        return False
    names = [
        entry.name,
        entry.tier_1,
        entry.tier_2,
        entry.tier_3,
        getattr(entry, "tier_4", None),
    ]
    for value in names:
        value_key = normalize_name(value or "")
        if not value_key:
            continue
        if query_key == value_key or query_key in value_key or value_key in query_key:
            return True
    return False


def _rule_matches(rule: TaxonomyAliasRule, text_key: str) -> bool:
    for term in rule.terms:
        term_key = normalize_name(term)
        if term_key and term_key in text_key:
            return True
    return False


def _dedupe_alignments(alignments: list[TaxonomyAlignment]) -> list[TaxonomyAlignment]:
    by_key: dict[tuple[str, str], TaxonomyAlignment] = {}
    for alignment in alignments:
        key = (alignment.taxonomy_type, alignment.taxonomy_id)
        current = by_key.get(key)
        if current is None or alignment.confidence > current.confidence:
            by_key[key] = alignment
    return sorted(
        by_key.values(),
        key=lambda item: (item.taxonomy_type != "product", -item.confidence, item.taxonomy_name),
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        key = normalize_name(clean)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result
