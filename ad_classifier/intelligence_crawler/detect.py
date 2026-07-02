"""Change detection: cold-start baseline + new-vs-seen classification.

This is the reliability core. Two timestamps are kept distinct:
- ``published_at``  — when the source says the item went live (real recency).
- ``first_seen_at`` — when we observed it (an artifact of when we added the source).

On a source's *first* poll (no ``source_activated_at``) we run in **baseline mode**:
every new item is recorded as backfill and **no live signals are emitted**, so adding a
source never floods the feed with its back catalogue. Afterwards an item is "live" only
if it was published after activation and within the recency lookback window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from ad_classifier.intelligence_crawler.ids import resource_id
from ad_classifier.intelligence_crawler.models import IntelSource, RawSourceItem
from ad_classifier.intelligence_crawler.timeutils import as_utc

ItemKind = Literal["live", "backfill", "refresh"]


@dataclass(frozen=True)
class ItemDecision:
    item: RawSourceItem
    resource_id: str
    kind: ItemKind  # "live" => eligible to emit a signal; "backfill" => record only


@dataclass(frozen=True)
class DetectionResult:
    baseline_mode: bool
    activated_at: datetime  # the activation time to persist on the source
    decisions: list[ItemDecision]  # NEW items only (already-seen are skipped)
    skipped_seen: int
    # Already-seen items re-observed this poll. Never signal-eligible; the runner upserts
    # them so a repoll refreshes metadata/artifacts (first_seen_at/is_backfill preserved).
    refreshes: list[ItemDecision] = field(default_factory=list)


def classify(
    *,
    source: IntelSource,
    items: list[RawSourceItem],
    seen_ids: set[str],
    now: datetime,
    lookback_days: int,
    activated_at: datetime | None,
) -> DetectionResult:
    now_utc = as_utc(now)
    assert now_utc is not None
    baseline = activated_at is None
    activation = now_utc if activated_at is None else as_utc(activated_at)
    assert activation is not None

    decisions: list[ItemDecision] = []
    refreshes: list[ItemDecision] = []
    skipped = 0
    for item in items:
        rid = resource_id(source.id, item.external_id)
        if rid in seen_ids:
            skipped += 1
            refreshes.append(ItemDecision(item=item, resource_id=rid, kind="refresh"))
            continue
        if baseline:
            kind: ItemKind = "backfill"
        else:
            kind = "live" if _is_live(item, now_utc, activation, lookback_days) else "backfill"
        decisions.append(ItemDecision(item=item, resource_id=rid, kind=kind))

    return DetectionResult(
        baseline_mode=baseline,
        activated_at=activation,
        decisions=decisions,
        skipped_seen=skipped,
        refreshes=refreshes,
    )


def _is_live(
    item: RawSourceItem, now: datetime, activated_at: datetime, lookback_days: int
) -> bool:
    published = as_utc(item.published_at)
    if published is None:
        return False
    if published <= activated_at:
        return False
    return (now - published) <= timedelta(days=lookback_days)
