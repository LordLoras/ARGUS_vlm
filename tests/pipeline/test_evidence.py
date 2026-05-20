from __future__ import annotations

from pathlib import Path

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.pipeline.evidence import build_evidence_bundle
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from ad_classifier.pipeline.rules.models import RuleTrigger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fa(frame_index: int, time_ms: int, path: Path | None = None) -> FrameAnalysis:
    return FrameAnalysis(
        frame_index=frame_index,
        time_ms=time_ms,
        path=path or Path(f"/tmp/frame_{frame_index}.png"),
        phash="0000000000000000",
        blur_score=500.0,
        blank_std=80.0,
        kept=True,
    )


def _ocr(frame_index: int, text: str, bbox: list[float] | None = None) -> OCRItem:
    return OCRItem(
        frame_index=frame_index,
        time_ms=frame_index * 500,
        text=text,
        bbox=bbox,
        engine="mock",
    )


def _transcript(*segments: tuple[int, int, str]) -> WhisperTranscript:
    segs = [TranscriptSegment(start_ms=s, end_ms=e, text=t) for s, e, t in segments]
    return WhisperTranscript(segments=segs, text=" ".join(t for _, _, t in segments))


def _trigger(frame_index: int, severity: str = "high") -> RuleTrigger:
    return RuleTrigger(
        rule_id="test_rule",
        evidence_text="no credit check",
        source="ocr",
        frame_index=frame_index,
        time_ms=frame_index * 500,
        severity=severity,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Basic bundle building
# ---------------------------------------------------------------------------


def test_build_empty_kept_frames():
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=[],
        transcript=_transcript(),
        rules_triggered=[],
    )
    assert bundle.frame_summaries == []
    assert bundle.frame_image_paths == []


def test_build_with_fewer_frames_than_budget():
    frames = [_fa(i, i * 500) for i in range(5)]
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        max_frames=12,
    )
    assert len(bundle.frame_summaries) == 5


def test_build_attaches_ocr_to_frame():
    frames = [_fa(0, 0), _fa(1, 500)]
    ocr = {0: [_ocr(0, "SALE 50% OFF")], 1: [_ocr(1, "Shop now")]}
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        ocr_by_frame=ocr,
        max_frames=12,
    )
    assert bundle.frame_summaries[0].ocr_items[0].text == "SALE 50% OFF"
    assert bundle.frame_summaries[1].ocr_items[0].text == "Shop now"


def test_build_splits_fine_print_from_main_ocr():
    frames = [_fa(0, 0)]
    fine_bbox = [10, 430, 610, 430, 610, 442, 10, 442]
    ocr = {
        0: [
            _ocr(0, "0% APR FINANCING", bbox=[180, 250, 460, 250, 460, 290, 180, 290]),
            _ocr(
                0,
                "Offer excludes leases and not all buyers will qualify. See dealer for details.",
                bbox=fine_bbox,
            ),
        ]
    }

    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        ocr_by_frame=ocr,
        max_frames=12,
    )

    assert [item.text for item in bundle.frame_summaries[0].ocr_items] == ["0% APR FINANCING"]
    assert bundle.frame_summaries[0].fine_print_ocr_items[0].text.startswith("Offer excludes")


def test_build_separates_broadcast_overlay_from_main_ocr(tmp_path):
    from PIL import Image

    path = tmp_path / "frame.png"
    Image.new("RGB", (640, 480), "black").save(path)
    frames = [_fa(0, 0, path)]
    ocr = {
        0: [
            _ocr(0, "FLASH FLOOD WARNING", bbox=[25, 84, 99, 84, 99, 95, 25, 95]),
            _ocr(0, "Austin Area", bbox=[113, 30, 171, 30, 171, 41, 113, 41]),
            _ocr(0, "Volvo", bbox=[138, 40, 161, 40, 161, 47, 138, 47]),
            _ocr(0, "SEIZE THE AWKWARD", bbox=[244, 157, 396, 157, 396, 181, 244, 181]),
        ]
    }

    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        ocr_by_frame=ocr,
        max_frames=12,
    )

    summary = bundle.frame_summaries[0]
    assert [item.text for item in summary.ocr_items] == ["SEIZE THE AWKWARD"]
    assert {item.text for item in summary.broadcast_overlay_ocr_items} == {
        "FLASH FLOOD WARNING",
        "Austin Area",
        "Volvo",
    }


