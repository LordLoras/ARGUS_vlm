from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig, WatchlistConfig
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


def test_source_failure_marks_run_degraded(tmp_path):
    db = tmp_path / "intel.db"
    # The youtube adapter is a Phase-3 stub whose poll() raises.
    cfg = _config(db, [], source_type="youtube_channel")
    summary = IntelRunner(cfg, now_fn=lambda: T1).run(due=True)
    assert summary.status == "degraded"
    assert summary.items[0].status == "failed"
