from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import quote

import httpx

from ad_classifier.brand_profiles.matching import (
    SearchContext,
    candidate_digest,
    enriched_queries,
    first_unseen,
    int_or_none,
    is_disambiguation,
    is_non_brand_detail,
    normalize_profile_name,
    select_wikidata_candidate,
    select_wikipedia_candidate,
    selected_page_id,
    selected_title,
    strip_html,
    unique,
    wiki_url,
)
from ad_classifier.brand_profiles.wikidata import (
    ENTITY_PROPS,
    METRIC_PROPS,
    claim_time,
    claim_url,
    collect_label_qids,
    entity_description,
    entity_ids,
    entity_label,
    entity_labels,
    entity_self_label_map,
    labels_for_qids,
    metrics,
)
from ad_classifier.models.ads import utc_now
from ad_classifier.models.brand_profiles import BrandProfile, BrandProfileLookupStep

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_DATA = "https://www.wikidata.org/wiki/Special:EntityData"


class BrandProfileNotFoundError(ValueError):
    pass


class WikimediaBrandProfileClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_s: float = 10.0,
        cache_days: int = 90,
        max_candidates: int = 5,
        max_parent_depth: int = 3,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_s = timeout_s
        self.cache_days = cache_days
        self.max_candidates = max_candidates
        self.max_parent_depth = max_parent_depth
        self.http_client = http_client

    def fetch(self, name: str, *, context: SearchContext | None = None) -> BrandProfile:
        normalized = normalize_profile_name(name)
        if not normalized:
            raise ValueError("brand or advertiser name is empty")

        fetched_at = utc_now()
        expires_at = fetched_at + timedelta(days=self.cache_days)
        steps: list[BrandProfileLookupStep] = []
        source_json: dict[str, Any] = {"query_name": name, "normalized_name": normalized}

        candidates = self._wikipedia_search(name, steps)
        source_json["wikipedia_candidates"] = candidate_digest(candidates)

        # Retry with enriched queries if initial results look like disambiguation.
        if is_disambiguation(candidates) and context is not None:
            for fallback_query in enriched_queries(name, context):
                fallback_candidates = self._wikipedia_search(fallback_query, steps)
                if fallback_candidates and not is_disambiguation(fallback_candidates):
                    candidates = fallback_candidates
                    source_json["wikipedia_candidates_fallback"] = {
                        "query": fallback_query,
                        "candidates": candidate_digest(candidates),
                    }
                    steps.append(
                        BrandProfileLookupStep(
                            source="wikipedia",
                            action="fallback_query_selected",
                            query=fallback_query,
                            result_count=len(candidates),
                            detail="replaced disambiguation results",
                        )
                    )
                    break

        selected = select_wikipedia_candidate(name, candidates, context=context)
        if selected is None and context is not None:
            for fallback_query in enriched_queries(name, context):
                fallback_candidates = self._wikipedia_search(fallback_query, steps)
                fallback_selected = select_wikipedia_candidate(
                    name,
                    fallback_candidates,
                    context=context,
                )
                if fallback_selected is None:
                    continue
                candidates = fallback_candidates
                selected = fallback_selected
                source_json["wikipedia_candidates_fallback"] = {
                    "query": fallback_query,
                    "candidates": candidate_digest(candidates),
                }
                steps.append(
                    BrandProfileLookupStep(
                        source="wikipedia",
                        action="fallback_query_selected",
                        query=fallback_query,
                        result_count=len(candidates),
                        detail="replaced rejected non-brand results",
                    )
                )
                break

        page_info: dict[str, Any] = {}
        if selected:
            page_info = self._wikipedia_page_info(str(selected["title"]), steps)
            source_json["selected_wikipedia_candidate"] = {
                "title": selected.get("title"),
                "pageid": selected.get("pageid"),
            }

        summary = self._wikipedia_summary(page_info.get("title") or selected_title(selected), steps)
        qid = page_info.get("wikidata_qid")
        if not qid:
            qid = self._wikidata_search(name, steps, context=context)
        if selected is None and not qid:
            steps.append(
                BrandProfileLookupStep(
                    source="wikimedia",
                    action="no_relevant_candidate",
                    query=name,
                    result_count=0,
                    detail="no candidate title or label matched the requested name",
                )
            )
            raise BrandProfileNotFoundError(f"no relevant Wikimedia profile found for {name}")

        entity = self._wikidata_entity(str(qid), steps) if qid else {}
        labels = self._resolve_labels(collect_label_qids(entity), steps)
        labels.update(entity_self_label_map(entity))

        parent_ids = entity_ids(entity, "P749", limit=5)
        owner_ids = entity_ids(entity, "P127", limit=5)
        corporate_chain = self._corporate_chain(entity, labels, steps)

        display_name = entity_label(entity) or page_info.get("title") or selected_title(selected)
        description = entity_description(entity) or summary.get("description")
        if description and is_non_brand_detail(description):
            steps.append(
                BrandProfileLookupStep(
                    source="wikidata",
                    action="rejected_non_brand_entity",
                    qid=str(qid) if qid else None,
                    detail=description,
                )
            )
            raise BrandProfileNotFoundError(f"no relevant Wikimedia profile found for {name}")
        wikipedia_url = (
            page_info.get("fullurl")
            or summary.get("content_urls", {}).get("desktop", {}).get("page")
            or wiki_url(page_info.get("title") or selected_title(selected))
        )
        source_urls = unique(
            [
                wikipedia_url,
                f"https://www.wikidata.org/wiki/{qid}" if qid else None,
                claim_url(entity, "P856"),
            ]
        )

        source_json["wikidata_qid"] = qid
        source_json["wikidata_claim_counts"] = {
            prop: len(entity.get("claims", {}).get(prop, []))
            for prop in [*ENTITY_PROPS.keys(), *METRIC_PROPS.keys(), "P856", "P571"]
        }

        return BrandProfile(
            normalized_name=normalized,
            query_name=name,
            display_name=display_name,
            description=description,
            summary=summary.get("extract"),
            wikipedia_title=page_info.get("title") or selected_title(selected),
            wikipedia_url=wikipedia_url,
            wikipedia_page_id=int_or_none(page_info.get("pageid") or selected_page_id(selected)),
            wikidata_qid=str(qid) if qid else None,
            parent_companies=labels_for_qids(parent_ids, labels),
            owners=labels_for_qids(owner_ids, labels),
            corporate_chain=corporate_chain,
            industries=entity_labels(entity, "P452", labels, limit=8),
            official_website=claim_url(entity, "P856"),
            headquarters=entity_labels(entity, "P159", labels, limit=5),
            countries=entity_labels(entity, "P17", labels, limit=5),
            inception=claim_time(entity, "P571"),
            founded_by=entity_labels(entity, "P112", labels, limit=5),
            subsidiaries=entity_labels(entity, "P355", labels, limit=12),
            key_metrics=metrics(entity, labels),
            lookup_steps=steps,
            source_urls=source_urls,
            source_json=source_json,
            fetched_at=fetched_at,
            expires_at=expires_at,
        )

    def _new_client(self) -> httpx.Client:
        timeout = httpx.Timeout(self.timeout_s, connect=min(self.timeout_s, 5.0))
        return httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
        )

    def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.http_client is not None:
            response = self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

        with self._new_client() as client:
            response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _wikipedia_search(
        self,
        name: str,
        steps: list[BrandProfileLookupStep],
    ) -> list[dict[str, Any]]:
        data = self._get_json(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": name,
                "srlimit": self.max_candidates,
                "format": "json",
                "utf8": 1,
            },
        )
        rows = data.get("query", {}).get("search", [])
        candidates = [row for row in rows if isinstance(row, dict)]
        steps.append(
            BrandProfileLookupStep(
                source="wikipedia",
                action="search",
                query=name,
                result_count=len(candidates),
            )
        )
        for candidate in candidates[: self.max_candidates]:
            steps.append(
                BrandProfileLookupStep(
                    source="wikipedia",
                    action="candidate",
                    title=str(candidate.get("title") or ""),
                    result_count=int_or_none(candidate.get("pageid")),
                    detail=strip_html(str(candidate.get("snippet") or ""))[:240] or None,
                )
            )
        return candidates

    def _wikipedia_page_info(
        self,
        title: str,
        steps: list[BrandProfileLookupStep],
    ) -> dict[str, Any]:
        data = self._get_json(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "titles": title,
                "prop": "pageprops|info",
                "inprop": "url",
                "redirects": 1,
                "format": "json",
            },
        )
        pages = data.get("query", {}).get("pages", {})
        page = next((p for p in pages.values() if isinstance(p, dict)), {})
        qid = page.get("pageprops", {}).get("wikibase_item")
        steps.append(
            BrandProfileLookupStep(
                source="wikipedia",
                action="page_info",
                title=str(page.get("title") or title),
                qid=str(qid) if qid else None,
                url=page.get("fullurl"),
                result_count=int_or_none(page.get("pageid")),
            )
        )
        return {
            "title": page.get("title") or title,
            "pageid": page.get("pageid"),
            "fullurl": page.get("fullurl"),
            "wikidata_qid": qid,
        }

    def _wikipedia_summary(
        self,
        title: str | None,
        steps: list[BrandProfileLookupStep],
    ) -> dict[str, Any]:
        if not title:
            return {}
        data = self._get_json(f"{WIKIPEDIA_SUMMARY_API}/{quote(title, safe='')}")
        steps.append(
            BrandProfileLookupStep(
                source="wikipedia",
                action="summary",
                title=title,
                url=data.get("content_urls", {}).get("desktop", {}).get("page"),
                status="ok" if data else "empty",
            )
        )
        return data

    def _wikidata_search(
        self,
        name: str,
        steps: list[BrandProfileLookupStep],
        *,
        context: SearchContext | None = None,
    ) -> str | None:
        data = self._get_json(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "limit": self.max_candidates,
                "format": "json",
            },
        )
        rows = data.get("search", [])
        candidates = [row for row in rows if isinstance(row, dict)]
        selected = select_wikidata_candidate(name, candidates, context=context)

        # Retry with enriched queries if Wikidata results are ambiguous.
        if selected is None and context is not None:
            for fallback_query in enriched_queries(name, context):
                fallback_data = self._get_json(
                    WIKIDATA_API,
                    params={
                        "action": "wbsearchentities",
                        "search": fallback_query,
                        "language": "en",
                        "limit": self.max_candidates,
                        "format": "json",
                    },
                )
                fallback_rows = fallback_data.get("search", [])
                fallback_candidates = [row for row in fallback_rows if isinstance(row, dict)]
                fallback_selected = select_wikidata_candidate(name, fallback_candidates, context=context)
                if fallback_selected:
                    selected = fallback_selected
                    steps.append(
                        BrandProfileLookupStep(
                            source="wikidata",
                            action="fallback_query_selected",
                            query=fallback_query,
                            qid=str(selected.get("id") or ""),
                            result_count=len(fallback_candidates),
                            detail="replaced ambiguous wikidata results",
                        )
                    )
                    break
        steps.append(
            BrandProfileLookupStep(
                source="wikidata",
                action="search",
                query=name,
                qid=selected.get("id") if selected else None,
                result_count=len(candidates),
                detail=selected.get("description") if selected else None,
            )
        )
        return str(selected["id"]) if selected and selected.get("id") else None

    def _wikidata_entity(
        self,
        qid: str,
        steps: list[BrandProfileLookupStep],
        *,
        action: str = "entity",
    ) -> dict[str, Any]:
        data = self._get_json(f"{WIKIDATA_ENTITY_DATA}/{qid}.json")
        entity = data.get("entities", {}).get(qid, {})
        steps.append(
            BrandProfileLookupStep(
                source="wikidata",
                action=action,
                qid=qid,
                url=f"https://www.wikidata.org/wiki/{qid}",
                status="ok" if entity else "empty",
            )
        )
        return entity if isinstance(entity, dict) else {}

    def _resolve_labels(
        self,
        qids: list[str],
        steps: list[BrandProfileLookupStep],
    ) -> dict[str, str]:
        qids = unique(qids)
        if not qids:
            return {}
        data = self._get_json(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(qids[:50]),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
        )
        entities = data.get("entities", {})
        steps.append(
            BrandProfileLookupStep(
                source="wikidata",
                action="resolve_labels",
                result_count=len(entities) if isinstance(entities, dict) else 0,
            )
        )
        labels: dict[str, str] = {}
        if not isinstance(entities, dict):
            return labels
        for qid, entity in entities.items():
            if isinstance(entity, dict):
                value = entity.get("labels", {}).get("en", {}).get("value")
                if value:
                    labels[str(qid)] = str(value)
        return labels

    def _corporate_chain(
        self,
        entity: dict[str, Any],
        labels: dict[str, str],
        steps: list[BrandProfileLookupStep],
    ) -> list[str]:
        chain: list[str] = []
        current = entity
        seen: set[str] = set()
        for depth in range(self.max_parent_depth):
            parent_id = first_unseen(
                [*entity_ids(current, "P749"), *entity_ids(current, "P127")],
                seen,
            )
            if parent_id is None:
                break
            seen.add(parent_id)
            if parent_id not in labels:
                labels.update(self._resolve_labels([parent_id], steps))
            chain.append(labels.get(parent_id, parent_id))
            current = self._wikidata_entity(
                parent_id,
                steps,
                action=f"parent_entity_depth_{depth + 1}",
            )
            labels.update(entity_self_label_map(current))
        return chain
