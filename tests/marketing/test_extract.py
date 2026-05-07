from __future__ import annotations

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.marketing.commercial import merge_commercial_entities
from ad_classifier.marketing.extract import (
    enrich_marketing_entities,
    extract_tracking_entities,
    merge_tracking_entities,
)
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import DisclaimerEntity, MarketingEntities, OfferEntity
from ad_classifier.pipeline.ocr.models import OCRItem


def test_extract_tracking_entities_from_ocr_and_transcript():
    extracted = extract_tracking_entities(
        ocr_items=[
            OCRItem(
                frame_index=2,
                time_ms=1000,
                text="Visit prillamanhvac.com or call (540) 555-1212. Use code SAVE20.",
                confidence=0.9,
                engine="test",
            )
        ],
        transcript=WhisperTranscript(
            segments=[
                TranscriptSegment(
                    start_ms=1500,
                    end_ms=2500,
                    text="Limited time offer, call today.",
                )
            ]
        ),
    )

    assert extracted.contact_points.websites[0].domain == "prillamanhvac.com"
    assert extracted.contact_points.phone_numbers[0].normalized == "+15405551212"
    assert extracted.offer_terms.promo_codes[0].code == "SAVE20"
    assert "limited time" in extracted.offer_terms.urgency_signals
    assert extracted.landing_page.domain == "prillamanhvac.com"


def test_merge_tracking_entities_adds_missing_values_without_duplicates():
    base = MarketingEntities()
    extracted = extract_tracking_entities(
        ocr_items=[
            OCRItem(
                frame_index=0,
                time_ms=0,
                text="example.com example.com",
                engine="test",
            )
        ],
        transcript=WhisperTranscript(),
    )

    merged = merge_tracking_entities(base, extracted)
    merged = merge_tracking_entities(merged, extracted)

    assert len(merged.contact_points.websites) == 1
    assert merged.landing_page.domain == "example.com"


def test_extract_tracking_entities_ignores_low_confidence_ocr_domains():
    extracted = extract_tracking_entities(
        ocr_items=[
            OCRItem(
                frame_index=0,
                time_ms=0,
                text="garbled.example",
                confidence=0.4,
                engine="test",
            )
        ],
        transcript=WhisperTranscript(),
    )

    assert extracted.contact_points.websites == []


def test_merge_tracking_entities_skips_weaker_suffix_domain():
    base = MarketingEntities()
    base.contact_points.websites.append(
        extract_tracking_entities(
            ocr_items=[],
            transcript=WhisperTranscript(
                segments=[
                    TranscriptSegment(
                        start_ms=0,
                        end_ms=100,
                        text="Visit prillamanhvac.com.",
                    )
                ]
            ),
        ).contact_points.websites[0]
    )
    extracted = extract_tracking_entities(
        ocr_items=[],
        transcript=WhisperTranscript(
            segments=[TranscriptSegment(start_ms=100, end_ms=200, text="Prillaman HVAC.com")]
        ),
    )

    merged = merge_tracking_entities(base, extracted)

    assert [item.domain for item in merged.contact_points.websites] == ["prillamanhvac.com"]


def test_extract_commercial_terms_from_joined_ocr_frame():
    extracted = extract_tracking_entities(
        ocr_items=[
            OCRItem(frame_index=4, time_ms=2000, text="0%", confidence=0.98, engine="test"),
            OCRItem(frame_index=4, time_ms=2000, text="FINANCING", confidence=0.98, engine="test"),
            OCRItem(frame_index=4, time_ms=2000, text="FOR", confidence=0.98, engine="test"),
            OCRItem(frame_index=4, time_ms=2000, text="60", confidence=0.98, engine="test"),
            OCRItem(frame_index=4, time_ms=2000, text="MONTHS", confidence=0.98, engine="test"),
            OCRItem(frame_index=4, time_ms=2000, text="ONSELECT", confidence=0.98, engine="test"),
            OCRItem(frame_index=4, time_ms=2000, text="2025", confidence=0.98, engine="test"),
            OCRItem(
                frame_index=4,
                time_ms=2000,
                text="GRAND CHEROKEE AND GLADIATOR MODELS",
                confidence=0.98,
                engine="test",
            ),
        ],
        transcript=WhisperTranscript(),
    )

    assert extracted.offer_terms.financing.apr == 0.0
    assert extracted.offer_terms.financing.duration_months == 60
    assert any("0% FINANCING FOR 60 MONTHS" in offer.text for offer in extracted.offers)


