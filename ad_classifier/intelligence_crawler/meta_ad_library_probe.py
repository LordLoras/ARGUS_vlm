"""Experimental Meta Ad Library public-UI probe.

This is intentionally not a production source adapter. It opens a public Meta Ad
Library URL with Playwright, scrolls the page, finds visible ad cards that expose a
``Library ID``, and writes screenshots plus a JSON summary. Use it to evaluate whether
the UI has enough signal before promoting the logic into a real adapter.

Guardrails:
- public UI only, no login flow
- no ad clicks
- no hidden endpoint replay
- no writes to intelligence_crawler.db
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TOYOTA_META_AD_LIBRARY_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=US&is_targeted_country=false"
    "&media_type=all&search_type=page&sort_data[mode]=relevancy_monthly_grouped"
    "&sort_data[direction]=desc&view_all_page_id=197052454200"
)

_LIBRARY_ID_RE = re.compile(r"\bLibrary\s+ID[:\s]*([0-9]+)", re.IGNORECASE)
_STARTED_RE = re.compile(
    r"Started\s+running\s+on\s+(.+?)(?:\s+(?:Platforms|Active|Inactive|Library ID)\b|$)",
    re.IGNORECASE,
)
_PLATFORMS = ("Facebook", "Instagram", "Messenger", "Audience Network", "Threads")


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
            _wait_for_ad_library_content(page, timeout_ms=max(wait_ms * 8, 15000))
            seen_library_ids = set(_visible_library_ids(page))
            no_new_rounds = 0
            for _ in range(max(scrolls, 0)):
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(wait_ms)
                scrolls_completed += 1

                current_library_ids = set(_visible_library_ids(page))
                if len(current_library_ids) <= len(seen_library_ids):
                    no_new_rounds += 1
                else:
                    no_new_rounds = 0
                seen_library_ids = current_library_ids
                if (
                    stop_after_no_new > 0
                    and seen_library_ids
                    and no_new_rounds >= stop_after_no_new
                ):
                    stopped_after_no_new = True
                    break

            full_page_screenshot = out_dir / "meta_ad_library_full_page.png"
            page.screenshot(path=str(full_page_screenshot), full_page=True)
            raw_cards = _mark_candidate_cards(page, max_cards=max_cards)

            for raw in raw_cards:
                index = int(raw["index"])
                text = _collapse_whitespace(str(raw.get("text") or ""))
                parsed = _parse_card_text(text)
                platforms = _platforms_from_text(
                    " ".join([text, *[str(item) for item in raw.get("platform_labels") or []]])
                )
                screenshot_path = _screenshot_card(page, out_dir, index, parsed["library_id"])
                cards.append(
                    MetaProbeCard(
                        index=index,
                        library_id=parsed["library_id"],
                        status=parsed["status"],
                        started_running=parsed["started_running"],
                        platforms=platforms,
                        text_excerpt=text[:600],
                        text=text,
                        links=_clean_links(raw.get("links")),
                        image_sources=_clean_source_urls(raw.get("image_sources")),
                        video_sources=_clean_source_urls(raw.get("video_sources")),
                        video_posters=_clean_source_urls(raw.get("video_posters")),
                        background_image_sources=_clean_source_urls(
                            raw.get("background_image_sources")
                        ),
                        video_count=int(raw.get("video_count") or 0),
                        screenshot_path=str(screenshot_path) if screenshot_path else None,
                        rect=_clean_rect(raw.get("rect")),
                    )
                )
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


def _wait_for_ad_library_content(page: Any, *, timeout_ms: int) -> None:
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
    except Exception:
        return


def _mark_candidate_cards(page: Any, *, max_cards: int) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        (maxCards) => {
          const textOf = (el) => (el.innerText || el.textContent || "")
            .replace(/\\s+/g, " ")
            .trim();
          const rectOf = (el) => {
            const r = el.getBoundingClientRect();
            return {
              x: r.x + window.scrollX,
              y: r.y + window.scrollY,
              width: r.width,
              height: r.height
            };
          };
          const normalizeUrl = (value) => {
            if (!value) return "";
            try {
              return new URL(value, document.baseURI).toString();
            } catch {
              return String(value);
            }
          };
          const cssUrls = (value) =>
            Array.from(String(value || "").matchAll(/url\\(["']?([^"')]+)["']?\\)/g))
              .map((match) => normalizeUrl(match[1]))
              .filter(Boolean);
          const hasCardSignals = (text) =>
            /Library\\s+ID/i.test(text) &&
            /(Active|Inactive|Started running|Platforms)/i.test(text);
          const libraryIdCount = (text) =>
            (text.match(/Library\\s+ID/gi) || []).length;
          const leaves = Array.from(document.querySelectorAll("span, div"))
            .filter((el) => /Library\\s+ID/i.test(textOf(el)));
          const selected = [];
          const platformNames = ["Facebook", "Instagram", "Messenger", "Audience Network", "Threads"];

          for (const leaf of leaves) {
            let el = leaf;
            let best = null;
            for (let depth = 0; depth < 12 && el; depth += 1, el = el.parentElement) {
              const text = textOf(el);
              const rect = el.getBoundingClientRect();
              if (
                hasCardSignals(text) &&
                libraryIdCount(text) === 1 &&
                rect.width >= 280 &&
                rect.height >= 110 &&
                rect.height <= 1800
              ) {
                best = el;
              }
            }
            if (!best) continue;

            let duplicate = false;
            for (let i = selected.length - 1; i >= 0; i -= 1) {
              const existing = selected[i];
              if (existing === best || existing.contains(best)) {
                duplicate = true;
                break;
              }
              if (best.contains(existing)) {
                selected.splice(i, 1);
              }
            }
            if (!duplicate) selected.push(best);
            if (selected.length >= maxCards) break;
          }

          return selected.map((card, index) => {
            card.setAttribute("data-argus-meta-ad-card", String(index));
            const links = Array.from(card.querySelectorAll("a"))
              .map((a) => ({ text: textOf(a), href: a.href || "" }))
              .filter((a) => a.href || a.text);
            const imageSources = Array.from(card.querySelectorAll("img"))
              .map((img) => {
                const rect = img.getBoundingClientRect();
                return {
                  src: normalizeUrl(img.currentSrc || img.src || ""),
                  area: Math.max(
                    (img.naturalWidth || 0) * (img.naturalHeight || 0),
                    (img.width || 0) * (img.height || 0),
                    rect.width * rect.height
                  )
                };
              })
              .filter((item) => item.src)
              .sort((left, right) => right.area - left.area)
              .map((item) => item.src);
            const videos = Array.from(card.querySelectorAll("video"));
            const videoSources = videos
              .flatMap((video) => [
                video.currentSrc || "",
                video.src || "",
                ...Array.from(video.querySelectorAll("source")).map((source) => source.src || "")
              ])
              .map(normalizeUrl)
              .filter(Boolean);
            const videoPosters = videos
              .map((video) => video.poster || "")
              .map(normalizeUrl)
              .filter(Boolean);
            const backgroundImageSources = Array.from(card.querySelectorAll("*"))
              .flatMap((el) => cssUrls(window.getComputedStyle(el).backgroundImage));
            const platformLabels = Array.from(card.querySelectorAll("[aria-label], [title], img[alt]"))
              .flatMap((el) => [el.getAttribute("aria-label"), el.getAttribute("title"), el.getAttribute("alt")])
              .filter(Boolean)
              .filter((value) => platformNames.some((name) => value.toLowerCase().includes(name.toLowerCase())));
            return {
              index,
              text: textOf(card),
              links,
              image_sources: imageSources,
              video_sources: videoSources,
              video_posters: videoPosters,
              background_image_sources: backgroundImageSources,
              platform_labels: platformLabels,
              video_count: videos.length,
              rect: rectOf(card)
            };
          });
        }
        """,
        max_cards,
    )


