"""Robots-gated, rate-limited HTTP fetcher — the real gate the v1 crawler never enforced.

The entity-graph crawler exposes ``respect_robots_txt`` / ``rate_limit_per_minute`` but does
not act on them. This module actually enforces both, and is the default network layer for
HTTP/RSS sources. Every side effect (network, robots fetch, sleep, clock) is injectable so the
gate and limiter are unit-testable with no network and no real waiting.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urlsplit

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: str
    etag: str | None = None
    last_modified: str | None = None


class RobotsBlocked(Exception):
    """Raised when robots.txt disallows the requested URL for our user agent."""


# (url, headers) -> (status_code, body, etag, last_modified)
RawOpen = Callable[[str, dict[str, str]], tuple[int, str, str | None, str | None]]
RobotsOpen = Callable[[str], str | None]  # robots_url -> robots.txt text (None if unavailable)
HttpFetcher = Callable[[str, dict[str, str]], HttpResponse]


class RobotsGate:
    """Per-origin robots.txt cache honoring Disallow for our user agent.

    Convention: if robots.txt is missing/unreachable, fetching is allowed.
    """

    def __init__(self, *, user_agent: str, robots_open: RobotsOpen, enabled: bool = True) -> None:
        self._ua = user_agent
        self._open = robots_open
        self._enabled = enabled
        self._cache: dict[str, robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        if not self._enabled:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._cache:
            self._cache[origin] = self._load(origin)
        parser = self._cache[origin]
        if parser is None:  # robots unavailable -> allowed
            return True
        return parser.can_fetch(self._ua, url)

    def _load(self, origin: str) -> robotparser.RobotFileParser | None:
        try:
            text = self._open(f"{origin}/robots.txt")
        except Exception:  # robots fetch failure -> treat as allowed
            return None
        if text is None:
            return None
        parser = robotparser.RobotFileParser()
        parser.parse(text.splitlines())
        return parser


class RateLimiter:
    """Per-host minimum interval between requests (token-bucket-lite)."""

    def __init__(
        self,
        *,
        per_minute: int,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = 60.0 / max(per_minute, 1)
        self._sleep = sleep
        self._now = now
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            elapsed = self._now() - last
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last[host] = self._now()


class DefaultHttpFetcher:
    """Robots-gated, rate-limited GET returning text. Default for HTTP/RSS sources."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_s: float = 12.0,
        rate_limit_per_minute: int = 20,
        respect_robots: bool = True,
        max_bytes: int = 2_000_000,
        raw_open: RawOpen | None = None,
        robots_open: RobotsOpen | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ua = user_agent
        self._timeout = timeout_s
        self._max_bytes = max_bytes
        self._open = raw_open or self._urllib_open
        self._robots = RobotsGate(
            user_agent=user_agent,
            robots_open=robots_open or self._urllib_robots,
            enabled=respect_robots,
        )
        self._limiter = RateLimiter(per_minute=rate_limit_per_minute, sleep=sleep, now=now)

    def fetch(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if not self._robots.allowed(url):
            raise RobotsBlocked(f"robots.txt disallows {url}")
        self._limiter.wait(urlsplit(url).netloc)
        status, body, etag, last_modified = self._open(url, {"User-Agent": self._ua, **headers})
        return HttpResponse(status_code=status, body=body, etag=etag, last_modified=last_modified)

    def _urllib_open(  # pragma: no cover - network
        self, url: str, headers: dict[str, str]
    ) -> tuple[int, str, str | None, str | None]:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = response.read(self._max_bytes).decode("utf-8", errors="replace")
                return (
                    int(getattr(response, "status", 200)),
                    body,
                    response.headers.get("ETag"),
                    response.headers.get("Last-Modified"),
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return 304, "", None, None
            return int(exc.code), "", None, None

    def _urllib_robots(self, robots_url: str) -> str | None:  # pragma: no cover - network
        request = urllib.request.Request(robots_url, headers={"User-Agent": self._ua}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.read(200_000).decode("utf-8", errors="replace")
        except Exception:
            return None
