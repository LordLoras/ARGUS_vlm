"""Pure parsing and URL-cleaning helpers for Meta Ad Library cards."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_LIBRARY_ID_RE = re.compile(r"\bLibrary\s+ID[:\s]*([0-9]+)", re.IGNORECASE)
_STARTED_RE = re.compile(
    r"Started\s+running\s+on\s+(.+?)(?:\s+(?:Platforms|Active|Inactive|Library ID)\b|$)",
    re.IGNORECASE,
)
_VERSIONS_RE = re.compile(
    r"\b([0-9]+)\s+ads?\s+use\s+this\s+creative\s+and\s+text\b",
    re.IGNORECASE,
)
_PLATFORMS = ("Facebook", "Instagram", "Messenger", "Audience Network", "Threads")
_FB_REDIRECT_HOSTS = ("l.facebook.com", "lm.facebook.com", "l.instagram.com")
_HREF_JUNK_HOST_MARKERS = (
    "ampproject.org",
    "gstatic.com",
    "googlesyndication.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googletagservices.com",
    "scorecardresearch.com",
    "app-measurement.com",
    "googleapis.com",
    "fbcdn.net",
)
_HREF_ASSET_RE = re.compile(
    r"\.(?:js|mjs|css|json|map|wasm|woff2?|ttf|otf|eot|svg|ico)(?:[?#]|$)", re.IGNORECASE
)


def parse_card_text(text: str) -> dict[str, Any]:
    compact = collapse_whitespace(text)
    library_match = _LIBRARY_ID_RE.search(compact)
    started_match = _STARTED_RE.search(compact)
    versions_match = _VERSIONS_RE.search(compact)
    status = None
    if re.search(r"\bActive\b", compact, re.IGNORECASE):
        status = "active"
    elif re.search(r"\bInactive\b", compact, re.IGNORECASE):
        status = "inactive"
    return {
        "library_id": library_match.group(1) if library_match else None,
        "status": status,
        "started_running": started_match.group(1).strip() if started_match else None,
        "platforms": platforms_from_text(compact),
        "creative_variant_count": int(versions_match.group(1)) if versions_match else None,
        "has_multiple_versions": bool(
            re.search(r"\bmultiple\s+versions\b", compact, re.IGNORECASE)
        ),
    }


def platforms_from_text(value: str) -> list[str]:
    compact = value.lower()
    return [platform for platform in _PLATFORMS if platform.lower() in compact]


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return clean[:80] or "unknown"


def _unwrap_redirect(href: str) -> str:
    try:
        parsed = urlparse(href)
    except ValueError:
        return href
    host = parsed.netloc.lower()
    is_fb_redirect = any(
        host == item or host.endswith("." + item) for item in _FB_REDIRECT_HOSTS
    ) or parsed.path.endswith("/l.php")
    if is_fb_redirect:
        target = parse_qs(parsed.query).get("u", [None])[0]
        if target:
            return unquote(target)
    return href


def _is_junk_href(href: str) -> bool:
    try:
        host = urlparse(href).netloc.lower()
    except ValueError:
        return False
    if any(marker in host for marker in _HREF_JUNK_HOST_MARKERS):
        return True
    return bool(_HREF_ASSET_RE.search(href.lower()))


def clean_links(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    links: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = collapse_whitespace(str(item.get("text") or ""))
        href = _unwrap_redirect(str(item.get("href") or ""))
        if href and _is_junk_href(href):
            href = ""
        if not text and not href:
            continue
        key = (text, href)
        if key in seen:
            continue
        seen.add(key)
        links.append({"text": text, "href": href})
    return links[:20]


def clean_source_urls(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        src = str(value or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        out.append(src)
    return out[:20]


def clean_rect(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    rect: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        try:
            rect[key] = float(raw.get(key))
        except (TypeError, ValueError):
            continue
    return rect
