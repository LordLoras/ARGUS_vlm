from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.models import IntelResourceArtifact
from ad_classifier.intelligence_crawler.normalized import build_normalized_resource

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)


def test_google_ad_transparency_payload_normalizes_to_cross_provider_shape():
    metadata = {
        "adLibraryUrl": (
            "https://adstransparency.google.com/advertiser/"
            "AR08888592736429539329/creative/CR08436770543486631937"
        ),
        "advertiserId": "AR08888592736429539329",
        "advertiserName": "Niantic, Inc.",
        "creativeId": "CR08436770543486631937",
        "firstShown": "2023-07-04",
        "format": "IMAGE",
        "lastShown": "2024-05-17",
        "numServedDays": 191,
        "previewUrl": "https://tpc.googlesyndication.com/archive/simgad/12683072185372151324",
        "regionStats": [
            {
                "regionCode": "DE",
                "regionName": "Germany",
                "firstShown": "2023-07-04",
                "lastShown": "2024-05-17",
                "impressions": {"lowerBound": 1000, "upperBound": 2000},
                "surfaceServingStats": [
                    {
                        "surfaceCode": "YOUTUBE",
                        "surfaceName": "YouTube",
                        "impressions": {"lowerBound": 1000, "upperBound": 2000},
                    },
                    {
                        "surfaceCode": "SEARCH",
                        "surfaceName": "Google Search",
                        "impressions": {"lowerBound": 0, "upperBound": 1000},
                    },
                ],
            }
        ],
        "startUrl": (
            "https://adstransparency.google.com/advertiser/" "AR08888592736429539329region=DE"
        ),
        "targeting": {"targetingCategory": {"demographics": {"1": True, "2": False}}},
        "variations": [
            {
                "clickUrl": "https://play.google.com/store/apps/details?id=com.example",
                "cta": "INSTALL",
                "description": "Catch Pokemon and battle with friends",
                "imageUrl": "https://tpc.googlesyndication.com/simgad/16977068568541754968",
            }
        ],
    }

    normalized = build_normalized_resource(
        source_type="google_atc",
        brand_name="Niantic",
        resource_type="atc_ad",
        url=metadata["adLibraryUrl"],
        platform=None,
        platform_id="CR08436770543486631937",
        title="Niantic ATC creative CR08436770543486631937",
        description="Catch Pokemon and battle with friends",
        published_at=None,
        fetched_at=NOW,
        variant_count=None,
        has_variants=False,
        metadata=metadata,
        artifacts=[],
    )

    assert normalized.provider == "google_ads_transparency"
    assert normalized.adapter == "google_atc"
    assert normalized.advertiser.id == "AR08888592736429539329"
    assert normalized.advertiser.name == "Niantic, Inc."
    assert normalized.creative.id == "CR08436770543486631937"
    assert normalized.creative.format == "image"
    assert normalized.creative.served_days == 191
    assert normalized.collection.requested_region_code == "DE"
    assert normalized.targeting.raw["targetingCategory"]["demographics"]["1"] is True

    variant = normalized.variants[0]
    assert variant.cta == "INSTALL"
    assert variant.landing_url == "https://play.google.com/store/apps/details?id=com.example"
    assert variant.assets[0].asset_type == "image"

    region = normalized.delivery.regions[0]
    assert region.region_code == "DE"
    assert region.region_name == "Germany"
    assert region.impressions is not None
    assert region.impressions.lower_bound == 1000
    assert [surface.surface_code for surface in region.surfaces] == ["YOUTUBE", "SEARCH"]


def test_meta_ui_metadata_normalizes_default_variant_and_artifacts():
    metadata = {
        "source": "meta_ad_library_ui",
        "source_url": "https://www.facebook.com/ads/library/?active_status=all&id=123",
        "library_id": "123",
        "status": "Active",
        "started_running": "Jun 10, 2026",
        "platforms": ["Facebook", "Instagram"],
        "links": [{"text": "Shop now", "href": "https://example.com/landing"}],
        "image_sources": ["https://cdn.example/image.jpg"],
        "video_sources": ["https://cdn.example/video.mp4"],
        "screenshot_path": "C:/tmp/meta_123.png",
    }
    artifacts = [
        IntelResourceArtifact(
            artifact_type="card_screenshot", label="Card screenshot", path="C:/tmp/meta_123.png"
        ),
        IntelResourceArtifact(
            artifact_type="image_url", label="Image", url="https://cdn.example/image.jpg"
        ),
        IntelResourceArtifact(
            artifact_type="video_url", label="Video", url="https://cdn.example/video.mp4"
        ),
        IntelResourceArtifact(
            artifact_type="link",
            label="Shop now",
            url="https://example.com/landing",
            text="Shop now",
        ),
    ]

    normalized = build_normalized_resource(
        source_type="meta_ad_library_ui",
        brand_name="Toyota",
        resource_type="meta_ad",
        url="https://www.facebook.com/ads/library/?id=123",
        platform="meta",
        platform_id="123",
        title="Toyota Meta ad 123",
        description="Camry launch creative",
        published_at=NOW,
        fetched_at=NOW,
        variant_count=2,
        has_variants=True,
        metadata=metadata,
        artifacts=artifacts,
    )

    assert normalized.provider == "meta_ad_library"
    assert normalized.platform == "meta"
    assert normalized.advertiser.name == "Toyota"
    assert normalized.creative.id == "123"
    assert normalized.creative.format == "video"
    assert normalized.creative.status == "Active"
    assert normalized.creative.variant_count == 2
    assert normalized.creative.has_variants is True

    variant = normalized.variants[0]
    assert variant.label == "Default creative"
    assert variant.cta == "Shop now"
    assert variant.landing_url == "https://example.com/landing"
    assert {(asset.asset_type, asset.role) for asset in variant.assets} >= {
        ("image", "screenshot"),
        ("image", "creative"),
        ("video", "creative"),
        ("landing_page", "clickout"),
    }
