"""Meta Ad Library public-UI browser probe used by the production source adapter.

It opens a public Meta Ad Library URL with Playwright, scrolls the page, finds visible
ad cards that expose a ``Library ID``, and can write screenshots plus a JSON summary.
The adapter translates probe state into explicit complete, partial, empty, or failed
poll outcomes so browser/UI changes are operationally visible.

Guardrails:
- public UI only, no login flow
- no ad clicks
- no hidden endpoint replay
- no writes to intelligence_crawler.db
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from ad_classifier.intelligence_crawler.diagnostics import (
    ProviderBlockedError,
    ProviderUiChangedError,
)
from ad_classifier.intelligence_crawler.meta_probe_dom import (
    mark_candidate_cards as _mark_candidate_cards,
)
from ad_classifier.intelligence_crawler.meta_probe_dom import (
    visible_library_ids as _visible_library_ids,
)
from ad_classifier.intelligence_crawler.meta_probe_parsing import (
    clean_links as _clean_links,
)
from ad_classifier.intelligence_crawler.meta_probe_parsing import (
    clean_rect as _clean_rect,
)
from ad_classifier.intelligence_crawler.meta_probe_parsing import (
    clean_source_urls as _clean_source_urls,
)
from ad_classifier.intelligence_crawler.meta_probe_parsing import (
    collapse_whitespace as _collapse_whitespace,
)
from ad_classifier.intelligence_crawler.meta_probe_parsing import (
    parse_card_text as _parse_card_text,
)
from ad_classifier.intelligence_crawler.meta_probe_parsing import (
    platforms_from_text as _platforms_from_text,
)
from ad_classifier.intelligence_crawler.meta_probe_parsing import (
    safe_filename as _safe_filename,
)

# Kept for compatibility with callers of the original probe helper surface.
_clean_image_sources = _clean_source_urls

TOYOTA_META_AD_LIBRARY_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=US&is_targeted_country=false"
    "&media_type=all&search_type=page&sort_data[mode]=relevancy_monthly_grouped"
    "&sort_data[direction]=desc&view_all_page_id=197052454200"
)


@dataclass(frozen=True)
class MetaProbeCard:
    index: int
    library_id: str | None
    status: str | None
    started_running: str | None
    platforms: list[str]
    text_excerpt: str
    text: str
    links: list[dict[str, str]] = field(default_factory=list)
    image_sources: list[str] = field(default_factory=list)
    video_sources: list[str] = field(default_factory=list)
    video_posters: list[str] = field(default_factory=list)
    background_image_sources: list[str] = field(default_factory=list)
    video_count: int = 0
    creative_variant_count: int | None = None
    has_multiple_versions: bool = False
    screenshot_path: str | None = None
    rect: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class MetaProbeResult:
    source_url: str
    final_url: str
    fetched_at: str
    cards_count: int
    full_page_screenshot: str | None
    cards: list[MetaProbeCard]
    scrolls_completed: int = 0
    unique_library_ids_seen: int = 0
    stopped_after_no_new: bool = False
    page_state: str = "ads"
    hit_card_limit: bool = False
    hit_scroll_limit: bool = False

    def write_json(self, path: Path) -> None:
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def run_meta_ad_library_probe(
    *,
    url: str = TOYOTA_META_AD_LIBRARY_URL,
    out_dir: Path,
    scrolls: int = 6,
    max_cards: int = 30,
    headed: bool = False,
    timeout_s: float = 45.0,
    wait_ms: int = 1800,
    stop_after_no_new: int = 3,
) -> MetaProbeResult:
    """Capture visible Meta Ad Library cards from a public URL."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Playwright is not installed. Install the browser extra with "
            "`pip install -e .[browser]` and then run "
            "`python -m playwright install chromium`."
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    cards: list[MetaProbeCard] = []
    full_page_screenshot: Path | None = None
    scrolls_completed = 0
    seen_library_ids: set[str] = set()
    stopped_after_no_new = False
    page_state = "ads"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1400},
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
            _dismiss_common_dialogs(page)
            page.wait_for_timeout(wait_ms)
            page_state = _wait_for_ad_library_content(page, timeout_ms=max(wait_ms * 8, 15000))
            seen_library_ids.update(_visible_library_ids(page))
            _capture_visible_cards(page, out_dir, cards, max_cards=max_cards)
            no_new_rounds = 0
            for _ in range(max(scrolls, 0)):
                if len(cards) >= max_cards:
                    break
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(wait_ms)
                scrolls_completed += 1

                previous_count = len(seen_library_ids)
                seen_library_ids.update(_visible_library_ids(page))
                _capture_visible_cards(page, out_dir, cards, max_cards=max_cards)
                if len(seen_library_ids) <= previous_count:
                    no_new_rounds += 1
                else:
                    no_new_rounds = 0
                if (
                    stop_after_no_new > 0
                    and seen_library_ids
                    and no_new_rounds >= stop_after_no_new
                ):
                    stopped_after_no_new = True
                    break

            full_page_screenshot = out_dir / "meta_ad_library_full_page.png"
            page.screenshot(path=str(full_page_screenshot), full_page=True)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Meta Ad Library page timed out: {exc}") from exc
        finally:
            context.close()
            browser.close()

    result = MetaProbeResult(
        source_url=url,
        final_url=page.url,
        fetched_at=datetime.now(UTC).isoformat(),
        cards_count=len(cards),
        full_page_screenshot=str(full_page_screenshot) if full_page_screenshot else None,
        cards=cards,
        scrolls_completed=scrolls_completed,
        unique_library_ids_seen=len(seen_library_ids),
        stopped_after_no_new=stopped_after_no_new,
        page_state=page_state,
        hit_card_limit=len(cards) >= max_cards,
        hit_scroll_limit=(scrolls_completed >= max(scrolls, 0) and not stopped_after_no_new),
    )
    result.write_json(out_dir / "meta_ad_library_probe.json")
    return result


