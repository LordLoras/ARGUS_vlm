from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from ad_classifier.config import AppConfig, DedupConfig, IngestConfig, PathsConfig, WhisperConfig
from ad_classifier.ingest.ffmpeg import existing_frames
from ad_classifier.ingest.models import TranscriptSegment, VideoMetadata, WhisperTranscript
from ad_classifier.ingest.service import IngestService
from ad_classifier.ingest.transcript import write_transcript_json


class FakeMediaExtractor:
    def __init__(self) -> None:
        self.probe_calls = 0
        self.frame_calls = 0
        self.audio_calls = 0

    def probe(self, video_path: Path) -> VideoMetadata:
        self.probe_calls += 1
        return VideoMetadata(
            duration_ms=1000,
            width=320,
            height=180,
            fps=30.0,
            video_codec="h264",
            audio_codec="aac",
        )

    def extract_frames(
        self,
        video_path: Path,
        frames_dir: Path,
        *,
        frame_interval_ms: int,
    ):
        self.frame_calls += 1
        frames_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), color=(0, 0, 0)).save(frames_dir / "frame_001_t0500ms.png")
        Image.new("RGB", (32, 32), color=(255, 255, 255)).save(frames_dir / "frame_000_t0000ms.png")
        return existing_frames(frames_dir, frame_interval_ms)

    def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        *,
        sample_rate: int,
        has_audio: bool,
    ) -> Path:
        self.audio_calls += 1
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"fake wav")
        return audio_path


class FakeTranscriber:
    def __init__(self) -> None:
        self.calls = 0
        self.transcript = WhisperTranscript(
            language="en",
            text="zero down financing",
            segments=[
                TranscriptSegment(
                    start_ms=0,
                    end_ms=900,
                    text="zero down financing",
                    confidence=0.9,
                )
            ],
        )

    def transcribe(self, audio_path: Path, output_path: Path) -> WhisperTranscript:
        self.calls += 1
        write_transcript_json(output_path, self.transcript)
        return self.transcript


def make_config(tmp_path: Path, *, skip_on_near_duplicate: bool = False) -> tuple[AppConfig, Path]:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}", encoding="utf-8")
    return (
        AppConfig(
            paths=PathsConfig(
                frames=tmp_path / "frames",
                audio=tmp_path / "audio",
                whisper=tmp_path / "whisper",
                out=tmp_path / "out",
                sqlite_path=tmp_path / "ad_classifier.db",
            ),
            ingest=IngestConfig(frame_interval_ms=500, audio_sample_rate=16000),
            whisper=WhisperConfig(backend="mock"),
            dedup=DedupConfig(
                skip_on_exact=True,
                skip_on_near_duplicate=skip_on_near_duplicate,
                phash_distance_threshold=0,
            ),
        ),
        config_file,
    )


def test_ingest_service_writes_artifacts_and_reuses_cached_outputs(tmp_path):
    config, config_file = make_config(tmp_path)
    video = tmp_path / "prepared-ad.mp4"
    video.write_bytes(b"not a real video; extractor is mocked")
    media = FakeMediaExtractor()
    transcriber = FakeTranscriber()
    service = IngestService(
        config=config,
        config_file=config_file,
        media_extractor=media,
        transcriber=transcriber,
    )

    first = service.run(video_path=video, ad_id="ad_abcd1234", persist=False)
    second = service.run(video_path=video, ad_id="ad_abcd1234", persist=False)

    assert first.ad_id == "ad_abcd1234"
    assert [frame.frame_index for frame in first.frames] == [0, 1]
    assert first.audio_path is not None and first.audio_path.exists()
    assert first.whisper_path.exists()
    assert first.manifest_path.exists()
    assert media.frame_calls == 1
    assert media.audio_calls == 1
    assert transcriber.calls == 1
    assert any(event.reused for event in second.events)


def test_ingest_service_persists_ad_frames_and_transcript(tmp_path):
    config, config_file = make_config(tmp_path)
    video = tmp_path / "prepared-ad.mp4"
    video.write_bytes(b"not a real video; extractor is mocked")

    service = IngestService(
        config=config,
        config_file=config_file,
        media_extractor=FakeMediaExtractor(),
        transcriber=FakeTranscriber(),
    )

    result = service.run(video_path=video, ad_id="ad_abcd1234", persist=True)

    conn = sqlite3.connect(tmp_path / "ad_classifier.db")
    try:
        ad_row = conn.execute(
            "SELECT id, status, duration_ms, width, height, phash_mean FROM ads WHERE id = ?",
            (result.ad_id,),
        ).fetchone()
        frame_count = conn.execute(
            "SELECT COUNT(*) FROM frames WHERE ad_id = ?",
            (result.ad_id,),
        ).fetchone()[0]
        transcript_count = conn.execute(
            "SELECT COUNT(*) FROM transcript_segments WHERE ad_id = ?",
            (result.ad_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert ad_row[:5] == ("ad_abcd1234", "new", 1000, 320, 180)
    assert ad_row[5] is not None
    assert frame_count == 2
    assert transcript_count == 1


def test_ingest_service_short_circuits_exact_duplicate(tmp_path):
    config, config_file = make_config(tmp_path)
    video = tmp_path / "prepared-ad.mp4"
    video.write_bytes(b"same bytes")
    media = FakeMediaExtractor()
    transcriber = FakeTranscriber()
    service = IngestService(
        config=config,
        config_file=config_file,
        media_extractor=media,
        transcriber=transcriber,
    )

    first = service.run(video_path=video, persist=True)
    second = service.run(video_path=video, persist=True)

    assert second.ad_id == first.ad_id
    assert second.dedup.exact_duplicate_of == first.ad_id
    assert second.dedup.skipped is True
    assert media.frame_calls == 1
    assert transcriber.calls == 1


def test_ingest_service_short_circuits_near_duplicate_when_enabled(tmp_path):
    config, config_file = make_config(tmp_path, skip_on_near_duplicate=True)
    first_video = tmp_path / "first.mp4"
    second_video = tmp_path / "second.mp4"
    first_video.write_bytes(b"first bytes")
    second_video.write_bytes(b"second bytes")
    media = FakeMediaExtractor()
    transcriber = FakeTranscriber()
    service = IngestService(
        config=config,
        config_file=config_file,
        media_extractor=media,
        transcriber=transcriber,
    )

    first = service.run(video_path=first_video, ad_id="ad_abcd1234", persist=True)
    second = service.run(video_path=second_video, ad_id="ad_dcba4321", persist=True)

    assert first.dedup.phash_mean is not None
    assert second.dedup.near_duplicate_of == "ad_abcd1234"
    assert second.dedup.skipped is True
    assert second.audio_path is None
    assert media.audio_calls == 1
    assert transcriber.calls == 1
