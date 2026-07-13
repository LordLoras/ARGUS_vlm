from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig, WatchlistConfig
from ad_classifier.intelligence_crawler.models import (
    PollDiagnostic,
    RawSourceItem,
    SourcePollResult,
)
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.runner import IntelRunner

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)

OLD_ITEM = {
    "external_id": "old1",
    "url": "https://yt/old1",
    "resource_type": "video",
    "title": "Camry Reborn official commercial",
    "published_at": "2026-05-30T00:00:00+00:00",
}
NEW_PRESS = {
    "external_id": "new_press",
    "url": "https://news/launch",
    "resource_type": "press",
    "title": "Camry Reborn official campaign launch",
    "published_at": T1.isoformat(),
}
NEW_VIDEO = {
    "external_id": "new_video",
    "url": "https://yt/new",
    "resource_type": "video",
    "title": "Camry Reborn official commercial",
    "published_at": T1.isoformat(),
}


def _config(db_path, items, *, source_type="mock", tier="A", enabled=True):
    return IntelConfig(
        db_path=db_path,
        watchlist=WatchlistConfig(
            include_graph_brands=False, entity_graph_db_path=None, seed_brands=["Toyota"]
        ),
        sources=[
            SourceConfig(
                id="s1",
                brand="Toyota",
                source_type=source_type,
                tier=tier,
                enabled=enabled,
                config={"items": items},
            )
        ],
    )


def test_coldstart_then_live_with_campaign_grouping(tmp_path):
    db = tmp_path / "intel.db"

    # Run 1: first poll -> baseline, no live signals even though items exist.
    summary1 = IntelRunner(_config(db, [OLD_ITEM]), now_fn=lambda: T0).run(due=True)
    assert summary1.signal_count == 0
    assert summary1.items[0].baseline is True
    assert summary1.items[0].backfilled == 1

    # Run 2: activation persisted; two new items in the same campaign go live.
    summary2 = IntelRunner(_config(db, [OLD_ITEM, NEW_PRESS, NEW_VIDEO]), now_fn=lambda: T1).run(
        due=False
    )
    assert summary2.items[0].baseline is False
    assert summary2.signal_count == 2  # old1 already seen; the two new ones emit

    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        signals = repo.list_signals(conn, brand="Toyota")
    assert len(signals) == 2
    # Variant rollup: both creatives share one campaign group.
    group_ids = {s.campaign_group_id for s in signals}
    assert len(group_ids) == 1 and None not in group_ids
    # The second creative in the group gets a corroboration bump.
    assert any(s.score_breakdown.get("corroborating_count", 0) >= 1 for s in signals)


def test_repoll_is_idempotent(tmp_path):
    db = tmp_path / "intel.db"
    IntelRunner(_config(db, [OLD_ITEM]), now_fn=lambda: T0).run(due=True)  # baseline
    cfg = _config(db, [OLD_ITEM, NEW_VIDEO])
    first = IntelRunner(cfg, now_fn=lambda: T1).run(due=False)
    second = IntelRunner(cfg, now_fn=lambda: T1).run(due=False)
    assert first.signal_count == 1
    assert second.signal_count == 0  # nothing new on re-poll


def test_repoll_refreshes_stored_metadata(tmp_path):
    db = tmp_path / "intel.db"
    IntelRunner(_config(db, [OLD_ITEM]), now_fn=lambda: T0).run(due=True)  # baseline records old1

    # Same external id re-observed with richer data (e.g. preview enrichment now succeeded).
    enriched = {
        **OLD_ITEM,
        "title": "Camry Reborn official commercial (extended cut)",
        "raw": {"image_sources": ["https://tpc.googlesyndication.com/archive/simgad/1"]},
    }
    summary = IntelRunner(_config(db, [enriched]), now_fn=lambda: T1).run(due=False)

    item = summary.items[0]
    assert item.new_resources == 0
    assert item.refreshed == 1
    assert summary.signal_count == 0  # a refresh never emits a signal

    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        views = repo.list_resources(conn, source_id="s1")
        observation_count = conn.execute(
            "SELECT COUNT(*) FROM intel_resource_observations WHERE resource_id = ?",
            (views[0].id,),
        ).fetchone()[0]
        media_count = conn.execute(
            "SELECT COUNT(*) FROM intel_media_assets WHERE resource_id = ?", (views[0].id,)
        ).fetchone()[0]
    assert len(views) == 1
    got = views[0]
    assert got.title == "Camry Reborn official commercial (extended cut)"
    assert got.metadata["image_sources"] == ["https://tpc.googlesyndication.com/archive/simgad/1"]
    # First-seen properties survive the refresh.
    assert got.is_backfill is True
    assert got.first_seen_at == T0
    assert got.last_seen_at == T1
    assert observation_count == 2
    assert media_count == 1

    with repo.connect(readonly=True) as conn:
        changes = repo.list_resource_changes(conn, limit=10)
    assert [change["change_type"] for change in changes] == ["created", "updated"]


