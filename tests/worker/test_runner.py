from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from ad_classifier.config import load_config
from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories import AdRepository, JobRepository
from ad_classifier.models.ads import AdRecord
from ad_classifier.models.jobs import JobRecord
from ad_classifier.worker.runner import PipelineWorker


def test_worker_run_once_completes_queued_job(tmp_path: Path):
    db_path = tmp_path / "worker.db"
    conn = open_database(db_path)
    apply_migrations(conn)
    AdRepository(conn).create(
        AdRecord(
            id="ad_worker",
            source_path="/tmp/ad.mp4",
            ingested_at=datetime.now(UTC),
            status="new",
        )
    )
    JobRepository(conn).create(JobRecord(id="job_worker", ad_id="ad_worker", state="queued"))
    conn.commit()
    conn.close()

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {"paths": {"sqlite_path": str(db_path)}, "worker": {"poll_interval_ms": 50}}
        ),
        encoding="utf-8",
    )
    config, config_file = load_config(config_path)

    def fake_runner(conn, ad_id, progress):
        assert ad_id == "ad_worker"
        progress("fake", 0.5, "halfway")

    worker = PipelineWorker(
        config=config, config_file=config_file, db_path=db_path, runner=fake_runner
    )
    assert worker.run_once() is True

    conn = open_database(db_path)
    try:
        job = JobRepository(conn).get("job_worker")
        ad = AdRepository(conn).get("ad_worker")
    finally:
        conn.close()

    assert job.state == "completed"
    assert job.progress == 1.0
    assert ad.status == "completed"


def test_worker_run_once_returns_false_when_empty(tmp_path: Path):
    db_path = tmp_path / "worker.db"
    conn = open_database(db_path)
    apply_migrations(conn)
    conn.close()

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"paths": {"sqlite_path": str(db_path)}}), encoding="utf-8"
    )
    config, config_file = load_config(config_path)
    worker = PipelineWorker(config=config, config_file=config_file, db_path=db_path, runner=None)

    assert worker.run_once() is False


def test_worker_reload_config_refreshes_vlm_model(tmp_path: Path):
    db_path = tmp_path / "worker.db"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {"sqlite_path": str(db_path)},
                "vlm": {"endpoint": {"model": "argus/vlm"}},
            }
        ),
        encoding="utf-8",
    )
    config, config_file = load_config(config_path)
    worker = PipelineWorker(config=config, config_file=config_file, db_path=db_path, runner=None)

    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {"sqlite_path": str(db_path)},
                "vlm": {"endpoint": {"model": "qwen-test-model"}},
            }
        ),
        encoding="utf-8",
    )

    worker.reload_config()

    assert worker.config.vlm.endpoint.model == "qwen-test-model"
    assert worker.db_path == db_path


def test_worker_does_not_overwrite_duplicate_ad_status(tmp_path: Path):
    db_path = tmp_path / "worker.db"
    conn = open_database(db_path)
    apply_migrations(conn)
    AdRepository(conn).create(
        AdRecord(
            id="ad_duplicate",
            source_path="/tmp/ad.mp4",
            ingested_at=datetime.now(UTC),
            status="new",
        )
    )
    JobRepository(conn).create(JobRecord(id="job_duplicate", ad_id="ad_duplicate", state="queued"))
    conn.commit()
    conn.close()

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"paths": {"sqlite_path": str(db_path)}}), encoding="utf-8"
    )
    config, config_file = load_config(config_path)

    def fake_runner(conn, ad_id, progress):
        AdRepository(conn).update_status(ad_id, "duplicate")
        conn.commit()

    worker = PipelineWorker(
        config=config, config_file=config_file, db_path=db_path, runner=fake_runner
    )
    assert worker.run_once() is True

    conn = open_database(db_path)
    try:
        ad = AdRepository(conn).get("ad_duplicate")
    finally:
        conn.close()

    assert ad.status == "duplicate"
