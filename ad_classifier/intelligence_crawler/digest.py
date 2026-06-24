"""Build a 'what's new' digest — the push/notification surface.

Groups recent signals by campaign so one launch reads as one line, not ten. Excludes
dismissed/stale signals.
"""

from __future__ import annotations

from datetime import datetime

from ad_classifier.intelligence_crawler.models import DigestEntry, IntelSignal
from ad_classifier.intelligence_crawler.repository import IntelRepository

_EXCLUDED = {"dismissed", "stale"}


def build_digest(
    repo: IntelRepository, *, since: datetime | None, limit: int = 200
) -> list[DigestEntry]:
    with repo.connect(readonly=True) as conn:
        signals = repo.list_signals(conn, since=since, limit=limit)
        url_map = repo.evidence_urls_for(conn, [s.id for s in signals])

    grouped: dict[tuple[str, str], list[IntelSignal]] = {}
    for signal in signals:
        if signal.status in _EXCLUDED:
            continue
        key = (signal.brand_name, signal.campaign_group_id or signal.id)
        grouped.setdefault(key, []).append(signal)

    entries: list[DigestEntry] = []
    for (brand, group_id), group_signals in grouped.items():
        top = max(group_signals, key=lambda s: s.confidence)
        entries.append(
            DigestEntry(
                brand_name=brand,
                campaign_group_id=(
                    group_id if any(s.campaign_group_id for s in group_signals) else None
                ),
                headline=top.campaign_name or top.title,
                signal_count=len(group_signals),
                top_confidence=round(top.confidence, 3),
                signal_ids=[s.id for s in group_signals],
                evidence_urls=[url for s in group_signals for url in url_map.get(s.id, [])][:5],
            )
        )

    entries.sort(key=lambda e: e.top_confidence, reverse=True)
    return entries