def test_extract_price_context_prefers_joined_ocr_frame():
    extracted = extract_tracking_entities(
        ocr_items=[
            OCRItem(
                frame_index=7,
                time_ms=3500,
                text="2026 JEEP WRANGLER",
                confidence=0.98,
                engine="test",
            ),
            OCRItem(frame_index=7, time_ms=3500, text="LEASE FOR:", confidence=0.98, engine="test"),
            OCRItem(frame_index=7, time_ms=3500, text="$400", confidence=0.98, engine="test"),
            OCRItem(frame_index=7, time_ms=3500, text="/MO", confidence=0.98, engine="test"),
            OCRItem(frame_index=7, time_ms=3500, text="LEASE", confidence=0.98, engine="test"),
            OCRItem(frame_index=7, time_ms=3500, text="36MOS", confidence=0.98, engine="test"),
            OCRItem(frame_index=7, time_ms=3500, text="$0", confidence=0.98, engine="test"),
            OCRItem(frame_index=7, time_ms=3500, text="DUEAT", confidence=0.98, engine="test"),
            OCRItem(frame_index=7, time_ms=3500, text="SIGNING", confidence=0.98, engine="test"),
        ],
        transcript=WhisperTranscript(),
    )

    prices = {price.text: price for price in extracted.prices}
    assert set(prices) == {"$400", "$0"}
    assert "36 MOS" in prices["$400"].evidence[0].text
    assert "DUE AT SIGNING" in prices["$0"].evidence[0].text


def test_exact_disclaimers_ignore_plain_sales_tax_copy():
    extracted = extract_tracking_entities(
        ocr_items=[
            OCRItem(
                frame_index=8,
                time_ms=4000,
                text="WE'LL COVER YOUR SALES TAX ON SELECT GRAND CHEROKEE MODELS",
                confidence=0.98,
                engine="test",
            )
        ],
        transcript=WhisperTranscript(),
    )

    assert extracted.disclaimers == []


def test_enrich_marketing_entities_dedupes_generic_financing_offer():
    base = MarketingEntities()
    base.offers = [OfferEntity(text="0% financing")]

    enriched = enrich_marketing_entities(
        base,
        ocr_items=[
            OCRItem(
                frame_index=4,
                time_ms=2000,
                text="0% APR financing for 60 months on select models",
                confidence=0.98,
                engine="test",
            )
        ],
        transcript=WhisperTranscript(),
    )

    assert [offer.text for offer in enriched.offers] == [
        "0% APR financing for 60 months on select models"
    ]


def test_merge_disclaimers_prefers_clean_vlm_text_over_ocr_context():
    base = MarketingEntities()
    base.disclaimers = [
        DisclaimerEntity(
            text=(
                "Offers exclude 4xe models. 0% APR financing for 60 months equals "
                "$16.67 per month per $1,000 financed for well-qualified buyers."
            ),
            evidence=[EvidenceItem(time_ms=1000, source="vlm", text="clean")],
        )
    ]
    extracted = MarketingEntities()
    extracted.disclaimers = [
        DisclaimerEntity(
            text=(
                "...YOUR SALES TAX Offers exclude 4xe models.0% APR financing for 60 months "
                "equals$16.67 per month per$1,000 financed for well-qualified buyers "
                "regardless of down payment garbled copy..."
            ),
            evidence=[EvidenceItem(time_ms=1500, source="ocr", text="garbled")],
        )
    ]

    merged = merge_commercial_entities(base, extracted)

    assert len(merged.disclaimers) == 1
    assert merged.disclaimers[0].evidence[0].source == "vlm"


def test_enrich_marketing_entities_repairs_product_noise_and_adds_offer_price():
    base = MarketingEntities()
    base.brand.name = "Jeep"
    base.products = [
        "2025 Grand Cherokee",
        "20MT66 Jeep Grand Cherokee Limited 4x4",
        "2026 Jeep Wrangler 4-Door Sport S",
    ]

    enriched = enrich_marketing_entities(
        base,
        ocr_items=[
            OCRItem(
                frame_index=8,
                time_ms=4000,
                text="$4,500 TOTAL BONUS CASH ALLOWANCE FOR CURRENT FCA OWNERS OR LESSEES",
                confidence=0.94,
                engine="test",
            )
        ],
        transcript=WhisperTranscript(),
    )

    assert "20MT66" not in ", ".join(enriched.products)
    assert "Grand Cherokee Limited 4x4" in enriched.products
    assert "2026 Wrangler 4-Door Sport S" in enriched.products
    assert enriched.prices[0].amount == 4500
    assert any("BONUS CASH ALLOWANCE" in offer.text for offer in enriched.offers)


def test_extract_disclaimer_density_without_exact_low_confidence_text():
    extracted = extract_tracking_entities(
        ocr_items=[
            OCRItem(
                frame_index=9,
                time_ms=4500,
                text=(
                    "Offers exclude 4xe models. Not all buyers will qualify. "
                    "Tax title license and dealer installed equipment extra. "
                    "MSRP excludes warranties and services. See dealer for terms and conditions."
                ),
                confidence=0.42,
                engine="test",
            )
        ],
        transcript=WhisperTranscript(),
    )

    assert extracted.creative_attributes.disclaimer_density in {"medium", "high"}
    assert extracted.disclaimers == []
