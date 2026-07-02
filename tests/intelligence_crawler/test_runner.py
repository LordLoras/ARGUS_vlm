from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig, WatchlistConfig
from ad_classifier.intelligence_crawler.models import SourcePollResult
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
        due=True
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
    first = IntelRunner(cfg, now_fn=lambda: T1).run(due=True)
    second = IntelRunner(cfg, now_fn=lambda: T1).run(due=True)
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
    summary = IntelRunner(_config(db, [enriched]), now_fn=lambda: T1).run(due=True)

    item = summary.items[0]
    assert item.new_resources == 0
    assert item.refreshed == 1
    assert summary.signal_count == 0  # a refresh never emits a signal

    repo = IntelRepository(db)
    with repo.connect(readonly=True) as conn:
        views = repo.list_resources(conn, source_id="s1")
    assert len(views) == 1
    got = views[0]
    assert got.title == "Camry Reborn official commercial (extended cut)"
    assert got.metadata["image_sources"] == ["https://tpc.googlesyndication.com/archive/simgad/1"]
    # First-seen properties survive the refresh.
    assert got.is_backfill is True
    assert got.first_seen_at == T0


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
    summary = IntelRunner(_config(db, [OLD_ITEM, walkaround]), now_fn=lambda: T1).run(due=True)
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


def test_source_failure_marks_run_degraded(tmp_path):
    db = tmp_path / "intel.db"
    cfg = _config(db, [])
    # Force the adapter to raise (a whole-source failure) via the factory seam.
    summary = IntelRunner(
        cfg, now_fn=lambda: T1, adapter_factory=lambda _stype: _BoomAdapter()
    ).run(due=True)
    assert summary.status == "degraded"
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
    assert summary.items[0].reason == "source deleted during poll"
