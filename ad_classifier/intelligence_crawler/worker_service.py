"""Durable crawler worker process; independent from FastAPI and ARGUS UI."""

from __future__ import annotations

import os
import socket
import threading
import time
from uuid import uuid4

import structlog

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.exports import write_latest_snapshots
from ad_classifier.intelligence_crawler.ids import new_run_id
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.timeutils import utcnow

logger = structlog.get_logger(__name__)


class IntelCrawlerWorker:
    def __init__(self, config: IntelConfig, *, manager: IntelManager | None = None) -> None:
        self.config = config
        self.manager = manager or IntelManager(config)
        self.repo = self.manager.repo
        self.instance_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self._stop = threading.Event()

    def run_once(self) -> bool:
        self._heartbeat("recovering")
        with self.repo.connect() as conn:
            recovery = self.repo.recover_abandoned_runs(
                conn,
                now=utcnow(),
                max_attempts=self.config.service.max_run_attempts,
                new_run_id=new_run_id,
            )
            conn.commit()
        if recovery["recovered"] or recovery["exhausted"]:
            logger.warning(
                "intel_worker_recovered_runs",
                stage="worker",
                recovered=recovery["recovered"],
                exhausted=recovery["exhausted"],
            )

        with self.repo.connect() as conn:
            claimed = self.repo.claim_next_run(
                conn,
                owner=self.instance_id,
                now=utcnow(),
                lease_seconds=self.config.service.run_lease_seconds,
            )
            conn.commit()
        if claimed is None:
            self._heartbeat("idle")
            return False

        run_id = claimed["run_id"]
        request = claimed.get("request") or {}
        self._heartbeat("running", run_id=run_id)
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._maintain_run_lease,
            args=(run_id, heartbeat_stop),
            name=f"intel-heartbeat-{run_id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            self.manager.run_queued_crawl(
                run_id,
                due=bool(request.get("due")),
                source_id=request.get("source_id"),
                brand=request.get("brand"),
                force=bool(request.get("force")),
            )
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=self.config.service.heartbeat_seconds + 1)

        completed = self.manager.get_run(run_id) or {}
        self._heartbeat(
            "idle",
            last_run_id=run_id,
            last_run_status=completed.get("status", "unknown"),
        )
        if self.config.service.write_snapshots_after_run:
            try:
                write_latest_snapshots(self.manager, self.config.service.snapshot_dir)
            except Exception as exc:  # snapshots are recoverable; crawl ledger stays authoritative
                logger.exception(
                    "intel_snapshot_write_failed",
                    stage="export",
                    run_id=run_id,
                    error=str(exc),
                )
                self._heartbeat("snapshot_error", last_run_id=run_id, error=str(exc))
        return True

    def run_forever(self) -> None:
        logger.info(
            "intel_worker_started",
            stage="worker",
            instance_id=self.instance_id,
            poll_seconds=self.config.service.worker_poll_seconds,
        )
        while not self._stop.is_set():
            try:
                did_work = self.run_once()
            except Exception as exc:
                logger.exception("intel_worker_loop_failed", stage="worker", error=str(exc))
                self._heartbeat("error", error=str(exc))
                did_work = False
            if not did_work:
                self._stop.wait(self.config.service.worker_poll_seconds)
        self._heartbeat("stopped")

    def stop(self) -> None:
        self._stop.set()

    def _maintain_run_lease(self, run_id: str, stop: threading.Event) -> None:
        while not stop.wait(self.config.service.heartbeat_seconds):
            try:
                now = utcnow()
                with self.repo.connect() as conn:
                    renewed = self.repo.renew_run_lease(
                        conn,
                        run_id,
                        owner=self.instance_id,
                        now=now,
                        lease_seconds=self.config.service.run_lease_seconds,
                    )
                    self.repo.upsert_service_heartbeat(
                        conn,
                        service_name="worker",
                        instance_id=self.instance_id,
                        activity="running",
                        now=now,
                        metadata={"run_id": run_id},
                    )
                    conn.commit()
                if not renewed:
                    logger.error("intel_worker_lease_lost", stage="worker", run_id=run_id)
                    return
            except Exception as exc:
                logger.exception(
                    "intel_worker_heartbeat_failed",
                    stage="worker",
                    run_id=run_id,
                    error=str(exc),
                )

    def _heartbeat(self, activity: str, **metadata) -> None:
        with self.repo.connect() as conn:
            self.repo.upsert_service_heartbeat(
                conn,
                service_name="worker",
                instance_id=self.instance_id,
                activity=activity,
                now=utcnow(),
                metadata=metadata,
            )
            conn.commit()


def wait_for_interrupt(service: IntelCrawlerWorker) -> None:
    try:
        service.run_forever()
    except KeyboardInterrupt:
        service.stop()
        time.sleep(0)
