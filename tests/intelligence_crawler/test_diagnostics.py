from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

from ad_classifier.intelligence_crawler.diagnostics import classify_exception, safe_traceback
from ad_classifier.intelligence_crawler.models import IntelSource, SourcePollResult
from ad_classifier.intelligence_crawler.run_policy import schedule


def test_safe_traceback_preserves_details_using_ascii_escapes() -> None:
    try:
        raise ValueError("provider said: blocked → retry later")
    except ValueError as exc:
        rendered = safe_traceback(exc)

    rendered.encode("ascii")
    assert "ValueError" in rendered
    assert "blocked \\u2192 retry later" in rendered
    assert "test_safe_traceback_preserves_details_using_ascii_escapes" in rendered


def test_http_429_retry_after_controls_cooldown() -> None:
    error = HTTPError(
        "https://provider.example",
        429,
        "Too Many Requests",
        {"Retry-After": "7200"},
        None,
    )
    diagnostic = classify_exception(error, provider="google_atc", phase="creative_pages")
    now = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
    source = IntelSource(
        id="g1", brand_name="Google", source_type="google_atc", poll_interval_hours=24
    )
    result = SourcePollResult(
        source_id="g1",
        outcome="failed",
        complete=False,
        diagnostics=[diagnostic],
    )

    next_due, cooldown = schedule(source, now, result, consecutive_errors=1)

    assert diagnostic.details["retry_after"] == "7200"
    assert diagnostic.details["retry_after_seconds"] == 7200
    assert next_due == now + timedelta(hours=2)
    assert cooldown == next_due
