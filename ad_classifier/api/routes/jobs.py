from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from ad_classifier.api.artifacts import cleanup_ad_artifacts
from ad_classifier.api.deps import get_config, get_config_file, open_request_db
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.db.repositories import AdRepository, JobRepository
from ad_classifier.search.fts import fts_delete
from ad_classifier.vectors.sqlite_vec import SqliteVecStore

router = APIRouter(tags=["jobs"])
TERMINAL_STATES = {"completed", "failed", "cancelled"}


@router.get("/jobs")
def list_jobs(
    request: Request,
    state: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        items = JobRepository(conn).list(state=state, limit=limit, offset=offset)
        return {"items": items, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        job = JobRepository(conn).get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.model_dump(mode="json")
    finally:
        conn.close()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        repo = JobRepository(conn)
        changed = repo.cancel(job_id)
        conn.commit()
        job = repo.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {"cancelled": changed, "job": job.model_dump(mode="json")}
    finally:
        conn.close()


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: str,
    request: Request,
    cleanup_artifacts: bool = Query(default=True),
) -> dict[str, Any]:
    config = get_config(request)
    config_file = get_config_file(request)
    conn = open_request_db(request)
    removed: list[str] = []
    deleted_ad_id: str | None = None
    try:
        jobs = JobRepository(conn)
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")

        ad = AdRepository(conn).get(job.ad_id) if job.ad_id else None
        if job.state in {"queued", "running"}:
            jobs.cancel(job_id, message="deleted by user")

        if ad is not None:
            deleted_ad_id = ad.id
            fts_delete(conn, ad.id)
            load_sqlite_vec(conn)
            store = SqliteVecStore(
                conn,
                text_dim=config.vector_store.text_dim,
                visual_dim=config.vector_store.visual_dim,
            )
            store.ensure_tables()
            store.delete(ad.id)
            AdRepository(conn).delete(ad.id)
        else:
            jobs.delete(job_id)
        conn.commit()

        if cleanup_artifacts and job.ad_id:
            removed = cleanup_ad_artifacts(
                config,
                config_file,
                job.ad_id,
                ad.source_path if ad is not None else None,
            )
        return {
            "deleted": job_id,
            "ad_id": deleted_ad_id or job.ad_id,
            "artifacts_removed": removed,
        }
    finally:
        conn.close()


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> EventSourceResponse:
    config = get_config(request)
    poll_s = max(config.worker.poll_interval_ms / 1000, 0.05)

    async def generate():
        last_payload: dict[str, Any] | None = None
        while True:
            if await request.is_disconnected():
                break
            conn = open_request_db(request)
            try:
                job = JobRepository(conn).get(job_id)
            finally:
                conn.close()
            if job is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"type": "error", "message": "job not found"}),
                }
                break

            payload = {
                "type": "job",
                "job_id": job.id,
                "ad_id": job.ad_id,
                "state": job.state,
                "progress": job.progress,
                "stage": job.stage,
                "message": job.message,
                "error": job.error,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }
            if payload != last_payload:
                yield {"event": "job", "data": json.dumps(payload)}
                last_payload = payload

            if job.state in TERMINAL_STATES:
                yield {"event": "done", "data": json.dumps({"type": "done", "state": job.state})}
                break
            await asyncio.sleep(poll_s)

    return EventSourceResponse(generate())
