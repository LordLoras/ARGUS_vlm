from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from ad_classifier.db.repositories.base import row_to_dict
from ad_classifier.models.brand_profiles import BrandProfile, BrandProfileLookupStep


class BrandProfileRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, profile: BrandProfile) -> None:
        self.conn.execute(
            """
            INSERT INTO brand_profiles (
              normalized_name, query_name, display_name, description, summary,
              wikipedia_title, wikipedia_url, wikipedia_page_id, wikidata_qid,
              parent_companies_json, owners_json, corporate_chain_json, industries_json,
              official_website, headquarters_json, countries_json, inception, founded_by_json,
              subsidiaries_json, key_metrics_json, lookup_steps_json, source_urls_json,
              source_json, fetched_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(normalized_name) DO UPDATE SET
              query_name = excluded.query_name,
              display_name = excluded.display_name,
              description = excluded.description,
              summary = excluded.summary,
              wikipedia_title = excluded.wikipedia_title,
              wikipedia_url = excluded.wikipedia_url,
              wikipedia_page_id = excluded.wikipedia_page_id,
              wikidata_qid = excluded.wikidata_qid,
              parent_companies_json = excluded.parent_companies_json,
              owners_json = excluded.owners_json,
              corporate_chain_json = excluded.corporate_chain_json,
              industries_json = excluded.industries_json,
              official_website = excluded.official_website,
              headquarters_json = excluded.headquarters_json,
              countries_json = excluded.countries_json,
              inception = excluded.inception,
              founded_by_json = excluded.founded_by_json,
              subsidiaries_json = excluded.subsidiaries_json,
              key_metrics_json = excluded.key_metrics_json,
              lookup_steps_json = excluded.lookup_steps_json,
              source_urls_json = excluded.source_urls_json,
              source_json = excluded.source_json,
              fetched_at = excluded.fetched_at,
              expires_at = excluded.expires_at
            """,
            (
                profile.normalized_name,
                profile.query_name,
                profile.display_name,
                profile.description,
                profile.summary,
                profile.wikipedia_title,
                profile.wikipedia_url,
                profile.wikipedia_page_id,
                profile.wikidata_qid,
                json.dumps(profile.parent_companies),
                json.dumps(profile.owners),
                json.dumps(profile.corporate_chain),
                json.dumps(profile.industries),
                profile.official_website,
                json.dumps(profile.headquarters),
                json.dumps(profile.countries),
                profile.inception,
                json.dumps(profile.founded_by),
                json.dumps(profile.subsidiaries),
                json.dumps(profile.key_metrics),
                json.dumps([step.model_dump() for step in profile.lookup_steps]),
                json.dumps(profile.source_urls),
                json.dumps(profile.source_json),
                profile.fetched_at.isoformat(),
                profile.expires_at.isoformat() if profile.expires_at else None,
            ),
        )

    def get(self, normalized_name: str) -> BrandProfile | None:
        row = self.conn.execute(
            "SELECT * FROM brand_profiles WHERE normalized_name = ?",
            (normalized_name,),
        ).fetchone()
        data = row_to_dict(row)
        if data is None:
            return None
        return _to_profile(data)

    def delete(self, normalized_name: str) -> None:
        self.conn.execute(
            "DELETE FROM brand_profiles WHERE normalized_name = ?",
            (normalized_name,),
        )


def _to_profile(data: dict[str, Any]) -> BrandProfile:
    return BrandProfile(
        normalized_name=str(data["normalized_name"]),
        query_name=str(data["query_name"]),
        display_name=data.get("display_name"),
        description=data.get("description"),
        summary=data.get("summary"),
        wikipedia_title=data.get("wikipedia_title"),
        wikipedia_url=data.get("wikipedia_url"),
        wikipedia_page_id=data.get("wikipedia_page_id"),
        wikidata_qid=data.get("wikidata_qid"),
        parent_companies=_json_list(data.get("parent_companies_json")),
        owners=_json_list(data.get("owners_json")),
        corporate_chain=_json_list(data.get("corporate_chain_json")),
        industries=_json_list(data.get("industries_json")),
        official_website=data.get("official_website"),
        headquarters=_json_list(data.get("headquarters_json")),
        countries=_json_list(data.get("countries_json")),
        inception=data.get("inception"),
        founded_by=_json_list(data.get("founded_by_json")),
        subsidiaries=_json_list(data.get("subsidiaries_json")),
        key_metrics=_json_dict(data.get("key_metrics_json")),
        lookup_steps=[
            BrandProfileLookupStep.model_validate(step)
            for step in _json_list(data.get("lookup_steps_json"))
            if isinstance(step, dict)
        ],
        source_urls=_json_list(data.get("source_urls_json")),
        source_json=_json_dict(data.get("source_json")),
        fetched_at=_parse_datetime(data["fetched_at"]),
        expires_at=_parse_datetime(data.get("expires_at")),
    )


def _json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    value = json.loads(raw)
    return value if isinstance(value, list) else []


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
