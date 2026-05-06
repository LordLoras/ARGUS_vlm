from __future__ import annotations

import json

import pytest

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.ingest.transcript import transcript_from_json
from ad_classifier.pipeline.alignment import align_transcript_to_frame, align_transcript_to_frames


def _transcript(*segments: tuple[int, int, str]) -> WhisperTranscript:
    segs = [TranscriptSegment(start_ms=s, end_ms=e, text=t) for s, e, t in segments]
    return WhisperTranscript(segments=segs, text=" ".join(t for _, _, t in segments))


# ---------------------------------------------------------------------------
# Transcript loaders (Shape 1 and Shape 2)
# ---------------------------------------------------------------------------


def test_transcript_loader_shape1_seconds():
    data = {
        "language": "en",
        "segments": [
            {"start": 0.2, "end": 1.7, "text": "hello"},
            {"start": 2.0, "end": 3.5, "text": "world"},
        ],
    }
    t = transcript_from_json(data)
    assert t.language == "en"
    assert len(t.segments) == 2
    assert t.segments[0].start_ms == 200
    assert t.segments[0].end_ms == 1700
    assert t.segments[0].text == "hello"


def test_transcript_loader_shape2_milliseconds():
    data = [
        {"start_ms": 200, "end_ms": 1700, "text": "hello"},
        {"start_ms": 2000, "end_ms": 3500, "text": "world"},
    ]
    t = transcript_from_json(data)
    assert len(t.segments) == 2
    assert t.segments[1].start_ms == 2000
    assert t.segments[1].end_ms == 3500


def test_transcript_loader_rejects_invalid_shape():
    with pytest.raises(ValueError):
        transcript_from_json("not a dict or list")


# ---------------------------------------------------------------------------
# Alignment: single frame
# ---------------------------------------------------------------------------


def test_alignment_returns_overlapping_segment():
    # frame at 2500ms, window 500 → [2000, 3000]
    # "opening" ends at 1000 < 2000 → excluded
    # "middle" [1500, 3000]: start 1500 <= 3000 AND end 3000 >= 2000 → included
    # "end" starts at 5000 > 3000 → excluded
    t = _transcript((0, 1000, "opening"), (1500, 3000, "middle"), (5000, 7000, "end"))
    result = align_transcript_to_frame(t, frame_time_ms=2500, window_ms=500)
    texts = {s.text for s in result}
    assert "middle" in texts
    assert "opening" not in texts
    assert "end" not in texts


def test_alignment_window_catches_segment_at_boundary():
    t = _transcript((3000, 4000, "boundary_seg"))
    # frame at 5000, window 1500 → hi = 6500, lo = 3500; seg ends at 4000 >= 3500 ✓
    result = align_transcript_to_frame(t, frame_time_ms=5000, window_ms=1500)
    assert len(result) == 1
    assert result[0].text == "boundary_seg"


def test_alignment_excludes_segment_outside_window():
    t = _transcript((0, 500, "early"))
    # frame at 5000, window 1500 → lo = 3500; seg ends at 500 < 3500 ✗
    result = align_transcript_to_frame(t, frame_time_ms=5000, window_ms=1500)
    assert result == []


def test_alignment_includes_segment_that_spans_frame():
    # A long segment that completely spans the frame window
    t = _transcript((0, 30000, "long narration"))
    result = align_transcript_to_frame(t, frame_time_ms=10000, window_ms=1500)
    assert len(result) == 1


def test_alignment_overlapping_segments_edge_case():
    # Overlapping segments — should return all that overlap
    t = _transcript((0, 2000, "seg_a"), (1000, 3000, "seg_b"), (4000, 5000, "seg_c"))
    result = align_transcript_to_frame(t, frame_time_ms=1500, window_ms=1000)
    texts = {s.text for s in result}
    assert "seg_a" in texts
    assert "seg_b" in texts
    assert "seg_c" not in texts


def test_alignment_empty_transcript():
    t = WhisperTranscript(segments=[], text="")
    result = align_transcript_to_frame(t, frame_time_ms=1000, window_ms=1500)
    assert result == []


# ---------------------------------------------------------------------------
# Alignment: multiple frames
# ---------------------------------------------------------------------------


def test_align_to_frames_returns_mapping():
    t = _transcript((0, 1000, "intro"), (2000, 3000, "main"), (8000, 9000, "outro"))
    mapping = align_transcript_to_frames(t, frame_times_ms=[500, 2500, 8500], window_ms=1000)
    assert set(mapping.keys()) == {500, 2500, 8500}
    assert any(s.text == "intro" for s in mapping[500])
    assert any(s.text == "main" for s in mapping[2500])
    assert any(s.text == "outro" for s in mapping[8500])


def test_align_to_frames_empty_frames():
    t = _transcript((0, 1000, "text"))
    result = align_transcript_to_frames(t, frame_times_ms=[])
    assert result == {}