def test_build_keeps_small_nonlegal_dealer_text_as_main_ocr():
    frames = [_fa(0, 0)]
    ocr = {
        0: [
            _ocr(
                0,
                "Kelly GMC Jeep",
                bbox=[220, 432, 420, 432, 420, 444, 220, 444],
            )
        ]
    }

    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        ocr_by_frame=ocr,
        max_frames=12,
    )

    assert [item.text for item in bundle.frame_summaries[0].ocr_items] == ["Kelly GMC Jeep"]
    assert bundle.frame_summaries[0].fine_print_ocr_items == []


def test_build_keeps_top_left_logo_without_broadcast_context(tmp_path):
    from PIL import Image

    path = tmp_path / "frame.png"
    Image.new("RGB", (640, 480), "black").save(path)
    frames = [_fa(0, 0, path)]
    ocr = {
        0: [
            _ocr(0, "Kelly GMC Jeep", bbox=[24, 30, 150, 30, 150, 48, 24, 48]),
            _ocr(0, "Shop now", bbox=[250, 230, 390, 230, 390, 260, 250, 260]),
        ]
    }

    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        ocr_by_frame=ocr,
        max_frames=12,
    )

    summary = bundle.frame_summaries[0]
    assert [item.text for item in summary.ocr_items] == ["Kelly GMC Jeep", "Shop now"]
    assert summary.broadcast_overlay_ocr_items == []


def test_build_attaches_nearby_transcript():
    frames = [_fa(0, 0), _fa(1, 2000)]
    t = _transcript((0, 1500, "intro"), (3000, 5000, "outro"))
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=t,
        rules_triggered=[],
        alignment_window_ms=1000,
        max_frames=12,
    )
    assert any(s.text == "intro" for s in bundle.frame_summaries[0].transcript_nearby)
    # frame at 2000ms, window 1000 → [1000, 3000]; "outro" starts at 3000 (boundary included)
    outro_found = any(s.text == "outro" for s in bundle.frame_summaries[1].transcript_nearby)
    assert outro_found


# ---------------------------------------------------------------------------
# H.1 Frame selection with budget
# ---------------------------------------------------------------------------


def _make_30_frames() -> list[FrameAnalysis]:
    return [_fa(i, i * 1000) for i in range(30)]


def test_budget_12_from_30_frames_returns_exactly_12():
    frames = _make_30_frames()
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        max_frames=12,
    )
    assert len(bundle.frame_summaries) == 12


def test_first_and_last_frames_always_present():
    frames = _make_30_frames()
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        max_frames=12,
    )
    indices = [s.frame_index for s in bundle.frame_summaries]
    assert 0 in indices, "first frame must be included"
    assert 29 in indices, "last frame must be included"


def test_rule_trigger_frames_preferred_over_time_distributed():
    frames = _make_30_frames()
    # Place a high-severity rule trigger on frame 15 (mid-range)
    triggers = [_trigger(frame_index=15, severity="high")]
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=triggers,
        max_frames=5,  # tight budget
    )
    indices = [s.frame_index for s in bundle.frame_summaries]
    assert 15 in indices, "rule-trigger frame must be in bundle"


def test_high_severity_before_low_severity():
    frames = _make_30_frames()
    triggers = [
        _trigger(frame_index=10, severity="low"),
        _trigger(frame_index=20, severity="high"),
    ]
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=triggers,
        max_frames=4,  # first, last, + 2 rule frames — high before low
    )
    indices = [s.frame_index for s in bundle.frame_summaries]
    assert 20 in indices, "high-severity rule frame must appear within budget"


def test_selection_is_deterministic():
    frames = _make_30_frames()
    triggers = [_trigger(5, "medium"), _trigger(25, "medium")]
    kwargs = dict(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=triggers,
        max_frames=12,
    )
    bundle1 = build_evidence_bundle(**kwargs)
    bundle2 = build_evidence_bundle(**kwargs)
    assert [s.frame_index for s in bundle1.frame_summaries] == [
        s.frame_index for s in bundle2.frame_summaries
    ]


def test_selection_reasons_recorded():
    frames = _make_30_frames()
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript(),
        rules_triggered=[],
        max_frames=12,
    )
    reasons = {s.frame_index: s.selection_reason for s in bundle.frame_summaries}
    assert reasons[0] == "first"
    assert reasons[29] == "last"


def test_bundle_serialisable_to_json():
    frames = [_fa(i, i * 500) for i in range(3)]
    bundle = build_evidence_bundle(
        ad_id="ad_001",
        kept_frames=frames,
        transcript=_transcript((0, 1000, "hello")),
        rules_triggered=[],
        max_frames=12,
    )
    import json

    data = bundle.model_dump(mode="json")
    # Should round-trip cleanly
    text = json.dumps(data)
    assert "ad_001" in text
