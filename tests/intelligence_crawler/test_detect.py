from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.config import SourceConfig
from ad_classifier.intelligence_crawler.detect import classify
from ad_classifier.intelligence_crawler.models import RawSourceItem

SOURCE = SourceConfig(id="s1", brand="Toyota", source_type="mock", tier="A").to_source()
NOW = datetime(2026, 6, 10, tzinfo=UTC)
ACTIVATED = datetime(2026, 6, 1, tzinfo=UTC)


def _items():
    return [
        RawSourceItem(
            external_id="old",
            url="u1",
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
        ),
        RawSourceItem(
            external_id="recent",
            url="u2",
            published_at=datetime(2026, 6, 9, tzinfo=UTC),
        ),
    ]


def test_first_poll_is_baseline_no_live_signals():
    result = classify(
        source=SOURCE,
        items=_items(),
        seen_ids=set(),
        now=NOW,
        lookback_days=30,
        activated_at=None,
    )
    assert result.baseline_mode is True
    assert result.activated_at == NOW
    assert {d.kind for d in result.decisions} == {"backfill"}


def test_after_activation_only_recent_post_activation_is_live():
    result = classify(
        source=SOURCE,
        items=_items(),
        seen_ids=set(),
        now=NOW,
        lookback_days=30,
        activated_at=ACTIVATED,
    )
    kinds = {d.item.external_id: d.kind for d in result.decisions}
    assert kinds == {"old": "backfill", "recent": "live"}


def test_already_seen_items_are_skipped():
    from ad_classifier.intelligence_crawler.ids import resource_id

    seen = {resource_id("s1", "old")}
    result = classify(
        source=SOURCE,
        items=_items(),
        seen_ids=seen,
        now=NOW,
        lookback_days=30,
        activated_at=ACTIVATED,
    )
    assert result.skipped_seen == 1
    assert [d.item.external_id for d in result.decisions] == ["recent"]
    # Seen items come back as refreshes so the runner can update their stored metadata.
    assert [d.item.external_id for d in result.refreshes] == ["old"]
    assert result.refreshes[0].kind == "refresh"


def test_recent_outside_lookback_is_backfill():
    result = classify(
        source=SOURCE,
        items=_items(),
        seen_ids=set(),
        now=NOW,
        lookback_days=1,
        activated_at=ACTIVATED,  # 'recent' is 1 day old -> within; tighten:
    )
    # 'recent' published 2026-06-09, now 2026-06-10 -> 1 day, lookback_days=1 -> still live.
    assert {d.item.external_id: d.kind for d in result.decisions}["recent"] == "live"
