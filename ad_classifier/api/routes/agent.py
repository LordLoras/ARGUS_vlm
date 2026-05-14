from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ad_classifier.agent.catalog import ToolCatalog
from ad_classifier.agent.client import AgentClient, HTTPAgentClient
from ad_classifier.agent.loop import AgentLoop, AgentRunContext
from ad_classifier.agent.prompt import render_agent_prompt
from ad_classifier.agent.schema import render_schema_summary
from ad_classifier.api.deps import get_config, get_db_path
from ad_classifier.config import AgentConfig, AppConfig
from ad_classifier.db.connection import open_database, open_readonly_database
from ad_classifier.db.repositories.agent import (
    AgentMessageRepository,
    AgentSessionRepository,
)

router = APIRouter(tags=["agent"])

AgentClientFactory = Callable[[AgentConfig], AgentClient]


class AskRequest(BaseModel):
    text: str = Field(min_length=1)


def _client_factory(request: Request) -> AgentClientFactory:
    factory = getattr(request.app.state, "agent_client_factory", None)
    if factory is not None:
        return factory  # type: ignore[no-any-return]
    return _default_client_factory


def _default_client_factory(config: AgentConfig) -> AgentClient:
    return HTTPAgentClient(
        endpoint=config.endpoint.endpoint,
        model=config.endpoint.model,
        api_key_env=config.endpoint.api_key_env,
        timeout_s=config.endpoint.timeout_s,
        max_retries=config.endpoint.max_retries,
        retry_delay_s=config.endpoint.retry_delay_s,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        stream=config.endpoint.stream if config.endpoint.stream is not None else True,
    )


def _build_loop(request: Request) -> tuple[AgentLoop, sqlite3.Connection, sqlite3.Connection]:
    config: AppConfig = get_config(request)
    db_path: Path = get_db_path(request)
    persistence = open_database(db_path)
    tool_conn = open_readonly_database(db_path)
    catalog = ToolCatalog()
    client = _client_factory(request)(config.agent)
    text_factory = getattr(request.app.state, "agent_text_embedder_factory", None)
    visual_text_factory = getattr(request.app.state, "agent_visual_text_embedder_factory", None)
    vector_factory = getattr(request.app.state, "agent_vector_store_factory", None)
    run = AgentRunContext(
        persistence_conn=persistence,
        tool_conn=tool_conn,
        catalog=catalog,
        client=client,
        config=config.agent,
        search_config=config.search,
        text_embedder_factory=(lambda: text_factory(config)) if text_factory else None,
        visual_text_embedder_factory=(
            (lambda: visual_text_factory(config)) if visual_text_factory else None
        ),
        vector_store_factory=(lambda c: vector_factory(config, c)) if vector_factory else None,
    )
    return AgentLoop(run), persistence, tool_conn


@router.post("/agent/sessions")
def create_session(request: Request) -> dict[str, Any]:
    db_path: Path = get_db_path(request)
    conn = open_database(db_path)
    try:
        repo = AgentSessionRepository(conn)
        from ad_classifier.agent.loop import _new_session_id  # noqa: PLC0415
        from ad_classifier.models.agent import AgentSessionRecord  # noqa: PLC0415

        session_id = _new_session_id()
        repo.create(AgentSessionRecord(id=session_id))
        conn.commit()
        return {"session_id": session_id}
    finally:
        conn.close()


@router.get("/agent/sessions")
def list_sessions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    db_path: Path = get_db_path(request)
    conn = open_database(db_path)
    try:
        sessions = AgentSessionRepository(conn).list(limit=limit, offset=offset)
        return {
            "items": [s.model_dump(mode="json") for s in sessions],
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()


@router.get("/agent/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> dict[str, Any]:
    db_path: Path = get_db_path(request)
    conn = open_database(db_path)
    try:
        session = AgentSessionRepository(conn).get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        messages = AgentMessageRepository(conn).list_for_session(session_id)
        return {
            "session": session.model_dump(mode="json"),
            "messages": [m.model_dump(mode="json") for m in messages],
        }
    finally:
        conn.close()


@router.delete("/agent/sessions/{session_id}")
def delete_session(session_id: str, request: Request) -> dict[str, Any]:
    db_path: Path = get_db_path(request)
    conn = open_database(db_path)
    try:
        repo = AgentSessionRepository(conn)
        existing = repo.get(session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="session not found")
        repo.delete(session_id)
        conn.commit()
        return {"deleted": session_id}
    finally:
        conn.close()


@router.post("/agent/sessions/{session_id}/query")
def agent_query(session_id: str, body: AskRequest, request: Request) -> dict[str, Any]:
    loop, persistence, tool_conn = _build_loop(request)
    try:
        answer = loop.ask(body.text, session_id=session_id)
        return answer.model_dump(mode="json")
    finally:
        persistence.close()
        tool_conn.close()


_SENTINEL_END = object()


def _next_or_sentinel(iterator):
    """Return next(iterator) or the sentinel when the iterator is exhausted.

    PEP 479: StopIteration cannot propagate through a coroutine boundary, so
    asyncio.to_thread(next, ...) wraps it in RuntimeError. Use a sentinel value
    instead so the SSE pump can detect end-of-stream cleanly.
    """
    try:
        return next(iterator)
    except StopIteration:
        return _SENTINEL_END


@router.get("/agent/sessions/{session_id}/events")
async def agent_events(session_id: str, q: str, request: Request) -> EventSourceResponse:
    loop, persistence, tool_conn = _build_loop(request)

    async def stream():
        # The loop is a sync generator (httpx is sync). Pull each event in a
        # threadpool so the FastAPI event loop stays responsive, and yield each
        # one immediately so sse-starlette flushes it to the client.
        iterator = iter(loop.stream(q, session_id=session_id))
        try:
            while True:
                event = await asyncio.to_thread(_next_or_sentinel, iterator)
                if event is _SENTINEL_END:
                    break
                yield {
                    "event": event.type,
                    "data": json.dumps(event.payload, default=str),
                }
        except Exception as exc:  # pragma: no cover - surfaced as SSE error
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "session_id": session_id,
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                ),
            }
            yield {
                "event": "done",
                "data": json.dumps({"session_id": session_id}),
            }
        finally:
            persistence.close()
            tool_conn.close()

    return EventSourceResponse(stream())


@router.get("/agent/tools")
def list_tools(request: Request) -> dict[str, Any]:
    catalog = ToolCatalog()
    return {"tools": [spec.model_dump() for spec in catalog.specs()]}


@router.get("/agent/schema")
def get_agent_schema(request: Request) -> dict[str, Any]:
    db_path: Path = get_db_path(request)
    conn = open_readonly_database(db_path)
    try:
        summary = render_schema_summary(conn)
        catalog = ToolCatalog()
        prompt = render_agent_prompt(catalog, summary)
        return {"schema": summary, "system_prompt": prompt}
    finally:
        conn.close()
