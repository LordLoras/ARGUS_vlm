from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ad_classifier.models.ads import utc_now
from ad_classifier.models.common import StrictModel

AgentRole = Literal["user", "assistant", "tool"]


class AgentSessionRecord(StrictModel):
    id: str
    created_at: datetime = Field(default_factory=utc_now)
    user_label: str | None = None
    context_json: str | None = None


class AgentMessageRecord(StrictModel):
    id: int | None = None
    session_id: str
    role: AgentRole
    content: str
    tool_name: str | None = None
    tool_args_json: str | None = None
    tool_result_json: str | None = None
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
