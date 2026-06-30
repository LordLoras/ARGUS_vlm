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

import json
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
    """Normalize a ``SearchCreatives`` response into flat creative dicts."""
    out: list[dict] = []
    for rec in payload.get("1", []) or []:
        if not isinstance(rec, dict):
            continue
        creative_id = rec.get("2")
        if not creative_id:
            continue
        content = rec.get("3")
        content = content if isinstance(content, dict) else {}
        inner = content.get("1")
        inner = inner if isinstance(inner, dict) else {}
        format_code = rec.get("4")
        out.append(
            {
                "creative_id": creative_id,
                "advertiser_id": rec.get("1"),
                "advertiser_name": rec.get("12"),
                "format_code": format_code,
                "format": _FORMAT_LABELS.get(format_code) if isinstance(format_code, int) else None,
                "first_shown": _epoch(rec.get("6")),
                "last_shown": _epoch(rec.get("7")),
                "preview_url": inner.get("4"),
            }
        )
    return out


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