def test_identical_repoll_does_not_emit_consumer_change(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [OLD_ITEM])
    IntelRunner(cfg, now_fn=lambda: T0).run(due=True)
    IntelRunner(cfg, now_fn=lambda: T1).run(due=False)

    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        changes = repo.list_resource_changes(conn, limit=10)
    assert [change["change_type"] for change in changes] == ["created"]


def test_verified_unchanged_resource_advances_freshness_without_ledger_noise(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [OLD_ITEM])
    IntelRunner(cfg, now_fn=lambda: T0).run(due=True)

    class UnchangedAdapter:
        tier = "A"

        def poll(self, source, state, *, now):
            return SourcePollResult(
                source_id=source.id,
                outcome="not_modified",
                verified_external_ids=["old1"],
            )

    summary = IntelRunner(
        cfg,
        now_fn=lambda: T1,
        adapter_factory=lambda _source_type: UnchangedAdapter(),
    ).run(due=False)

    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        resource = repo.list_resources(conn, source_id="s1")[0]
        observations = conn.execute(
            "SELECT COUNT(*) FROM intel_resource_observations WHERE resource_id = ?",
            (resource.id,),
        ).fetchone()[0]
    assert summary.items[0].outcome == "not_modified"
    assert resource.last_seen_at == T1
    assert resource.fetched_at == T1
    assert observations == 1


def test_due_run_obeys_next_due_schedule(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [OLD_ITEM])

    assert IntelRunner(cfg, now_fn=lambda: T0).run(due=True).source_count == 1
    assert IntelRunner(cfg, now_fn=lambda: T1).run(due=True).source_count == 0
    after_interval = T0 + timedelta(hours=13)
    assert IntelRunner(cfg, now_fn=lambda: after_interval).run(due=True).source_count == 1


def test_explicit_source_run_respects_freshness_unless_forced(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [OLD_ITEM])
    IntelRunner(cfg, now_fn=lambda: T0).run(due=True)

    guarded = IntelRunner(cfg, now_fn=lambda: T1).run(source_id="s1")
    forced = IntelRunner(cfg, now_fn=lambda: T1).run(source_id="s1", force=True)

    assert guarded.items[0].status == "skipped"
    assert guarded.items[0].error_code == "source_not_due"
    assert "Current copy is fresh" in guarded.items[0].reason
    assert forced.items[0].status == "polled"


def test_rate_limit_opens_provider_circuit_for_remaining_sources(tmp_path):
    db = tmp_path / "intel.db"
    cfg = IntelConfig(
        db_path=db,
        watchlist=WatchlistConfig(
            include_graph_brands=False, entity_graph_db_path=None, seed_brands=["A", "B"]
        ),
        sources=[
            SourceConfig(
                id="g1",
                brand="A",
                source_type="google_atc",
                enabled=True,
                platform_id="AR_A",
            ),
            SourceConfig(
                id="g2",
                brand="B",
                source_type="google_atc",
                enabled=True,
                platform_id="AR_B",
            ),
        ],
    )
    calls = []

    class RateLimitedAdapter:
        tier = "B"

        def poll(self, source, state, *, now):
            calls.append(source.id)
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    PollDiagnostic(
                        code="provider_rate_limited",
                        category="rate_limited",
                        message="Google returned HTTP 429.",
                        retryable=True,
                    )
                ],
            )

    summary = IntelRunner(
        cfg,
        now_fn=lambda: T0,
        adapter_factory=lambda _source_type: RateLimitedAdapter(),
    ).run(due=False)

    assert calls == ["g1"]
    assert [item.status for item in summary.items] == ["failed", "skipped"]
    assert summary.items[1].error_code == "provider_circuit_open"
    assert summary.items[1].next_due_at == T0 + timedelta(hours=1)
    assert summary.status == "degraded"


