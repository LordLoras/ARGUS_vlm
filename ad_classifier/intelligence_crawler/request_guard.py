"""No-request crawl guards for provider health, cooldown, and fresh projections."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    PollDiagnostic,
    SourceRunItem,
    SourceState,
)
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.timeutils import as_utc


def request_guard(
    repo: IntelRepository,
    conn: sqlite3.Connection,
    source: IntelSource,
    now: datetime,
    *,
    respect_freshness: bool,
) -> SourceRunItem | None:
    """Return a durable no-request result when provider/source state forbids a poll."""
    circuit = repo.get_provider_circuit(conn, source.source_type, now=now)
    if circuit is not None:
        diagnostic = PollDiagnostic(
            code="provider_circuit_open",
            category=circuit.category,
            message=(
                f"{source.source_type} requests paused until "
                f"{circuit.open_until.isoformat()} after {circuit.error_code} "
                f"on {circuit.source_id}."
            ),
            retryable=True,
            provider=source.source_type,
            phase="request_guard",
            details={
                "open_until": circuit.open_until.isoformat(),
                "trigger_source_id": circuit.source_id,
                "trigger_error_code": circuit.error_code,
            },
        )
        return SourceRunItem(
            source_id=source.id,
            status="skipped",
            complete=False,
            reason=diagnostic.message,
            failure_category=diagnostic.category,
            error_code=diagnostic.code,
            diagnostics=[diagnostic],
            next_due_at=circuit.open_until,
            stop_reason="provider_circuit_open",
        )

    if not respect_freshness:
        return None
    blocked_until, reason, code = source_guard(repo.get_source_state(conn, source.id), now)
    if blocked_until is None:
        return None
    return SourceRunItem(
        source_id=source.id,
        status="skipped",
        complete=False,
        reason=reason,
        error_code=code,
        next_due_at=blocked_until,
        stop_reason=code,
    )


def source_guard(
    state: SourceState, now: datetime
) -> tuple[datetime | None, str | None, str | None]:
    now_utc = as_utc(now)
    assert now_utc is not None
    cooldown = as_utc(state.cooldown_until)
    if cooldown is not None and cooldown > now_utc:
        return (
            cooldown,
            f"Source is cooling down until {cooldown.isoformat()} after its last error.",
            "source_cooldown_active",
        )
    next_due = as_utc(state.next_due_at)
    if next_due is not None and next_due > now_utc:
        return (
            next_due,
            f"Current copy is fresh; next provider check is due at {next_due.isoformat()}.",
            "source_not_due",
        )
    return None, None, None
