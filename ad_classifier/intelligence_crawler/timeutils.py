"""UTC time helpers. All persisted timestamps are tz-aware UTC ISO strings."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime | None) -> datetime | None:
    """Coerce a datetime to tz-aware UTC. Naive datetimes are assumed UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso(dt: datetime | None) -> str | None:
    coerced = as_utc(dt)
    return coerced.isoformat() if coerced else None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return as_utc(datetime.fromisoformat(value))