def _visible_library_ids(page: Any) -> list[str]:
    return page.evaluate(
        """
        () => Array.from(document.body.innerText.matchAll(/Library\\s+ID[:\\s]*([0-9]+)/gi))
          .map((match) => match[1])
        """
    )


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


def _parse_card_text(text: str) -> dict[str, Any]:
    compact = _collapse_whitespace(text)
    library_match = _LIBRARY_ID_RE.search(compact)
    started_match = _STARTED_RE.search(compact)
    status = None
    if re.search(r"\bActive\b", compact, re.IGNORECASE):
        status = "active"
    elif re.search(r"\bInactive\b", compact, re.IGNORECASE):
        status = "inactive"
    platforms = [platform for platform in _PLATFORMS if platform.lower() in compact.lower()]
    return {
        "library_id": library_match.group(1) if library_match else None,
        "status": status,
        "started_running": started_match.group(1).strip() if started_match else None,
        "platforms": platforms,
    }


def _platforms_from_text(value: str) -> list[str]:
    compact = value.lower()
    return [platform for platform in _PLATFORMS if platform.lower() in compact]


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return clean[:80] or "unknown"


def _clean_links(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    links: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = _collapse_whitespace(str(item.get("text") or ""))
        href = str(item.get("href") or "")
        if not text and not href:
            continue
        key = (text, href)
        if key in seen:
            continue
        seen.add(key)
        links.append({"text": text, "href": href})
    return links[:20]


def _clean_image_sources(raw: Any) -> list[str]:
    return _clean_source_urls(raw)


def _clean_source_urls(raw: Any) -> list[str]:
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


def _clean_rect(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    rect: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        try:
            rect[key] = float(raw.get(key))
        except (TypeError, ValueError):
            continue
    return rect