def _dismiss_common_dialogs(page: Any) -> None:
    labels = [
        "Allow all cookies",
        "Accept all",
        "Accept All",
        "Only allow essential cookies",
        "Decline optional cookies",
        "Close",
        "Not now",
    ]
    for label in labels:
        try:
            locator = page.get_by_role("button", name=label)
            if locator.count():
                locator.first.click(timeout=1500)
                page.wait_for_timeout(500)
        except Exception:
            continue


def _wait_for_ad_library_content(page: Any, *, timeout_ms: int) -> str:
    try:
        page.wait_for_function(
            """
            () => {
              const text = document.body?.innerText || "";
              return /Library\\s+ID/i.test(text) ||
                /No ads|No results|currently running ads|try changing/i.test(text);
            }
            """,
            timeout=timeout_ms,
        )
    except Exception as exc:
        body = _body_text(page).lower()
        if any(marker in body for marker in ("log in", "captcha", "checkpoint", "blocked")):
            raise ProviderBlockedError("Meta served a login, checkpoint, or blocked page.") from exc
        raise ProviderUiChangedError(
            "Meta page did not expose ad cards or a recognized empty-result state."
        ) from exc
    body = _body_text(page)
    if re.search(
        r"No ads|No results|currently running ads|try changing", body, re.IGNORECASE
    ) and not re.search(r"Library\s+ID", body, re.IGNORECASE):
        return "explicit_empty"
    return "ads"


def _body_text(page: Any) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=2000) or "")
    except Exception:
        return ""


