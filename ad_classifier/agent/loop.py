from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ad_classifier.agent.catalog import ToolCatalog
from ad_classifier.agent.client import AgentClient, AgentClientError, AgentMessage
from ad_classifier.agent.models import AgentAnswer, AgentEvent, ToolCall, ToolResult
from ad_classifier.agent.prompt import render_agent_prompt
from ad_classifier.agent.schema import render_schema_summary
from ad_classifier.agent.tools.base import ToolContext
from ad_classifier.config import AgentConfig
from ad_classifier.db.repositories.agent import (
    AgentMessageRepository,
    AgentSessionRepository,
)
from ad_classifier.models.agent import AgentMessageRecord, AgentSessionRecord


def _new_session_id() -> str:
    return f"agent_{uuid.uuid4().hex[:12]}"


@dataclass
class AgentRunContext:
    """All collaborators an AgentLoop needs.

    The persistence connection is mutable (writes session + message rows) and
    is separate from the read-only `tool_conn` used by tools, mirroring the
    spec rule that the agent's tool surface cannot mutate the DB.
    """

    persistence_conn: sqlite3.Connection
    tool_conn: sqlite3.Connection
    catalog: ToolCatalog
    client: AgentClient
    config: AgentConfig
    text_embedder_factory: Callable[[], Any] | None = None
    vector_store_factory: Callable[[sqlite3.Connection], Any] | None = None


