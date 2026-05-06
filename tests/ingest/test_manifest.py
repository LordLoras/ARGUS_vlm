from __future__ import annotations

import json

import pytest

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.ingest.transcript import transcript_from_json, write_transcript_json
from ad_classifier.pipeline.manifest import (
    build_manifest_from_files,
    frames_from_directory,
    parse_frame_filename,
)


def test_parse_frame_filename_prefers_explicit_timestamp(tmp_path):
    frame = parse_frame_filename(tmp_path / "ad123_frame_000001_t2500ms.jpg", 500)

    assert frame.frame_index == 1
    assert frame.time_ms == 2500


def test_parse_frame_filename_infers_timestamp(tmp_path):
    frame = parse_frame_filename(tmp_path / "screenshot_000004.png", 500)

    assert frame.frame_index == 4
    assert frame.time_ms == 2000


def test_frames_from_directory_sorts_without_filesystem_order(tmp_path):
    (tmp_path / "frame_002_t1000ms.png").write_bytes(b"fake")
    (tmp_path / "frame_000_t0000ms.png").write_bytes(b"fake")
    (tmp_path / "frame_001_t0500ms.png").write_bytes(b"fake")

    frames = frames_from_directory(tmp_path, 500)

    assert [frame.frame_index for frame in frames] == [0, 1, 2]
    assert [frame.time_ms for frame in frames] == [0, 500, 1000]


def test_frames_from_directory_rejects_duplicate_timestamps(tmp_path):
    (tmp_path / "frame_000_t0000ms.png").write_bytes(b"fake")
    (tmp_path / "frame_001_t0000ms.png").write_bytes(b"fake")

    with pytest.raises(ValueError, match="Duplicate frame timestamp"):
        frames_from_directory(tmp_path, 500)


def test_build_manifest_from_files_round_trips_transcript(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_000_t0000ms.png").write_bytes(b"fake")
    transcript_path = tmp_path / "whisper.json"
    write_transcript_json(transcript_path, WhisperTranscript(language="en", text="hello"))

    manifest = build_manifest_from_files(
        frames_dir=frames_dir,
        transcript_path=transcript_path,
        ad_id="ad_abcd1234",
        frame_interval_ms=500,
    )

    assert manifest.ad_id == "ad_abcd1234"
    assert len(manifest.frames) == 1
    assert manifest.transcript.language == "en"


def test_transcript_loader_supports_whisper_cpp_shape():
    transcript = transcript_from_json(
        {
            "result": {"language": "en"},
            "transcription": [
                {
                    "offsets": {"from": 500, "to": 1250},
                    "text": "limited time offer",
                }
            ],
        }
    )

    assert transcript.language == "en"
    assert transcript.segments[0].start_ms == 500
    assert transcript.segments[0].end_ms == 1250
    assert transcript.text == "limited time offer"


def test_transcript_loader_supports_flat_millisecond_shape():
    transcript = transcript_from_json(
        json.loads('[{"start_ms": 1000, "end_ms": 1500, "text": "save now"}]')
    )

    assert transcript.segments[0].start_ms == 1000
    assert transcript.segments[0].text == "save now"
