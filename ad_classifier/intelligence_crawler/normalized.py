"""Provider-agnostic ad creative normalization for crawler resource API views."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from ad_classifier.intelligence_crawler.models import (
    IntelCollectionContext,
    IntelCreativeAsset,
    IntelCreativeVariant,
    IntelDeliveryRegion,
    IntelDeliverySummary,
    IntelDeliverySurface,
    IntelImpressionRange,
    IntelNormalizedAdvertiser,
    IntelNormalizedCreative,
    IntelNormalizedResource,
    IntelResourceArtifact,
    IntelTargetingSummary,
)
from ad_classifier.intelligence_crawler.timeutils import as_utc, parse_iso

PROVIDER_ALIASES = {
    "google_atc": "google_ads_transparency",
    "google_ads_transparency": "google_ads_transparency",
    "meta_ad_library_ui": "meta_ad_library",
    "meta_ad_library": "meta_ad_library",
}


def build_normalized_resource(
    *,
    source_type: str,
    brand_name: str,
    resource_type: str,
    url: str | None,
    platform: str | None,
    platform_id: str | None,
    title: str | None,
    description: str | None,
    published_at: datetime | None,
    fetched_at: datetime,
    variant_count: int | None,
    has_variants: bool,
    metadata: dict,
    artifacts: list[IntelResourceArtifact],
) -> IntelNormalizedResource:
    """Return the stable cross-provider resource contract used by the API."""

    provider = _provider(source_type, metadata)
    source_url = _first_str(metadata, "source_url", "startUrl", "start_url") or url
    delivery = _delivery_summary(metadata)
    requested_region = _first_str(
        metadata, "requested_region", "requestedRegion", "region"
    ) or _region_from_url(source_url)
    advertiser_name = _first_str(metadata, "advertiser_name", "advertiserName") or brand_name
    creative_id = _first_str(metadata, "creativeId", "creative_id", "library_id") or platform_id
    normalized_format = _creative_format(resource_type, metadata, artifacts)
    default_landing_url, default_cta = _first_link(metadata)

    return IntelNormalizedResource(
        provider=provider,
        adapter=source_type,
        platform=platform,
        source_url=source_url,
        fetched_at=fetched_at,
        advertiser=IntelNormalizedAdvertiser(
            id=_first_str(metadata, "advertiserId", "advertiser_id"),
            name=advertiser_name,
            url=_first_str(metadata, "advertiser_url", "advertiserUrl"),
        ),
        creative=IntelNormalizedCreative(
            id=creative_id,
            library_url=_first_str(metadata, "adLibraryUrl", "ad_library_url") or url,
            format=normalized_format,
            status=_first_str(metadata, "status"),
            title=title,
            description=description,
            first_shown_at=(
                _first_datetime(metadata, "firstShown", "first_shown", "started_running")
                or published_at
            ),
            last_shown_at=_first_datetime(metadata, "lastShown", "last_shown"),
            served_days=_first_int(metadata, "numServedDays", "num_served_days", "served_days"),
            variant_count=variant_count,
            has_variants=has_variants,
        ),
        variants=_variants(
            metadata=metadata,
            row_description=description,
            default_landing_url=default_landing_url,
            default_cta=default_cta,
            artifacts=artifacts,
        ),
        delivery=delivery,
        targeting=IntelTargetingSummary(raw=_targeting(metadata)),
        collection=IntelCollectionContext(
            requested_region_code=requested_region,
            collector_region_code=_first_str(
                metadata, "collector_region", "collectorRegion", "vm_region"
            ),
            collector_id=_first_str(metadata, "collector_id", "collectorId"),
            source_url=source_url,
        ),
    )


def _provider(source_type: str, metadata: dict) -> str:
    raw = _first_str(metadata, "source") or source_type
    return PROVIDER_ALIASES.get(raw, PROVIDER_ALIASES.get(source_type, raw))


def _creative_format(
    resource_type: str, metadata: dict, artifacts: list[IntelResourceArtifact]
) -> str | None:
    if bool(metadata.get("dynamic_creative")):
        return "rich_media"
    raw = _first_str(metadata, "format", "formatCode", "format_code")
    if raw:
        return raw.strip().lower()
    if any(item.artifact_type == "video_url" for item in artifacts):
        return "video"
    if any(
        item.artifact_type in {"image_url", "background_image", "card_screenshot"}
        for item in artifacts
    ):
        return "image"
    return resource_type or None


def _variants(
    *,
    metadata: dict,
    row_description: str | None,
    default_landing_url: str | None,
    default_cta: str | None,
    artifacts: list[IntelResourceArtifact],
) -> list[IntelCreativeVariant]:
    raw_variants = _raw_list_any(metadata, "variations", "variants", "creative_variants")
    variants: list[IntelCreativeVariant] = []
    for index, item in enumerate(raw_variants, start=1):
        if not isinstance(item, dict):
            continue
        landing_url = _first_str(item, "clickUrl", "click_url", "landing_url", "landingUrl")
        variants.append(
            IntelCreativeVariant(
                id=_first_str(item, "id", "creativeId", "creative_id"),
                label=f"Variant {index}",
                description=_first_str(item, "description", "text", "body", "headline"),
                cta=_first_str(item, "cta", "call_to_action", "callToAction"),
                landing_url=landing_url,
                assets=_dedupe_assets(_variant_assets(item, landing_url=landing_url)),
            )
        )
    if variants:
        return variants

    assets = _dedupe_assets([_asset_from_artifact(item) for item in artifacts])
    if row_description or default_landing_url or default_cta or assets:
        return [
            IntelCreativeVariant(
                id=None,
                label="Default creative",
                description=row_description,
                cta=default_cta,
                landing_url=default_landing_url,
                assets=assets,
            )
        ]
    return []


def _variant_assets(item: dict, *, landing_url: str | None) -> list[IntelCreativeAsset]:
    assets: list[IntelCreativeAsset] = []
    for key in ("imageUrl", "image_url", "previewUrl", "preview_url"):
        url = _clean_str(item.get(key))
        if url:
            assets.append(
                IntelCreativeAsset(asset_type="image", role="creative", url=url, source="provider")
            )
    for key in ("videoUrl", "video_url"):
        url = _clean_str(item.get(key))
        if url:
            assets.append(
                IntelCreativeAsset(asset_type="video", role="creative", url=url, source="provider")
            )
    if landing_url:
        assets.append(
            IntelCreativeAsset(
                asset_type="landing_page", role="clickout", url=landing_url, source="provider"
            )
        )
    return assets


def _asset_from_artifact(artifact: IntelResourceArtifact) -> IntelCreativeAsset:
    if artifact.artifact_type == "card_screenshot":
        return IntelCreativeAsset(
            asset_type="image",
            role="screenshot",
            path=artifact.path,
            text=artifact.text,
            source="crawler",
        )
    if artifact.artifact_type == "image_url":
        return IntelCreativeAsset(
            asset_type="image",
            role="creative",
            url=artifact.url,
            text=artifact.text,
            source="provider",
        )
    if artifact.artifact_type == "video_url":
        return IntelCreativeAsset(
            asset_type="video",
            role="creative",
            url=artifact.url,
            text=artifact.text,
            source="provider",
        )
    if artifact.artifact_type == "video_poster":
        return IntelCreativeAsset(
            asset_type="image",
            role="video_poster",
            url=artifact.url,
            text=artifact.text,
            source="provider",
        )
    if artifact.artifact_type == "background_image":
        return IntelCreativeAsset(
            asset_type="image",
            role="background",
            url=artifact.url,
            text=artifact.text,
            source="provider",
        )
    if artifact.artifact_type == "link":
        return IntelCreativeAsset(
            asset_type="landing_page",
            role="clickout",
            url=artifact.url,
            text=artifact.text,
            source="provider",
        )
    return IntelCreativeAsset(
        asset_type=artifact.artifact_type,
        role="supporting",
        url=artifact.url,
        path=artifact.path,
        text=artifact.text,
        source="provider",
    )


def _delivery_summary(metadata: dict) -> IntelDeliverySummary:
    regions: list[IntelDeliveryRegion] = []
    for item in _raw_list_any(metadata, "regionStats", "region_stats"):
        if not isinstance(item, dict):
            continue
        regions.append(
            IntelDeliveryRegion(
                region_code=_first_str(item, "regionCode", "region_code"),
                region_name=_first_str(item, "regionName", "region_name"),
                first_shown_at=_first_datetime(item, "firstShown", "first_shown"),
                last_shown_at=_first_datetime(item, "lastShown", "last_shown"),
                impressions=_impressions(item.get("impressions")),
                surfaces=_surfaces(item),
            )
        )
    return IntelDeliverySummary(regions=regions)


def _surfaces(item: dict) -> list[IntelDeliverySurface]:
    surfaces: list[IntelDeliverySurface] = []
    for surface in _raw_list_any(item, "surfaceServingStats", "surface_serving_stats"):
        if not isinstance(surface, dict):
            continue
        surfaces.append(
            IntelDeliverySurface(
                surface_code=_first_str(surface, "surfaceCode", "surface_code"),
                surface_name=_first_str(surface, "surfaceName", "surface_name"),
                impressions=_impressions(surface.get("impressions")),
            )
        )
    return surfaces


def _impressions(value: object) -> IntelImpressionRange | None:
    if not isinstance(value, dict):
        return None
    lower = _first_int(value, "lowerBound", "lower_bound")
    upper = _first_int(value, "upperBound", "upper_bound")
    if lower is None and upper is None:
        return None
    return IntelImpressionRange(lower_bound=lower, upper_bound=upper)


def _targeting(metadata: dict) -> dict:
    targeting = _first_dict(metadata, "targeting")
    if targeting:
        return targeting
    targeting_category = _first_dict(metadata, "targetingCategory", "targeting_category")
    return {"targetingCategory": targeting_category} if targeting_category else {}


def _first_link(metadata: dict) -> tuple[str | None, str | None]:
    for item in _raw_list_any(metadata, "links"):
        if isinstance(item, dict):
            href = _clean_str(item.get("href") or item.get("url"))
            text = _clean_str(item.get("text") or item.get("label") or item.get("cta"))
            if href or text:
                return href, text
        else:
            href = _clean_str(item)
            if href:
                return href, None
    return None, None


def _dedupe_assets(assets: list[IntelCreativeAsset]) -> list[IntelCreativeAsset]:
    deduped: list[IntelCreativeAsset] = []
    seen: set[tuple[str | None, str | None, str | None, str]] = set()
    for asset in assets:
        key = (asset.url, asset.path, asset.text, asset.role)
        if key not in seen:
            seen.add(key)
            deduped.append(asset)
    return deduped


def _first_str(data: dict, *keys: str) -> str | None:
    for key in keys:
        value = _clean_str(data.get(key))
        if value:
            return value
    return None


def _first_dict(data: dict, *keys: str) -> dict:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first_int(data: dict, *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                continue
    return None


def _first_datetime(data: dict, *keys: str) -> datetime | None:
    for key in keys:
        dt = _datetime_from_any(data.get(key))
        if dt is not None:
            return dt
    return None


def _datetime_from_any(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            raw = float(value)
            if raw > 10_000_000_000:
                raw /= 1000
            return datetime.fromtimestamp(raw, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    text = _clean_str(value)
    if not text:
        return None
    try:
        return parse_iso(text)
    except ValueError:
        return None


def _raw_list_any(data: dict, *keys: str) -> list:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _region_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("region", "regionCode", "region_code"):
        values = query.get(key)
        if values:
            return _clean_str(values[0])
    match = re.search(r"region=([A-Za-z0-9_-]+)", url)
    if match:
        return _clean_str(match.group(1))
    return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
