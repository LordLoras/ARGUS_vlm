from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from ad_classifier.models.ads import utc_now
from ad_classifier.models.common import StrictModel

AssignmentSource = Literal["auto", "user"]


class CampaignRecord(StrictModel):
    id: str
    name: str
    advertiser: str | None = None
    brand: str | None = None
    theme: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    created_by: AssignmentSource
    description: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AdCampaignRecord(StrictModel):
    ad_id: str
    campaign_id: str
    similarity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    assigned_by: AssignmentSource
    assigned_at: datetime = Field(default_factory=utc_now)