def test_force_bypasses_open_provider_circuit(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [], source_type="google_atc")
    cfg = cfg.model_copy(
        update={"sources": [cfg.sources[0].model_copy(update={"platform_id": "AR_A", "tier": "B"})]}
    )
    repo = IntelRepository(db)
    with repo.connect() as conn:
        repo.sync_sources(conn, [cfg.sources[0].to_source()])
        repo.update_source_state(
            conn,
            "s1",
            last_error="Google returned HTTP 429.",
            last_error_category="rate_limited",
            last_error_code="provider_rate_limited",
            cooldown_until=T0 + timedelta(hours=2),
            next_due_at=T0 + timedelta(hours=2),
        )
        conn.commit()

    class CompleteAdapter:
        tier = "B"

        def poll(self, source, state, *, now):
            return SourcePollResult(source_id=source.id, outcome="explicit_empty")

    guarded = IntelRunner(
        cfg,
        repo=repo,
        now_fn=lambda: T1,
        adapter_factory=lambda _source_type: CompleteAdapter(),
    ).run(source_id="s1")
    forced = IntelRunner(
        cfg,
        repo=repo,
        now_fn=lambda: T1,
        adapter_factory=lambda _source_type: CompleteAdapter(),
    ).run(source_id="s1", force=True)

    assert guarded.items[0].error_code == "provider_circuit_open"
    assert forced.items[0].status == "polled"


def test_page_checkpoint_is_durable_even_when_adapter_crashes(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [], source_type="google_atc")
    cfg = cfg.model_copy(
        update={"sources": [cfg.sources[0].model_copy(update={"platform_id": "AR_A", "tier": "B"})]}
    )

    class CrashingCheckpointAdapter:
        tier = "B"

        def set_checkpoint_sink(self, sink):
            self.sink = sink

        def poll(self, source, state, *, now):
            self.sink(
                {
                    "google_atc": {
                        "checkpoint": {
                            "token": "NEXT_PAGE",
                            "fingerprint": "fingerprint",
                            "mode": "full",
                            "page_count": 12,
                            "updated_at": now.isoformat(),
                        }
                    }
                }
            )
            raise RuntimeError("worker terminated after page")

    summary = IntelRunner(
        cfg,
        now_fn=lambda: T0,
        adapter_factory=lambda _source_type: CrashingCheckpointAdapter(),
    ).run(due=True)

    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        state = repo.get_source_state(conn, "s1")
        status = repo.list_source_statuses(conn)[0]
    checkpoint = state.provider_state["google_atc"]["checkpoint"]
    assert summary.items[0].status == "failed"
    assert checkpoint["token"] == "NEXT_PAGE"
    assert checkpoint["page_count"] == 12
    assert status.resume_available is True
    assert status.resume_page == 12
    assert "provider_state" not in status.model_dump(mode="json")["state"]


def test_partial_baseline_persists_observation_but_does_not_activate(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [])

    class PartialAdapter:
        tier = "A"

        def poll(self, source, state, *, now):
            return SourcePollResult(
                source_id=source.id,
                items=[RawSourceItem.model_validate(NEW_VIDEO)],
                outcome="partial",
                complete=False,
                truncated=True,
                truncation_reason="Configured page limit reached.",
                diagnostics=[
                    PollDiagnostic(
                        code="page_limit_reached",
                        category="request_limit",
                        message="Configured page limit reached.",
                        retryable=True,
                    )
                ],
            )

    summary = IntelRunner(
        cfg, now_fn=lambda: T0, adapter_factory=lambda _source_type: PartialAdapter()
    ).run(due=True)

    assert summary.status == "degraded"
    assert summary.items[0].status == "partial"
    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        state = repo.get_source_state(conn, "s1")
        source = repo.get_source(conn, "s1")
        observations = conn.execute("SELECT COUNT(*) FROM intel_resource_observations").fetchone()[
            0
        ]
    assert state.last_success_at is None
    assert state.last_outcome == "partial"
    assert state.last_error_category == "request_limit"
    assert source is not None and source.source_activated_at is None
    assert observations == 1


