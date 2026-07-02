"""Google Ads Transparency Center (ATC) internal-RPC client — US market.

ATC has **no official API**, and its public UI is a Flutter app that paints to a
``<canvas>`` with no scrapeable DOM. The only programmatic way to list a brand's
creatives is ATC's own JSON-RPC (the same endpoints the UI calls):

- ``SearchService/SearchCreatives`` — an advertiser's creatives, region-filtered.
- ``LookupService/GetAdvertiserById`` — advertiser name + region (identity check).

Calling these directly is a deliberate, **opt-in exception** to this module's usual
"no hidden-endpoint replay" guideline, chosen for the ATC source (read-only, US-only,
brand/advertiser-anchored, free, no key). The endpoints are unofficial and may change
without notice; failures are surfaced, never fatal to the run.

The RPC transport is injected (``RpcFetch``) so the client is fully testable offline.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

import structlog

logger = structlog.get_logger(__name__)

# ATC's internal region enum for the United States (verified empirically; the UI's
# ``region=US`` maps to this code in the RPC payload). US-market only by design.
US_REGION_CODE = 2840
RPC_BASE = "https://adstransparency.google.com/anji/_/rpc"
_DEFAULT_PAGE_SIZE = 40
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
# Best-effort map of the creative ``format`` code (field 4). Unknown codes pass through.
_FORMAT_LABELS = {1: "text", 2: "image", 3: "video"}

# (service_method, f_req_dict) -> parsed JSON dict. Injected so tests need no network.
RpcFetch = Callable[[str, dict], dict]
PreviewFetch = Callable[[str], str]

_URL_RE = re.compile(r"https?:(?:(?:\\?/\\?/)|(?://))[^\"'<>\s]+", re.IGNORECASE)
_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:embed|shorts)/|youtu\.be/|[?&]v=|ytimg\.com/(?:vi|vi_webp)/)"
    r"([A-Za-z0-9_-]{6,})",
    re.IGNORECASE,
)
_IMAGE_EXT_RE = re.compile(r"\.(?:avif|gif|jpe?g|png|webp)(?:[?#]|$)", re.IGNORECASE)
# Extension-less creative images on Google's ad CDNs (e.g. a rich-media banner's
# ``renderAs: BACKUP_IMAGE`` — the static representation of an HTML5 creative).
_AD_IMAGE_URL_RE = re.compile(
    r"^https?://(?:tpc\.googlesyndication\.com|s0\.2mdn\.net)/(?:archive/)?simgad/\d+",
    re.IGNORECASE,
)
# Inline creative HTML (field 3.3.2): an ``<img src=...>`` on Google's ad-image CDN.
_IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def advertiser_creatives_freq(
    advertiser_id: str, *, region: int, page_size: int, after: str | None = None
) -> dict:
    """Build the ``SearchCreatives`` ``f.req`` payload for one advertiser, region-scoped.

    ``after`` is the continuation token from a previous response (its field ``"2"``); passing
    it as request field ``"4"`` returns the next page (the offset field ``7.2`` does not work).
    """
    freq: dict = {
        "2": page_size,
        "3": {
            "8": [region],
            "12": {"1": "", "2": True},
            "13": {"1": [advertiser_id]},
        },
        "7": {"1": 1, "2": 0, "3": 2100},
    }
    if after:
        freq["4"] = after
    return freq


def parse_creatives(payload: dict) -> list[dict]:
    """Normalize a ``SearchCreatives`` response into flat creative dicts.

    The creative content is **polymorphic** (two shapes seen live):
    - hosted / video creatives expose a preview-script URL at field ``3.1.4``;
    - image / display creatives inline the rendered ad as HTML at field ``3.3.2`` — an
      ``<img src=...>`` on Google's ad-image CDN (``tpc.googlesyndication.com/archive/simgad/…``,
      a directly-downloadable file).

    We parse **both**, so the common image case is captured straight from the RPC with no
    extra preview fetch. ``format`` is derived from the actual content because the numeric
    ``format`` code (field 4) is unreliable — image/display creatives report code ``1``.
    """
    out: list[dict] = []
    for rec in payload.get("1", []) or []:
        if not isinstance(rec, dict):
            continue
        creative_id = rec.get("2")
        if not creative_id:
            continue
        content = rec.get("3")
        content = content if isinstance(content, dict) else {}
        hosted = content.get("1")
        hosted = hosted if isinstance(hosted, dict) else {}
        inline = _inline_creative(content)
        image_sources = inline.get("image_sources", [])
        format_code = rec.get("4")
        out.append(
            {
                "creative_id": creative_id,
                "advertiser_id": rec.get("1"),
                "advertiser_name": rec.get("12"),
                "format_code": format_code,
                "format": _creative_format(format_code, image_sources),
                "first_shown": _epoch(rec.get("6")),
                "last_shown": _epoch(rec.get("7")),
                "preview_url": hosted.get("4"),
                "image_sources": image_sources,
                "image_url": image_sources[0] if image_sources else None,
                "text": inline.get("text"),
            }
        )
    return out


def _inline_creative(content: dict) -> dict:
    """Parse the inline rendered-HTML creative at field ``3.3.2`` (image/display ads).

    Returns ``{image_sources: [...], text: str}`` — empty when the creative has no inline
    HTML (hosted/video creatives carry a ``preview_url`` at ``3.1.4`` instead).
    """
    node = content.get("3")
    node = node if isinstance(node, dict) else {}
    raw_html = node.get("2")
    if not isinstance(raw_html, str) or not raw_html.strip():
        return {}
    images = _dedupe(_normalize_js_url(src) for src in _IMG_SRC_RE.findall(raw_html))
    text = re.sub(r"\s+", " ", html.unescape(_HTML_TAG_RE.sub(" ", raw_html))).strip()
    result: dict = {}
    if images:
        result["image_sources"] = images
    if text:
        result["text"] = text
    return result


def _creative_format(format_code: object, image_sources: list[str]) -> str | None:
    """Human creative type. Prefers observed content over the unreliable numeric code map."""
    if image_sources:
        return "image"
    if isinstance(format_code, int):
        return _FORMAT_LABELS.get(format_code)
    return None


def search_creatives(
    advertiser_id: str,
    *,
    fetch: RpcFetch,
    region: int = US_REGION_CODE,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_pages: int = 1,
) -> list[dict]:
    """Fetch + normalize an advertiser's region-scoped creatives, following the cursor.

    Pages up to ``max_pages`` times via the response continuation token (field ``"2"``),
    de-duplicating by creative id. Stops early when the token is empty, a page is empty, or
    a page yields nothing new.
    """
    creatives: list[dict] = []
    seen: set[str] = set()
    token: str | None = None
    for _ in range(max(max_pages, 1)):
        payload = fetch(
            "SearchService/SearchCreatives",
            advertiser_creatives_freq(
                advertiser_id, region=region, page_size=page_size, after=token
            ),
        )
        if not isinstance(payload, dict):
            break
        page = parse_creatives(payload)
        fresh = [c for c in page if c["creative_id"] not in seen]
        for creative in fresh:
            seen.add(creative["creative_id"])
        creatives.extend(fresh)
        token = payload.get("2") if isinstance(payload.get("2"), str) else None
        if not token or not page or not fresh:
            break
    return creatives


def parse_preview_artifacts(script: str, *, preview_url: str | None = None) -> dict:
    """Extract useful creative assets from an ATC preview ``content.js`` response.

    Google renders many ATC previews through a JavaScript bundle instead of static HTML.
    We avoid evaluating the script and only pull stable URL-shaped artifacts: YouTube ids,
    thumbnails, direct video-ish URLs, direct image-ish URLs, and a link back to the ATC
    preview script. The returned keys intentionally match the generic artifact metadata
    already understood by the repository/Watcher.
    """
    # Decode JS escape sequences over the whole bundle FIRST. The URL regex excludes
    # quotes/angle brackets, but their escaped forms (``\x22``, ``<``, …) sail right
    # through the character class — extracting before decoding produced "URLs" with XML
    # fragments and stray backslashes baked in (seen live on VAST/2mdn video creatives).
    urls = _extract_urls(_decode_js_escapes(script))
    youtube_ids = _youtube_ids_from(urls)
    video_sources = [f"https://www.youtube.com/watch?v={video_id}" for video_id in youtube_ids]
    video_posters = [f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" for video_id in youtube_ids]
    image_sources: list[str] = []

    for url in urls:
        lower = url.lower()
        if _is_junk_asset_url(lower):
            continue
        if _is_video_url(lower):
            video_sources.append(url)
        elif _is_video_poster_url(lower):
            video_posters.append(url)
        elif _is_image_url(lower) or _AD_IMAGE_URL_RE.match(url):
            image_sources.append(url)
        # NOTE: we deliberately do NOT scrape other URLs as "destinations". A minified preview
        # bundle is full of library/namespace URLs (safevalues, w3.org/svg, amp runtime, …) that
        # are not the ad's landing page — scraping them produced junk. The resource already links
        # to the ATC creative page; a real click-through would need anchor-level parsing (TODO).

    out: dict[str, object] = {}
    if youtube_ids:
        out["youtube_video_ids"] = youtube_ids
    if video_sources:
        out["video_sources"] = _dedupe(video_sources)
    if video_posters:
        out["video_posters"] = _dedupe(video_posters)
    if image_sources:
        out["image_sources"] = _dedupe(image_sources)
    return out


def search_advertisers(
    query: str, *, fetch: RpcFetch, region: int = US_REGION_CODE, limit: int = 40
) -> list[dict]:
    """Resolve a free-text query to advertiser suggestions via ``SearchSuggestions``.

    Returns ``[{name, advertiser_id, region}]`` (ranked by ATC). Region-scoped to ``region``.
    """
    freq = {"1": query, "2": limit, "3": limit, "4": [region], "5": {"1": 1}}
    payload = fetch("SearchService/SearchSuggestions", freq)
    rows = payload.get("1", []) if isinstance(payload, dict) else []
    out: list[dict] = []
    for row in rows or []:
        advertiser = row.get("1") if isinstance(row, dict) else None
        advertiser = advertiser if isinstance(advertiser, dict) else {}
        if advertiser.get("2"):
            out.append(
                {
                    "name": advertiser.get("1"),
                    "advertiser_id": advertiser.get("2"),
                    "region": advertiser.get("3"),
                }
            )
    return out


def resolve_advertiser(
    brand: str,
    *,
    fetch: RpcFetch,
    accept_names: tuple[str, ...] = (),
    extra_queries: tuple[str, ...] = (),
    region: int = US_REGION_CODE,
) -> dict | None:
    """Brand name → advertiser ``{name, advertiser_id, region}``, or ``None``.

    Refuses to guess: returns only a US advertiser whose name **exactly** equals ``brand`` or
    one of ``accept_names`` (legal-name variants like "Ford Motor Company"). Never falls back
    to a dealer/look-alike. ``extra_queries`` lets the caller also search those legal names.
    """
    targets = {brand.strip().lower(), *(n.strip().lower() for n in accept_names if n)}
    candidates: dict[str, dict] = {}
    for query in (brand, *extra_queries):
        for row in search_advertisers(query, fetch=fetch, region=region):
            if row["region"] == "US" and row["advertiser_id"]:
                candidates.setdefault(row["advertiser_id"], row)
    for row in candidates.values():
        if (row["name"] or "").strip().lower() in targets:
            return row
    return None


def lookup_advertiser(advertiser_id: str, *, fetch: RpcFetch) -> dict:
    """Return ``{advertiser_id, name, region}`` — the look-alike / identity guard."""
    payload = fetch("LookupService/GetAdvertiserById", {"1": advertiser_id, "3": {"1": 1}})
    rec = payload.get("1") if isinstance(payload, dict) else None
    rec = rec if isinstance(rec, dict) else {}
    return {
        "advertiser_id": rec.get("1"),
        "name": rec.get("2"),
        "region": rec.get("11") or rec.get("3"),
    }


def _epoch(node: object) -> int | None:
    if isinstance(node, dict):
        node = node.get("1")
    if not isinstance(node, (int, str)):
        return None
    try:
        return int(node)
    except ValueError:
        return None


def default_rpc_fetch(service_method: str, f_req: dict) -> dict:  # pragma: no cover - network
    """Real transport: POST ``f.req`` form-encoded to the ATC RPC; parse JSON."""
    url = f"{RPC_BASE}/{service_method}?authuser="
    body = urllib.parse.urlencode({"f.req": json.dumps(f_req, separators=(",", ":"))}).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Same-Domain": "1",
            "Origin": "https://adstransparency.google.com",
            "Referer": "https://adstransparency.google.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", errors="replace") or "{}")


def default_preview_fetch(preview_url: str) -> str:  # pragma: no cover - network
    """Fetch an ATC preview script using browser-like headers."""
    request = urllib.request.Request(
        preview_url,
        headers={
            "User-Agent": _UA,
            "Referer": "https://adstransparency.google.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_urls(value: str) -> list[str]:
    return _dedupe(_normalize_js_url(match.group(0)) for match in _URL_RE.finditer(value or ""))


def _decode_js_escapes(value: str) -> str:
    clean = value.replace("\\/", "/")
    clean = re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), clean)
    return re.sub(r"\\x([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), clean)


def _normalize_js_url(value: str) -> str:
    # Raw backslashes are never valid in a URL; leftovers are double-escaping residue
    # (``\\x3d`` decodes to ``\=``), so dropping them restores the real URL.
    clean = _decode_js_escapes(value).replace("\\", "")
    return html.unescape(clean).rstrip(".,);]")


def _youtube_ids_from(urls: list[str]) -> list[str]:
    ids: list[str] = []
    for url in urls:
        for match in _YOUTUBE_ID_RE.finditer(url):
            ids.append(match.group(1))
    return _dedupe(ids)


def _is_video_url(lower_url: str) -> bool:
    return (
        "googlevideo.com/" in lower_url
        or "videoplayback" in lower_url
        or ".mp4" in lower_url
        or ".webm" in lower_url
        or ".m3u8" in lower_url
    )


def _is_video_poster_url(lower_url: str) -> bool:
    return "ytimg.com/" in lower_url and _is_image_url(lower_url)


def _is_image_url(lower_url: str) -> bool:
    return bool(_IMAGE_EXT_RE.search(lower_url))


def _is_junk_asset_url(lower_url: str) -> bool:
    """Tracking pixels / ad-infra assets that must never surface as creative artifacts."""
    return lower_url.endswith("/dot.gif") or "/pagead/" in lower_url or "/activeview" in lower_url


def _dedupe(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
