"""Pure crawl-result normalization, retry scheduling, and asset projection policy."""

from __future__ import annotations

from datetime import timedelta

from ad_classifier.intelligence_crawler.diagnostics import legacy_error_diagnostic
from ad_classifier.intelligence_crawler.ids import media_asset_id
from ad_classifier.intelligence_crawler.models import (
    IntelMediaAsset,
    IntelResource,
    PollDiagnostic,
    RunStatus,
    SourcePollResult,
    SourceRunItem,
)


def normalize_poll_result(result: SourcePollResult, provider: str) -> SourcePollResult:
    diagnostics = list(result.diagnostics)
    diagnostics.extend(legacy_error_diagnostic(error, provider=provider) for error in result.errors)
    outcome = result.outcome
    complete = result.complete
    if diagnostics and outcome == "success":
        outcome = "partial" if result.items else "failed"
        complete = False
    if result.truncated and outcome == "success":
        outcome, complete = "partial", False
    return result.model_copy(
        update={"diagnostics": diagnostics, "outcome": outcome, "complete": complete}
    )


def schedule(source, now, result, consecutive_errors):
    if result.complete:
        return now + timedelta(hours=source.poll_interval_hours), None
    primary = primary_diagnostic(result.diagnostics)
    category = primary.category if primary else "unknown"
    if result.outcome == "partial":
        delay = min(timedelta(hours=1), timedelta(hours=source.poll_interval_hours / 4))
        delay = max(delay, timedelta(minutes=10))
    elif category == "rate_limited":
        delay = timedelta(hours=min(24, 2 ** min(consecutive_errors - 1, 5)))
    elif category in {"configuration", "authentication"}:
        delay = timedelta(hours=12)
    elif category in {"provider_ui_changed", "provider_api_changed", "parse_error"}:
        delay = timedelta(hours=6)
    else:
        delay = timedelta(minutes=min(360, 15 * (2 ** min(consecutive_errors - 1, 4))))
    next_due = now + delay
    return next_due, next_due


def media_assets(resource: IntelResource) -> list[IntelMediaAsset]:
    raw = resource.metadata
    candidates: list[tuple[str, str, int | None]] = []
    if resource.thumbnail_url:
        candidates.append(("thumbnail", resource.thumbnail_url, None))
    for key, asset_type in (
        ("image_sources", "image"),
        ("video_sources", "video"),
        ("video_posters", "video_poster"),
        ("background_image_sources", "background_image"),
    ):
        values = raw.get(key)
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    duration = resource.duration_ms if asset_type == "video" else None
                    candidates.append((asset_type, value.strip(), duration))
    screenshot = raw.get("screenshot_path")
    if isinstance(screenshot, str) and screenshot.strip():
        candidates.append(("card_screenshot", screenshot.strip(), None))

    return [
        IntelMediaAsset(
            id=media_asset_id(resource.id, asset_type, url),
            resource_id=resource.id,
            asset_type=asset_type,
            url=url,
            duration_ms=duration,
        )
        for asset_type, url, duration in dict.fromkeys(candidates)
    ]


def primary_diagnostic(diagnostics: list[PollDiagnostic]) -> PollDiagnostic | None:
    return diagnostics[0] if diagnostics else None


def poll_reason(result, baseline):
    if baseline and result.complete:
        return "Complete baseline poll; no live signals emitted."
    if result.outcome == "partial":
        return result.truncation_reason or "Provider returned an incomplete result."
    if result.outcome == "not_modified":
        return "Provider reported no change since the previous successful poll."
    if result.outcome == "explicit_empty":
        return "Provider explicitly returned a complete empty result."
    return None


def overall_status(items: list[SourceRunItem]) -> RunStatus:
    if items and all(item.status == "failed" for item in items):
        return "failed"
    if any(item.status in {"failed", "partial"} for item in items):
        return "degraded"
    return "completed"
