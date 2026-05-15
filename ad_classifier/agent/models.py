from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel


class ToolSpec(StrictModel):
    """OpenAI-compatible function spec."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


class ToolCall(StrictModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(StrictModel):
    """Result returned by an agent tool.

    `truncated` lets the model surface "ask the user to narrow the filter"
    when a list query had to drop rows.
    """

    name: str
    ok: bool
    data: Any = None
    error: str | None = None
    truncated: bool = False
    row_count: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "truncated": self.truncated,
            "row_count": self.row_count,
        }


AgentEventType = Literal[
    "session",
    "message",
    "tool_call",
    "tool_result",
    "final",
    "error",
    "done",
]


class AgentEvent(StrictModel):
    type: AgentEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentAnswer(StrictModel):
    session_id: str
    text: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    iterations: int = Field(ge=0)
    truncated: bool = False
    error: str | None = None
