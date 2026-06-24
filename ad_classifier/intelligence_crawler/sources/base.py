"""Source-adapter interface, registry, and the offline mock adapter.

This is the extensibility seam. The runner depends only on :class:`SourceAdapter` and
the registry — never on a concrete source — so a new integration (YouTube, Meta, an RSS
flavor, a paid TV-ad API) is added by writing one module:

    from ad_classifier.intelligence_crawler.sources.base import (
        SourceAdapter, register_source, SourcePollResult,
    )

    @register_source("my_api")
    class MyApiAdapter:
        tier = "B"
        def __init__(self, *, http=None, intel_config=None):
            ...
        def poll(self, source, state, *, now) -> SourcePollResult:
            ...

…and importing it in ``sources/__init__.py``. No core code changes required.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

import structlog

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    RawSourceItem,
    SourcePollResult,
    SourceState,
    Tier,
)

logger = structlog.get_logger(__name__)


@runtime_checkable
class SourceAdapter(Protocol):
    """Polls one source for new items. Implementations must be network-isolatable.

    Adapters never write to the DB and never decide what is "new" — they only fetch and
    normalize. Change detection, dedup, scoring, and persistence are the runner's job.
    """

    source_type: str
    tier: Tier

    def poll(
        self, source: IntelSource, state: SourceState, *, now: datetime
    ) -> SourcePollResult: ...


# adapter_type -> adapter class. Populated by @register_source at import time.
_REGISTRY: dict[str, type] = {}


def register_source(source_type: str):
    """Class decorator that registers an adapter under ``source_type``."""

    def decorator(cls: type) -> type:
        cls.source_type = source_type  # type: ignore[attr-defined]
        _REGISTRY[source_type] = cls
        return cls

    return decorator


def available_source_types() -> list[str]:
    return sorted(_REGISTRY)


def build_adapter(
    source_type: str,
    *,
    http=None,
    intel_config: IntelConfig | None = None,
) -> SourceAdapter:
    """Instantiate the adapter registered for ``source_type``.

    Adapters accept ``http`` and ``intel_config`` keyword args; ones that need neither
    simply ignore them. Raises KeyError for an unknown type.
    """
    try:
        cls = _REGISTRY[source_type]
    except KeyError as exc:  # pragma: no cover - guarded by config validation upstream
        raise KeyError(
            f"unknown source_type '{source_type}'; registered: {available_source_types()}"
        ) from exc
    return cls(http=http, intel_config=intel_config)


@register_source("mock")
class MockSourceAdapter:
    """Deterministic, offline adapter. Items come from ``source.config['items']``.

    Each item is a dict matching :class:`RawSourceItem` fields. Lets the whole pipeline
    be exercised in tests and demos with no network. The watermark is set to the latest
    published timestamp so re-polls are incremental.
    """

    tier: Tier = "A"

    def __init__(self, *, http=None, intel_config: IntelConfig | None = None) -> None:
        self._http = http
        self._config = intel_config

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        raw_items = source.config.get("items", [])
        items: list[RawSourceItem] = []
        errors: list[str] = []
        for entry in raw_items:
            try:
                items.append(RawSourceItem.model_validate(entry))
            except Exception as exc:  # pragma: no cover - bad fixture data
                errors.append(f"invalid mock item: {exc}")
        watermark = _latest_published(items) or state.watermark
        logger.debug(
            "mock_source_poll", source_id=source.id, item_count=len(items), errors=len(errors)
        )
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=watermark,
            errors=errors,
        )


def _latest_published(items: list[RawSourceItem]) -> str | None:
    published = [item.published_at for item in items if item.published_at is not None]
    if not published:
        return None
    return max(published).isoformat()
