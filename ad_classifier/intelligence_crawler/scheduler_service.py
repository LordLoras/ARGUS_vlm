"""Due-source scheduler process; only enqueues work and never calls providers."""

from __future__ import annotations

import os
import socket
import threading
from datetime import UTC
from uuid import uuid4

import structlog

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.timeutils import utcnow

logger = structlog.get_logger(__name__)


class IntelScheduler:
    def __init__(self, config: IntelConfig, *, manager: IntelManager | None = None) -> None:
        self.config = config
        self.manager = manager or IntelManager(config)
        self.repo = self.manager.repo
        self.instance_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self._stop = threading.Event()

    def run_once(self) -> str | None:
        now = utcnow()
        with self.repo.connect() as conn:
            due_sources = self.repo.list_sources(conn, enabled_only=True, due_at=now)
            active = self.repo.has_active_request_origin(conn, "scheduler")
            self.repo.upsert_service_heartbeat(
                conn,
                service_name="scheduler",
                instance_id=self.instance_id,
                activity="queueing" if due_sources and not active else "idle",
                now=now,
                metadata={"due_sources": len(due_sources), "active_scheduled_run": active},
            )
            conn.commit()
        if not due_sources or active:
            return None
        bucket = now.astimezone(UTC).strftime("%Y%m%dT%H%M")
        summary = self.manager.queue_crawl(
            due=True,
            origin="scheduler",
            idempotency_key=f"scheduler:due:{bucket}",
        )
        self._heartbeat("idle", queued_run_id=summary.run_id, due_sources=len(due_sources))
        logger.info(
            "intel_scheduler_queued_run",
            stage="scheduler",
            run_id=summary.run_id,
            due_sources=len(due_sources),
        )
        return summary.run_id

    def run_forever(self) -> None:
        logger.info(
            "intel_scheduler_started",
            stage="scheduler",
            instance_id=self.instance_id,
            poll_seconds=self.config.service.scheduler_poll_seconds,
        )
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("intel_scheduler_loop_failed", stage="scheduler", error=str(exc))
                self._heartbeat("error", error=str(exc))
            self._stop.wait(self.config.service.scheduler_poll_seconds)
        self._heartbeat("stopped")

    def stop(self) -> None:
        self._stop.set()

    def _heartbeat(self, activity: str, **metadata) -> None:
        with self.repo.connect() as conn:
            self.repo.upsert_service_heartbeat(
                conn,
                service_name="scheduler",
                instance_id=self.instance_id,
                activity=activity,
                now=utcnow(),
                metadata=metadata,
            )
            conn.commit()
