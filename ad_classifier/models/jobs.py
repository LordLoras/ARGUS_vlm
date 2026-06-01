from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel

JobState = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class JobRecord(StrictModel):
    id: str
    ad_id: str | None = None
    state: JobState
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    stage: str | None = None
    message: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
