from __future__ import annotations

from ad_classifier.intelligence_crawler.diagnostics import safe_traceback


def test_safe_traceback_preserves_details_using_ascii_escapes() -> None:
    try:
        raise ValueError("provider said: blocked → retry later")
    except ValueError as exc:
        rendered = safe_traceback(exc)

    rendered.encode("ascii")
    assert "ValueError" in rendered
    assert "blocked \\u2192 retry later" in rendered
    assert "test_safe_traceback_preserves_details_using_ascii_escapes" in rendered
