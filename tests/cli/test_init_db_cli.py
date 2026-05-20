from __future__ import annotations

from typer.testing import CliRunner

from ad_classifier.cli import app
from ad_classifier.db.connection import initialize_database, open_database
from ad_classifier.db.repositories import AdRepository, JobRepository
from ad_classifier.models.ads import AdRecord
from ad_classifier.models.jobs import JobRecord

runner = CliRunner()


def test_help_lists_init_db():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "api" in result.output
    assert "dedup-check" in result.output
    assert "campaigns" in result.output
    assert "init-db" in result.output
    assert "ingest" in result.output
    assert "version" in result.output
    assert "worker" in result.output
    assert "recover-jobs" in result.output


def test_init_db_cli_creates_database(tmp_path):
    db_path = tmp_path / "cli.db"

    result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])

    assert result.exit_code == 0, result.output
    assert db_path.exists()
    assert "journal_mode=wal" in result.output
    assert "sqlite_vec=" in result.output


def test_recover_jobs_requeues_running_jobs(tmp_path):
    db_path = tmp_path / "cli.db"
    initialize_database(db_path, require_sqlite_vec=False)
    conn = open_database(db_path)
    try:
        AdRepository(conn).create(
            AdRecord(id="ad_running", source_path="/tmp/ad.mp4", status="processing")
        )
        JobRepository(conn).create(
            JobRecord(
                id="job_running",
                ad_id="ad_running",
                state="running",
                progress=0.5,
                message="vlm",
            )
        )
        conn.commit()
    finally:
        conn.close()

    result = runner.invoke(app, ["recover-jobs", "--db-path", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "jobs_requeued=1" in result.output

    conn = open_database(db_path)
    try:
        job = JobRepository(conn).get("job_running")
        ad = AdRepository(conn).get("ad_running")
    finally:
        conn.close()

    assert job is not None
    assert job.state == "queued"
    assert job.progress == 0.0
    assert job.started_at is None
    assert ad is not None
    assert ad.status == "new"