def _capture_visible_cards(
    page: Any,
    out_dir: Path,
    cards: list[MetaProbeCard],
    *,
    max_cards: int,
) -> None:
    """Snapshot newly visible cards before virtualized/infinite-scroll DOM nodes disappear."""
    known_ids = {card.library_id for card in cards if card.library_id}
    known_text = {card.text for card in cards if not card.library_id}
    for raw in _mark_candidate_cards(page, max_cards=max_cards):
        if len(cards) >= max_cards:
            break
        selector_index = int(raw["index"])
        text = _collapse_whitespace(str(raw.get("text") or ""))
        parsed = _parse_card_text(text)
        library_id = parsed["library_id"]
        if (library_id and library_id in known_ids) or (not library_id and text in known_text):
            continue
        global_index = len(cards)
        screenshot_path = _screenshot_card(page, out_dir, selector_index, library_id)
        cards.append(
            MetaProbeCard(
                index=global_index,
                library_id=library_id,
                status=parsed["status"],
                started_running=parsed["started_running"],
                platforms=_platforms_from_text(
                    " ".join([text, *[str(item) for item in raw.get("platform_labels") or []]])
                ),
                text_excerpt=text[:600],
                text=text,
                links=_clean_links(raw.get("links")),
                image_sources=_clean_source_urls(raw.get("image_sources")),
                video_sources=_clean_source_urls(raw.get("video_sources")),
                video_posters=_clean_source_urls(raw.get("video_posters")),
                background_image_sources=_clean_source_urls(raw.get("background_image_sources")),
                video_count=int(raw.get("video_count") or 0),
                creative_variant_count=parsed["creative_variant_count"],
                has_multiple_versions=parsed["has_multiple_versions"],
                screenshot_path=str(screenshot_path) if screenshot_path else None,
                rect=_clean_rect(raw.get("rect")),
            )
        )
        if library_id:
            known_ids.add(library_id)
        else:
            known_text.add(text)


def _screenshot_card(page: Any, out_dir: Path, index: int, library_id: str | None) -> Path | None:
    filename = f"card_{index:03d}"
    if library_id:
        filename += f"_{_safe_filename(library_id)}"
    path = out_dir / f"{filename}.png"
    try:
        page.locator(f'[data-argus-meta-ad-card="{index}"]').screenshot(
            path=str(path), timeout=6000
        )
    except Exception:
        return None
    return path


# --- brand -> Meta page id resolution (best-effort) -------------------------------------
# Meta has no clean suggest RPC, so resolution scrapes the public Ad Library page-search and
# matches on the page NAME. Less reliable than ATC's resolver. The candidate fetch is injected
# (``search``) so the match/refuse-to-guess logic is unit-tested offline.

# brand -> [{"page_id": str, "name": str}]. Injected for tests.
MetaPageSearch = Callable[[str], list[dict]]


def resolve_meta_page(
    brand: str, *, search: MetaPageSearch, accept_names: tuple[str, ...] = ()
) -> dict | None:
    """Brand → ``{page_id, name}`` via the page-search, or ``None``.

    Refuses to guess: returns only a candidate whose page **name** exactly equals ``brand`` or
    an ``accept_names`` entry. Never falls back to a dealer/look-alike (the Autotrader trap).
    """
    targets = {brand.strip().lower(), *(n.strip().lower() for n in accept_names if n)}
    for candidate in search(brand):
        if not candidate.get("page_id"):
            continue
        if (candidate.get("name") or "").strip().lower() in targets:
            return {"page_id": candidate["page_id"], "name": candidate.get("name")}
    return None


def meta_page_search(  # pragma: no cover - Playwright/network, best-effort
    brand: str, *, country: str = "US", headed: bool = False, wait_ms: int = 2500
) -> list[dict]:
    """Best-effort live page-search: ``[{page_id, name}]`` for matching advertiser pages.

    Scrapes the public Ad Library page-search DOM (React, not the Flutter canvas ATC uses).
    Selectors are best-effort and may need tuning when Meta reskins the page.
    """
    from playwright.sync_api import sync_playwright

    params = {
        "active_status": "all",
        "ad_type": "all",
        "country": country,
        "search_type": "page",
        "q": brand,
    }
    url = "https://www.facebook.com/ads/library/?" + urlencode(params)
    out: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(locale="en-US")
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _dismiss_common_dialogs(page)
            page.wait_for_timeout(wait_ms)
            raw = page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href*="view_all_page_id"]'))
                  .map((a) => {
                    const m = a.href.match(/view_all_page_id=(\\d+)/);
                    return { page_id: m ? m[1] : null,
                             name: (a.innerText || a.textContent || "").replace(/\\s+/g," ").trim() };
                  })
                  .filter((x) => x.page_id && x.name)
                """)
        except Exception:
            raw = []
        finally:
            context.close()
            browser.close()
    seen: set[str] = set()
    for entry in raw or []:
        pid = str(entry.get("page_id") or "")
        if pid and pid not in seen:
            seen.add(pid)
            out.append({"page_id": pid, "name": entry.get("name")})
    return out