def test_failure_preserves_previous_complete_success(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [OLD_ITEM])
    IntelRunner(cfg, now_fn=lambda: T0).run(due=True)

    IntelRunner(cfg, now_fn=lambda: T1, adapter_factory=lambda _source_type: _BoomAdapter()).run(
        due=False
    )

    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        state = repo.get_source_state(conn, "s1")
        runs = repo.list_source_runs(conn, "s1")
    assert state.last_success_at == T0
    assert state.last_attempt_at == T1
    assert state.last_outcome == "failed"
    assert runs[0]["status"] == "failed"
    assert runs[0]["error_code"] == "provider_poll_failed"


def test_runner_seed_does_not_disable_curated_db_source(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [], enabled=False)
    repo = IntelRepository(db)
    runner = IntelRunner(cfg, repo=repo, now_fn=lambda: T0)

    # First run seeds the disabled YAML source into the DB.
    assert runner.run(due=True).source_count == 0
    with repo.connect() as conn:
        repo.set_source_enabled(conn, "s1", True)
        conn.commit()

    # Second run sees the DB toggle and does not overwrite it with enabled=False from YAML.
    summary = runner.run(due=True)

    assert summary.source_count == 1
    with repo.connect(readonly=True) as conn:
        source = repo.get_source(conn, "s1")
    assert source is not None
    assert source.enabled is True


def test_non_ad_video_is_filtered_not_signaled(tmp_path):
    db = tmp_path / "intel.db"
    IntelRunner(_config(db, [OLD_ITEM]), now_fn=lambda: T0).run(due=True)  # baseline activates
    walkaround = {
        "external_id": "walk1",
        "url": "https://yt/walk1",
        "resource_type": "video",
        "title": "2026 RAV4 full walkaround",  # no ad cue, no duration -> below the gate
        "published_at": T1.isoformat(),
    }
    summary = IntelRunner(_config(db, [OLD_ITEM, walkaround]), now_fn=lambda: T1).run(due=False)
    assert summary.signal_count == 0
    item = summary.items[0]
    assert item.filtered == 1
    assert item.new_resources == 1  # recorded as a resource, just not emitted as a signal


class _BoomAdapter:
    tier = "A"

    def __init__(self, *, http=None, intel_config=None):
        pass

    def poll(self, source, state, *, now):
        raise RuntimeError("boom")


def test_only_source_failure_marks_run_failed(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [])
    # Force the adapter to raise (a whole-source failure) via the factory seam.
    summary = IntelRunner(
        cfg, now_fn=lambda: T1, adapter_factory=lambda _stype: _BoomAdapter()
    ).run(due=True)
    assert summary.status == "failed"
    assert summary.items[0].status == "failed"


def test_slow_poll_does_not_hold_write_lock(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [])
    repo = IntelRepository(db)
    entered_poll = threading.Event()
    release_poll = threading.Event()
    result = {}

    class BlockingAdapter:
        tier = "A"

        def poll(self, source, state, *, now):
            entered_poll.set()
            assert release_poll.wait(timeout=5)
            return SourcePollResult(source_id=source.id)

    runner = IntelRunner(
        cfg,
        repo=repo,
        now_fn=lambda: T1,
        adapter_factory=lambda _stype: BlockingAdapter(),
    )

    def run() -> None:
        result["summary"] = runner.run(source_id="s1")

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered_poll.wait(timeout=5)
        with repo.connect() as conn:
            deleted = repo.delete_source(conn, "s1")
            conn.commit()
        assert deleted is True
    finally:
        release_poll.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    summary = result["summary"]
    assert summary.items[0].status == "skipped"
    assert summary.items[0].reason == (
        "Source was archived during polling; provider result was discarded."
    )
