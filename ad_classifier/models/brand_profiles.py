from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ad_classifier.models.ads import utc_now
from ad_classifier.models.common import StrictModel


class BrandProfileLookupStep(StrictModel):
    source: str
    action: str
    status: str = "ok"
    query: str | None = None
    title: str | None = None
    qid: str | None = None
    url: str | None = None
    result_count: int | None = Field(default=None, ge=0)
    detail: str | None = None


class BrandProfile(StrictModel):
    normalized_name: str
    query_name: str
    display_name: str | None = None
    description: str | None = None
    summary: str | None = None
    wikipedia_title: str | None = None
    wikipedia_url: str | None = None
    wikipedia_page_id: int | None = Field(default=None, ge=0)
    wikidata_qid: str | None = None
    parent_companies: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
    corporate_chain: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    official_website: str | None = None
    headquarters: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    inception: str | None = None
    founded_by: list[str] = Field(default_factory=list)
    subsidiaries: list[str] = Field(default_factory=list)
    key_metrics: dict[str, str | list[str]] = Field(default_factory=dict)
    lookup_steps: list[BrandProfileLookupStep] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_json: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
