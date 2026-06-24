from __future__ import annotations

import pytest

from ad_classifier.intelligence_crawler.sources.http import (
    DefaultHttpFetcher,
    RateLimiter,
    RobotsBlocked,
    RobotsGate,
)

ROBOTS = "User-agent: *\nDisallow: /private\n"


def test_robots_gate_allows_and_blocks():
    gate = RobotsGate(user_agent="UA", robots_open=lambda _url: ROBOTS)
    assert gate.allowed("https://x.com/news/a") is True
    assert gate.allowed("https://x.com/private/secret") is False


def test_robots_unavailable_is_allowed():
    gate = RobotsGate(user_agent="UA", robots_open=lambda _url: None)
    assert gate.allowed("https://x.com/anything") is True


def test_robots_disabled_allows_everything():
    gate = RobotsGate(user_agent="UA", robots_open=lambda _url: ROBOTS, enabled=False)
    assert gate.allowed("https://x.com/private/secret") is True


def test_rate_limiter_waits_for_same_host():
    slept: list[float] = []
    rl = RateLimiter(per_minute=60, sleep=slept.append, now=lambda: 0.0)  # 1.0s min interval
    rl.wait("h")  # first request: no wait
    rl.wait("h")  # immediate repeat: must wait ~1.0s
    assert slept and abs(slept[0] - 1.0) < 1e-6


def test_fetcher_enforces_robots_and_returns_body():
    fetcher = DefaultHttpFetcher(
        user_agent="UA",
        raw_open=lambda _u, _h: (200, "<rss/>", '"e"', None),
        robots_open=lambda _u: ROBOTS,
        sleep=lambda _s: None,
    )
    ok = fetcher.fetch("https://x.com/news/a", {})
    assert ok.status_code == 200 and ok.body == "<rss/>" and ok.etag == '"e"'
    with pytest.raises(RobotsBlocked):
        fetcher.fetch("https://x.com/private/x", {})
