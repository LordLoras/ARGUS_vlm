from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ad_classifier.config import AppConfig, load_config, resolve_config_path
from ad_classifier.db.connection import initialize_database, open_database
from ad_classifier.db.repositories import AdRepository, JobRepository
from ad_classifier.worker.stages import PipelineComponents, run_pipeline_for_job

JobRunner = Callable[[sqlite3.Connection, str, Callable[[str, float, str], None]], None]
logger = logging.getLogger(__name__)


class PipelineWorker:
    def __init__(
        self,
        *,
        config: AppConfig,
        config_file: Path,
        db_path: Path | None = None,
        runner: JobRunner | None = None,
    ) -> None:
        self.config = config
        self.config_file = config_file
        self.db_path = db_path or resolve_config_path(config.paths.sqlite_path, config_file)
        self._runner = runner

    def run_once(self) -> bool:
        initialize_database(self.db_path)
        conn = open_database(self.db_path)
        try:
            jobs = JobRepository(conn)
            job = jobs.next_queued()
            if job is None:
                return False

            jobs.update_state(
                job.id,
                state="running",
                progress=0.0,
                message="job started",
                started_at=datetime.now(UTC),
            )
            if job.ad_id is not None:
                AdRepository(conn).update_status(job.ad_id, "processing")
            conn.commit()

            if job.ad_id is None:
                raise ValueError("job has no ad_id")

            def progress(stage: str, value: float, message: str) -> None:
                jobs.update_state(job.id, state="running", progress=value, message=message)
                conn.commit()

            if self._runner is not None:
                self._runner(conn, job.ad_id, progress)
            else:
                run_pipeline_for_job(
                    conn=conn,
                    config=self.config,
                    config_file=self.config_file,
                    ad_id=job.ad_id,
                    components=PipelineComponents(),
                    progress=progress,
                )

            current = jobs.get(job.id)
            if current is not None and current.state == "cancelled":
                conn.commit()
                return True

            jobs.update_state(
                job.id,
                state="completed",
                progress=1.0,
                message="completed",
                finished_at=datetime.now(UTC),
            )
            ad = AdRepository(conn).get(job.ad_id)
            if ad is not None and ad.status not in {"duplicate", "failed"}:
                AdRepository(conn).update_status(job.ad_id, "completed")
            conn.commit()
            return True
        except Exception as exc:
            if "job" in locals():
                jobs.update_state(
                    job.id,
                    state="failed",
                    progress=1.0,
                    message="failed",
                    error=str(exc),
                    finished_at=datetime.now(UTC),
                )
                if job.ad_id is not None:
                    AdRepository(conn).update_status(job.ad_id, "failed")
                conn.commit()
            logger.exception(
                "worker job failed", extra={"job_id": job.id if "job" in locals() else None}
            )
            return True
        finally:
            conn.close()

    def run_forever(self) -> None:
        while True:
            did_work = self.run_once()
            if not did_work:
                time.sleep(self.config.worker.poll_interval_ms / 1000)


def build_worker(config_path: Path | None = None, db_path: Path | None = None) -> PipelineWorker:
    config, config_file = load_config(config_path)
    return PipelineWorker(config=config, config_file=config_file, db_path=db_path)