class AgentLoop:
    def __init__(self, run: AgentRunContext) -> None:
        self.run = run

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def ensure_session(self, session_id: str | None = None) -> str:
        repo = AgentSessionRepository(self.run.persistence_conn)
        if session_id is not None:
            existing = repo.get(session_id)
            if existing is not None:
                return existing.id
        new_id = session_id or _new_session_id()
        repo.create(AgentSessionRecord(id=new_id))
        self.run.persistence_conn.commit()
        return new_id

    def ask(self, user_text: str, *, session_id: str | None = None) -> AgentAnswer:
        events: list[AgentEvent] = list(self.stream(user_text, session_id=session_id))
        return _answer_from_events(events)

    def stream(
        self, user_text: str, *, session_id: str | None = None
    ) -> Iterator[AgentEvent]:
        sid = self.ensure_session(session_id)
        yield AgentEvent(type="session", payload={"session_id": sid})

        history = _build_history(self.run.persistence_conn, sid)
        system_prompt = render_agent_prompt(
            self.run.catalog,
            render_schema_summary(self.run.tool_conn),
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        # Persist the user turn before talking to the model so the audit trail
        # survives a crash mid-call.
        self._record_user(sid, user_text)
        yield AgentEvent(
            type="message",
            payload={"role": "user", "content": user_text, "session_id": sid},
        )

        ctx = ToolContext(
            conn=self.run.tool_conn,
            config=self.run.config,
            text_embedder_factory=self.run.text_embedder_factory,
            vector_store_factory=self.run.vector_store_factory,
        )
        tools = self.run.catalog.openai_tools()

        final_text: str | None = None
        for iteration in range(1, self.run.config.max_iterations + 1):
            try:
                response = self.run.client.complete(messages, tools=tools)
            except AgentClientError as exc:
                error = f"agent client error: {exc}"
                self._record_assistant_text(sid, error)
                yield AgentEvent(
                    type="error", payload={"session_id": sid, "message": str(exc)}
                )
                yield AgentEvent(
                    type="final",
                    payload={
                        "session_id": sid,
                        "text": error,
                        "iterations": iteration - 1,
                        "error": str(exc),
                    },
                )
                yield AgentEvent(type="done", payload={"session_id": sid})
                return

            assistant_message = _serialize_assistant(response)
            messages.append(assistant_message)

            if not response.tool_calls:
                final_text = response.content or ""
                self._record_assistant_text(sid, final_text)
                yield AgentEvent(
                    type="message",
                    payload={"role": "assistant", "content": final_text, "session_id": sid},
                )
                yield AgentEvent(
                    type="final",
                    payload={
                        "session_id": sid,
                        "text": final_text,
                        "iterations": iteration,
                        "error": None,
                    },
                )
                yield AgentEvent(type="done", payload={"session_id": sid})
                return

            for call in response.tool_calls:
                yield AgentEvent(
                    type="tool_call",
                    payload={
                        "session_id": sid,
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                )
                if "_raw" in call.arguments and len(call.arguments) == 1:
                    # Malformed args — surface a structured error rather than crashing
                    result = ToolResult(
                        name=call.name,
                        ok=False,
                        error=f"could not parse tool arguments: {call.arguments['_raw'][:200]!r}",
                    )
                else:
                    result = self.run.catalog.call(call.name, call.arguments, ctx)

                self._record_tool(sid, call, result)
                messages.append(_serialize_tool_result(call, result))
                yield AgentEvent(
                    type="tool_result",
                    payload={
                        "session_id": sid,
                        "id": call.id,
                        "name": call.name,
                        "ok": result.ok,
                        "truncated": result.truncated,
                        "row_count": result.row_count,
                        "error": result.error,
                        "data": result.data,
                    },
                )

        # Iteration cap reached without final answer
        cap_msg = (
            "Reached the agent iteration cap without producing a final answer. "
            "Try asking the question more narrowly."
        )
        self._record_assistant_text(sid, cap_msg)
        yield AgentEvent(type="error", payload={"session_id": sid, "message": cap_msg})
        yield AgentEvent(
            type="final",
            payload={
                "session_id": sid,
                "text": cap_msg,
                "iterations": self.run.config.max_iterations,
                "error": "iteration_cap_reached",
            },
        )
        yield AgentEvent(type="done", payload={"session_id": sid})

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _record_user(self, session_id: str, text: str) -> None:
        AgentMessageRepository(self.run.persistence_conn).append(
            AgentMessageRecord(session_id=session_id, role="user", content=text)
        )
        self.run.persistence_conn.commit()

    def _record_assistant_text(self, session_id: str, text: str) -> None:
        AgentMessageRepository(self.run.persistence_conn).append(
            AgentMessageRecord(session_id=session_id, role="assistant", content=text)
        )
        self.run.persistence_conn.commit()

    def _record_tool(self, session_id: str, call: ToolCall, result: ToolResult) -> None:
        AgentMessageRepository(self.run.persistence_conn).append(
            AgentMessageRecord(
                session_id=session_id,
                role="tool",
                content=result.error if not result.ok and result.error else "",
                tool_name=call.name,
                tool_args_json=json.dumps(call.arguments),
                tool_result_json=json.dumps(result.to_payload(), default=str),
            )
        )
        self.run.persistence_conn.commit()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _serialize_assistant(message: AgentMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in message.tool_calls
        ]
    return out


def _serialize_tool_result(call: ToolCall, result: ToolResult) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "name": call.name,
        "content": json.dumps(result.to_payload(), default=str),
    }


def _build_history(conn: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    """Replay prior turns so the agent has multi-turn context.

    We omit prior tool_calls/tool_results for simplicity: the agent only sees
    user/assistant text from earlier turns. Tool outputs are still preserved
    in the DB for auditing via list_messages.
    """
    rows = AgentMessageRepository(conn).list_for_session(session_id)
    out: list[dict[str, Any]] = []
    for record in rows:
        if record.role in ("user", "assistant") and record.content:
            out.append({"role": record.role, "content": record.content})
    return out


def _answer_from_events(events: list[AgentEvent]) -> AgentAnswer:
    session_id = ""
    final_text = ""
    iterations = 0
    error: str | None = None
    truncated = False
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []

    for event in events:
        if event.type == "session":
            session_id = event.payload.get("session_id", session_id)
        elif event.type == "tool_call":
            tool_calls.append(
                ToolCall(
                    id=event.payload["id"],
                    name=event.payload["name"],
                    arguments=event.payload.get("arguments", {}),
                )
            )
        elif event.type == "tool_result":
            tool_results.append(
                ToolResult(
                    name=event.payload["name"],
                    ok=event.payload.get("ok", False),
                    error=event.payload.get("error"),
                    truncated=event.payload.get("truncated", False),
                    row_count=event.payload.get("row_count"),
                    data=event.payload.get("data"),
                )
            )
            if event.payload.get("truncated"):
                truncated = True
        elif event.type == "final":
            final_text = event.payload.get("text", "")
            iterations = event.payload.get("iterations", 0)
            error = event.payload.get("error")

    return AgentAnswer(
        session_id=session_id,
        text=final_text,
        tool_calls=tool_calls,
        tool_results=tool_results,
        iterations=iterations,
        truncated=truncated,
        error=error,
    )
