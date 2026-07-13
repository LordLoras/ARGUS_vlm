"""Google ATC creative projection and best-effort preview enrichment."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from ad_classifier.intelligence_crawler.diagnostics import classify_exception, safe_traceback
from ad_classifier.intelligence_crawler.google_atc_rpc import (
    PreviewFetch,
    parse_preview_artifacts,
)
from ad_classifier.intelligence_crawler.google_crawl_state import cached_preview_artifacts
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    PollDiagnostic,
    RawSourceItem,
)

PROVIDER = "google_atc"
_ADVERTISER_URL = "https://adstransparency.google.com/advertiser/{adv}?region=US"
_CREATIVE_URL = "https://adstransparency.google.com/advertiser/{adv}/creative/{cid}?region=US"

logger = structlog.get_logger(__name__)


def creative_to_item(source: IntelSource, advertiser_id: str, creative: dict) -> RawSourceItem:
    cid = creative["creative_id"]
    adv = creative.get("advertiser_id") or advertiser_id
    url = _CREATIVE_URL.format(adv=adv, cid=cid)
    raw_advertiser_name = creative.get("advertiser_name")
    advertiser_name = _display_advertiser_name(raw_advertiser_name, source.brand_name)
    # A dict means the preview was fetched even when no static artifacts were found.
    preview_fetched = isinstance(creative.get("preview_artifacts"), dict)
    preview_artifacts = creative.get("preview_artifacts")
    preview_artifacts = preview_artifacts if isinstance(preview_artifacts, dict) else {}
    inline_images = _list_artifact(creative, "image_sources")
    image_sources = _dedupe_str(
        [*inline_images, *_list_artifact(preview_artifacts, "image_sources")]
    )
    video_sources = _list_artifact(preview_artifacts, "video_sources")
    video_posters = _list_artifact(preview_artifacts, "video_posters")
    thumbnail_url = _first_present(video_posters, image_sources)
    dynamic_creative = (
        preview_fetched
        and bool(creative.get("preview_url"))
        and not image_sources
        and not video_sources
    )
    display_format = "rich_media" if dynamic_creative else creative.get("format")
    return RawSourceItem(
        external_id=cid,
        url=url,
        canonical_url=url,
        resource_type="atc_ad",
        title=f"{advertiser_name} ATC creative {cid}",
        description=_creative_description(creative.get("text")),
        published_at=_epoch_to_dt(creative.get("first_shown")),
        thumbnail_url=thumbnail_url,
        raw={
            "source": PROVIDER,
            "advertiser_id": adv,
            "advertiser_name": advertiser_name,
            "advertiser_name_raw": (
                raw_advertiser_name if raw_advertiser_name != advertiser_name else None
            ),
            "advertiser_url": _ADVERTISER_URL.format(adv=adv),
            "format_code": creative.get("format_code"),
            "format": display_format,
            "first_shown": creative.get("first_shown"),
            "last_shown": creative.get("last_shown"),
            "preview_url": creative.get("preview_url"),
            "inline_image_sources": inline_images,
            "creative_text": creative.get("text"),
            "region": "US",
            "has_inline_image": bool(inline_images),
            "dynamic_creative": dynamic_creative,
            "preview_enriched": preview_fetched,
            "youtube_video_ids": _list_artifact(preview_artifacts, "youtube_video_ids"),
            "image_sources": image_sources,
            "video_sources": video_sources,
            "video_posters": video_posters,
            "links": _links_artifact(preview_artifacts),
        },
    )


def enrich_preview_artifacts(
    creatives: list[dict],
    *,
    preview_fetch: PreviewFetch,
    limit: int,
    known_index: dict[str, dict] | None = None,
) -> tuple[list[dict], list[PollDiagnostic], int]:
    """Reuse known artifacts, fetch missing previews, and halt the burst on blocking/429."""
    enriched: list[dict] = []
    diagnostics: list[PollDiagnostic] = []
    fetched = 0
    provider_halted = False
    for creative in creatives:
        next_creative = dict(creative)
        preview_url = str(next_creative.get("preview_url") or "").strip()
        cached = cached_preview_artifacts(next_creative, known_index or {})
        if cached is not None:
            next_creative["preview_artifacts"] = cached
        elif preview_url and fetched < limit and not provider_halted:
            fetched += 1
            try:
                script = preview_fetch(preview_url)
                next_creative["preview_artifacts"] = parse_preview_artifacts(
                    script, preview_url=preview_url
                )
            except Exception as exc:
                diagnostic = classify_exception(exc, provider=PROVIDER, phase="preview_asset")
                logger.warning(
                    "google_preview_asset_failed",
                    creative_id=creative.get("creative_id"),
                    stage="google_atc.preview_asset",
                    category=diagnostic.category,
                    code=diagnostic.code,
                    traceback=safe_traceback(exc),
                )
                if diagnostic.category in {"rate_limited", "blocked", "authentication"}:
                    provider_halted = True
                    diagnostics.append(
                        diagnostic.model_copy(
                            update={
                                "message": (
                                    "Google preview enrichment stopped after provider failure "
                                    f"for creative {creative.get('creative_id')}."
                                )
                            }
                        )
                    )
                else:
                    diagnostics.append(
                        diagnostic.model_copy(
                            update={
                                "code": "google_preview_asset_fetch_failed",
                                "category": "asset_fetch",
                                "message": (
                                    "Google preview asset fetch failed for creative "
                                    f"{creative.get('creative_id')}."
                                ),
                                "details": {"cause_category": diagnostic.category},
                            }
                        )
                    )
        enriched.append(next_creative)
    return enriched, diagnostics, fetched


def latest_published(items: list[RawSourceItem]) -> str | None:
    dates = [item.published_at for item in items if item.published_at is not None]
    return max(dates).isoformat() if dates else None


def _epoch_to_dt(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _list_artifact(artifacts: dict, key: str) -> list[str]:
    values = artifacts.get(key)
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _links_artifact(artifacts: dict) -> list[dict[str, str]]:
    values = artifacts.get("links")
    if not isinstance(values, list):
        return []
    links: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        href = str(value.get("href") or "").strip()
        text = str(value.get("text") or "Link").strip()
        if href:
            links.append({"text": text, "href": href})
    return links


def _first_present(*groups: list[str]) -> str | None:
    for group in groups:
        if group:
            return group[0]
    return None


def _dedupe_str(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _creative_description(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    clean = " ".join(text.split()).strip()
    return clean[:600] or None


def _display_advertiser_name(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if not text or "\ufffd" in text:
        return fallback
    return text
