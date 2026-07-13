from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ad_classifier.intelligence_crawler.config import (
    IntelConfig,
    ServiceConfig,
    SourceConfig,
    WatchlistConfig,
)
from ad_classifier.intelligence_crawler.exports import write_latest_snapshots
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.scheduler_service import IntelScheduler
from ad_classifier.intelligence_crawler.worker_service import IntelCrawlerWorker

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _config(tmp_path, *, enabled: bool = True) -> IntelConfig:
    return IntelConfig(
        db_path=tmp_path / "intel.db",
        cache_dir=tmp_path / "cache",
        service=ServiceConfig(write_snapshots_after_run=False),
        watchlist=WatchlistConfig(include_graph_brands=False, entity_graph_db_path=None),
        sources=[
            SourceConfig(
                id="s1",
                brand="Toyota",
                source_type="mock",
                enabled=enabled,
                config={"items": []},
            )
        ],
    )


def test_worker_claims_durable_queue_and_records_heartbeat(tmp_path):
    manager = IntelManager(_config(tmp_path, enabled=False))
    queued = manager.queue_crawl(source_id="s1")

    worker = IntelCrawlerWorker(manager.config, manager=manager)
    assert worker.run_once() is True
    assert manager.get_run(queued.run_id)["status"] == "completed"

    with manager.repo.connect(readonly=True) as conn:
        heartbeats = manager.repo.list_service_heartbeats(conn)
    assert heartbeats[0]["service_name"] == "worker"
    assert heartbeats[0]["activity"] == "idle"


def test_scheduler_enqueues_once_and_worker_executes_later(tmp_path):
    manager = IntelManager(_config(tmp_path))
    scheduler = IntelScheduler(manager.config, manager=manager)

    run_id = scheduler.run_once()
    assert run_id is not None
    assert scheduler.run_once() is None
    assert manager.get_run(run_id)["status"] == "queued"

    worker = IntelCrawlerWorker(manager.config, manager=manager)
    assert worker.run_once() is True
    assert manager.get_run(run_id)["status"] == "completed"


def test_expired_worker_run_is_failed_and_requeued_with_request(tmp_path):
    manager = IntelManager(_config(tmp_path, enabled=False))
    queued = manager.queue_crawl(source_id="s1")
    repo: IntelRepository = manager.repo
    with repo.connect() as conn:
        claimed = repo.claim_next_run(conn, owner="dead-worker", now=NOW, lease_seconds=30)
        conn.commit()
    assert claimed["run_id"] == queued.run_id

    ids = iter(["intel_run_recovered"])
    with repo.connect() as conn:
        recovered = repo.recover_abandoned_runs(
            conn,
            now=NOW + timedelta(seconds=31),
            max_attempts=5,
            new_run_id=lambda: next(ids),
        )
        conn.commit()
    assert recovered["recovered"] == ["intel_run_recovered"]
    assert manager.get_run(queued.run_id)["status"] == "failed"
    retry = manager.get_run("intel_run_recovered")
    assert retry["status"] == "queued"
    assert retry["request"]["source_id"] == "s1"
    assert retry["request"]["recovered_from"] == queued.run_id
    with repo.connect() as conn:
        repo.finish_run(
            conn,
            queued.run_id,
            status="completed",
            source_count=1,
            resource_count=0,
            signal_count=0,
            summary={"items": []},
        )
        conn.commit()
    assert manager.get_run(queued.run_id)["status"] == "failed"


def test_expired_run_waits_for_source_lease_before_recovery(tmp_path):
    manager = IntelManager(_config(tmp_path, enabled=False))
    queued = manager.queue_crawl(source_id="s1")
    repo = manager.repo
    with repo.connect() as conn:
        repo.claim_next_run(conn, owner="dead-worker", now=NOW, lease_seconds=30)
        assert repo.acquire_lease(
            conn,
            "s1",
            f"runner:{queued.run_id}:s1",
            now=NOW,
            ttl_seconds=600,
        )
        conn.commit()

    with repo.connect() as conn:
        blocked = repo.recover_abandoned_runs(
            conn,
            now=NOW + timedelta(seconds=31),
            max_attempts=5,
            new_run_id=lambda: "should_not_be_used",
        )
        conn.commit()
    assert blocked == {"recovered": [], "exhausted": []}
    assert manager.get_run(queued.run_id)["status"] == "running"


def test_services_can_generate_atomic_latest_json_snapshots(tmp_path):
    manager = IntelManager(_config(tmp_path, enabled=False))
    manager.run_crawl(source_id="s1")

    paths = write_latest_snapshots(manager, tmp_path / "snapshots")

    assert {path.name for path in paths} == {
        "latest_resources.json",
        "source_statuses.json",
        "health.json",
    }
    assert all(path.is_file() for path in paths)
    assert not list((tmp_path / "snapshots").glob("*.tmp"))
