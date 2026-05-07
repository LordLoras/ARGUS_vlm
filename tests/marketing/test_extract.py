from __future__ import annotations

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.marketing.extract import extract_tracking_entities, merge_tracking_entities
from ad_classifier.models.marketing import MarketingEntities
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
