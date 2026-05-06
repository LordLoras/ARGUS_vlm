from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.db.repositories import JobRepository

router = APIRouter(tags=["jobs"])
TERMINAL_STATES = {"completed", "failed", "cancelled"}


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
                "state": job.state,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
            }
            if payload != last_payload:
                yield {"event": "job", "data": json.dumps(payload)}
                last_payload = payload

            if job.state in TERMINAL_STATES:
                yield {"event": "done", "data": json.dumps({"type": "done", "state": job.state})}
                break
            await asyncio.sleep(poll_s)

    return EventSourceResponse(generate())
