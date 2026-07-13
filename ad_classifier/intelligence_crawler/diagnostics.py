"""Stable, provider-neutral crawl failure diagnostics.

Adapters report machine-readable causes instead of making operators infer health from an
empty item list.  The full exception remains in structured logs; API-safe diagnostics are
short and omit tracebacks and response bodies.
"""

from __future__ import annotations

import socket
import traceback
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError

from ad_classifier.intelligence_crawler.models import FailureCategory, PollDiagnostic


class ProviderUiChangedError(RuntimeError):
    """Expected public-page structure or identifiers were not found."""


class ProviderApiChangedError(RuntimeError):
    """A provider response no longer matches the known response contract."""


class ProviderBlockedError(RuntimeError):
    """The provider served a login, checkpoint, CAPTCHA, or explicit denial."""


def safe_traceback(exc: BaseException) -> str:
    """Return a complete ASCII-safe traceback for Windows consoles and JSON logs."""
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return rendered.encode("ascii", errors="backslashreplace").decode("ascii")


def classify_exception(
    exc: BaseException, *, provider: str | None = None, phase: str | None = None
) -> PollDiagnostic:
    """Convert an exception into a stable operator-facing diagnostic."""
    status = exc.code if isinstance(exc, HTTPError) else None
    message = _safe_message(exc)
    lower = message.lower()

    category: FailureCategory
    code: str
    retryable = False
    if isinstance(exc, ProviderUiChangedError):
        category, code = "provider_ui_changed", "provider_ui_contract_changed"
    elif isinstance(exc, ProviderApiChangedError):
        category, code = "provider_api_changed", "provider_response_contract_changed"
    elif isinstance(exc, ProviderBlockedError):
        category, code = "blocked", "provider_access_blocked"
        retryable = True
    elif status == 429 or any(
        marker in lower for marker in ("rate limit", "too many requests", "quota exceeded", "429")
    ):
        category, code, retryable = "rate_limited", "provider_rate_limited", True
    elif status in {401, 407} or "unauthorized" in lower:
        category, code = "authentication", "provider_authentication_failed"
    elif status == 403 or any(
        marker in lower for marker in ("captcha", "checkpoint", "access denied", "blocked")
    ):
        category, code, retryable = "blocked", "provider_access_blocked", True
    elif isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in lower:
        category, code, retryable = "transport", "provider_timeout", True
    elif isinstance(exc, (URLError, ConnectionError, OSError)):
        category, code, retryable = "transport", "provider_connection_failed", True
    elif isinstance(exc, (ValueError, KeyError, TypeError)):
        category, code = "parse_error", "provider_response_parse_failed"
    else:
        category, code = "unknown", "provider_poll_failed"

    return PollDiagnostic(
        code=code,
        category=category,
        message=message,
        retryable=retryable,
        provider=provider,
        phase=phase,
        http_status=status,
        details=_retry_after_details(exc),
    )


def configuration_diagnostic(
    code: str, message: str, *, provider: str | None = None
) -> PollDiagnostic:
    return PollDiagnostic(
        code=code,
        category="configuration",
        message=message,
        provider=provider,
        phase="configuration",
    )


def legacy_error_diagnostic(message: str, *, provider: str | None = None) -> PollDiagnostic:
    """Classify pre-contract adapter errors while custom adapters migrate."""
    lower = message.lower()
    if "needs " in lower or "required" in lower or "missing" in lower:
        return configuration_diagnostic("source_configuration_invalid", message, provider=provider)
    if "rate" in lower or "quota" in lower or "429" in lower:
        category: FailureCategory = "rate_limited"
        code = "provider_rate_limited"
        retryable = True
    elif "parse" in lower or "xml" in lower or "json" in lower:
        category, code, retryable = "parse_error", "provider_response_parse_failed", False
    else:
        category, code, retryable = "unknown", "provider_reported_error", False
    return PollDiagnostic(
        code=code,
        category=category,
        message=message[:300],
        retryable=retryable,
        provider=provider,
    )


def http_status_diagnostic(status: int, *, provider: str, phase: str = "fetch") -> PollDiagnostic:
    if status == 429:
        category: FailureCategory = "rate_limited"
        code, retryable = "provider_rate_limited", True
    elif status in {401, 407}:
        category, code, retryable = "authentication", "provider_authentication_failed", False
    elif status == 403:
        category, code, retryable = "blocked", "provider_access_blocked", True
    elif status >= 500:
        category, code, retryable = "transport", "provider_server_error", True
    else:
        category, code, retryable = "transport", "provider_http_error", False
    return PollDiagnostic(
        code=code,
        category=category,
        message=f"Provider request failed with HTTP status {status}.",
        retryable=retryable,
        provider=provider,
        phase=phase,
        http_status=status,
    )


def _safe_message(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"Provider HTTP request failed with status {exc.code}."
    raw = " ".join(str(exc).split())
    return (raw or exc.__class__.__name__)[:300]


def _retry_after_details(exc: BaseException) -> dict[str, int | str]:
    if not isinstance(exc, HTTPError) or not exc.headers:
        return {}
    raw = str(exc.headers.get("Retry-After") or "").strip()
    if not raw:
        return {}
    try:
        seconds = max(0, int(raw))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            seconds = max(0, int((retry_at - datetime.now(UTC)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return {"retry_after": raw[:100]}
    return {"retry_after": raw[:100], "retry_after_seconds": seconds}
