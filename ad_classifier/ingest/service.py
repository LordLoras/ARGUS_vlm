from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from pathlib import Path

from ad_classifier.config import AppConfig, resolve_config_path
from ad_classifier.db.connection import initialize_database, open_database
from ad_classifier.db.repositories import AdRepository
from ad_classifier.ingest.ffmpeg import FFmpegMediaExtractor, MediaExtractor, existing_frames
from ad_classifier.ingest.models import (
    IngestArtifacts,
    IngestEvent,
    IngestFrame,
    TranscriptSegment,
    VideoMetadata,
    WhisperTranscript,
)
from ad_classifier.ingest.transcript import load_transcript_json, write_transcript_json
from ad_classifier.ingest.whisper import WhisperTranscriber, build_transcriber
from ad_classifier.models.ads import AdRecord
from ad_classifier.paths import validate_ad_id
from ad_classifier.pipeline.manifest import build_manifest, write_manifest

ProgressCallback = Callable[[IngestEvent], None]


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ad_id_from_source_hash(source_hash: str) -> str:
    return validate_ad_id(f"ad_{source_hash[:8]}")


class IngestService:
    def __init__(
        self,
        *,
        config: AppConfig,
        config_file: Path,
        media_extractor: MediaExtractor | None = None,
        transcriber: WhisperTranscriber | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.config_file = config_file
        self.media_extractor = media_extractor or FFmpegMediaExtractor(
            ffmpeg_path=config.ingest.ffmpeg_path,
            ffprobe_path=config.ingest.ffprobe_path,
        )
        self.transcriber = transcriber or build_transcriber(config, config_file)
        self.progress = progress
        self.events: list[IngestEvent] = []

    def run(
        self,
        *,
        video_path: Path,
        ad_id: str | None = None,
        force: bool = False,
        persist: bool = True,
    ) -> IngestArtifacts:
        source_path = video_path.expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Video file not found: {source_path}")

        file_hash = source_sha256(source_path)
        resolved_ad_id = validate_ad_id(ad_id) if ad_id else ad_id_from_source_hash(file_hash)
        paths = self._paths_for_ad(resolved_ad_id)

        metadata = self._probe(source_path)
        frames = self._frames(source_path, paths["frames_dir"], force=force)
        audio_path = self._audio(source_path, paths["audio_path"], metadata, force=force)
        transcript = self._transcript(audio_path, paths["whisper_path"], metadata, force=force)
        manifest_path = self._manifest(
            paths["frames_dir"],
            paths["manifest_path"],
            resolved_ad_id,
            transcript,
        )
        if persist:
            self._persist(
                ad_id=resolved_ad_id,
                source_path=source_path,
                source_hash=file_hash,
                metadata=metadata,
                frames=frames,
                transcript=transcript,
            )

        return IngestArtifacts(
            ad_id=resolved_ad_id,
            source_path=source_path,
            metadata=metadata,
            frames_dir=paths["frames_dir"],
            frames=frames,
            audio_path=audio_path,
            whisper_path=paths["whisper_path"],
            manifest_path=manifest_path,
            transcript=transcript,
            events=self.events,
        )

    def _paths_for_ad(self, ad_id: str) -> dict[str, Path]:
        return {
            "frames_dir": resolve_config_path(self.config.paths.frames, self.config_file) / ad_id,
            "audio_path": resolve_config_path(self.config.paths.audio, self.config_file)
            / ad_id
            / "audio.wav",
            "whisper_path": resolve_config_path(self.config.paths.whisper, self.config_file)
            / ad_id
            / "whisper.json",
            "manifest_path": resolve_config_path(self.config.paths.out, self.config_file)
            / ad_id
            / "manifest.json",
        }

    def _probe(self, source_path: Path) -> VideoMetadata:
        metadata = self.media_extractor.probe(source_path)
        self._event("probe", "video metadata loaded", done=1, total=1)
        return metadata

    def _frames(self, source_path: Path, frames_dir: Path, *, force: bool) -> list[IngestFrame]:
        cached = [] if force else existing_frames(frames_dir, self.config.ingest.frame_interval_ms)
        if cached and not force:
            self._event(
                "frames", "reused cached frames", done=len(cached), total=len(cached), reused=True
            )
            return cached

        frames = self.media_extractor.extract_frames(
            source_path,
            frames_dir,
            frame_interval_ms=self.config.ingest.frame_interval_ms,
        )
        self._event("frames", "frames extracted", done=len(frames), total=len(frames))
        return frames

    def _audio(
        self,
        source_path: Path,
        audio_path: Path,
        metadata: VideoMetadata,
        *,
        force: bool,
    ) -> Path | None:
        if audio_path.exists() and not force:
            self._event("audio", "reused cached audio", done=1, total=1, reused=True)
            return audio_path

        extracted = self.media_extractor.extract_audio(
            source_path,
            audio_path,
            sample_rate=self.config.ingest.audio_sample_rate,
            has_audio=metadata.has_audio,
        )
        message = "audio extracted" if metadata.has_audio else "silent audio placeholder written"
        self._event("audio", message, done=1, total=1)
        return extracted

    def _transcript(
        self,
        audio_path: Path | None,
        whisper_path: Path,
        metadata: VideoMetadata,
        *,
        force: bool,
    ) -> WhisperTranscript:
        if whisper_path.exists() and not force:
            transcript = load_transcript_json(whisper_path)
            self._event("whisper", "reused cached transcript", done=1, total=1, reused=True)
            return transcript

        if audio_path is None or not metadata.has_audio:
            transcript = WhisperTranscript(
                segments=[],
                language=self.config.whisper.language,
                duration_ms=metadata.duration_ms,
                text="",
            )
            write_transcript_json(whisper_path, transcript)
            self._event(
                "whisper", "empty transcript written for video without audio", done=1, total=1
            )
            return transcript

        transcript = self.transcriber.transcribe(audio_path, whisper_path)
        self._event("whisper", "transcript generated", done=1, total=1)
        return transcript

    def _manifest(
        self,
        frames_dir: Path,
        manifest_path: Path,
        ad_id: str,
        transcript: WhisperTranscript,
    ) -> Path:
        manifest = build_manifest(
            frames_dir=frames_dir,
            transcript=transcript,
            ad_id=ad_id,
            frame_interval_ms=self.config.ingest.frame_interval_ms,
        )
        write_manifest(manifest_path, manifest)
        self._event(
            "manifest", "manifest written", done=len(manifest.frames), total=len(manifest.frames)
        )
        return manifest_path

    def _persist(
        self,
        *,
        ad_id: str,
        source_path: Path,
        source_hash: str,
        metadata: VideoMetadata,
        frames: list[IngestFrame],
        transcript: WhisperTranscript,
    ) -> None:
        db_path = resolve_config_path(self.config.paths.sqlite_path, self.config_file)
        initialize_database(db_path)
        conn = open_database(db_path)
        try:
            AdRepository(conn).upsert_ingest(
                AdRecord(
                    id=ad_id,
                    source_path=str(source_path),
                    duration_ms=metadata.duration_ms,
                    width=metadata.width,
                    height=metadata.height,
                    fps=metadata.fps,
                    status="new",
                    source_hash=source_hash,
                )
            )
            _replace_frame_rows(conn, ad_id, frames)
            _replace_transcript_rows(conn, ad_id, transcript.segments)
            conn.commit()
        finally:
            conn.close()
        self._event("persist", "ingest metadata persisted", done=1, total=1)

    def _event(
        self,
        stage: str,
        message: str,
        *,
        done: int | None = None,
        total: int | None = None,
        reused: bool = False,
    ) -> None:
        event = IngestEvent(
            stage=stage,  # type: ignore[arg-type]
            message=message,
            done=done,
            total=total,
            reused=reused,
        )
        self.events.append(event)
        if self.progress is not None:
            self.progress(event)


def _replace_frame_rows(conn: sqlite3.Connection, ad_id: str, frames: list[IngestFrame]) -> None:
    conn.execute("DELETE FROM frames WHERE ad_id = ?", (ad_id,))
    conn.executemany(
        """
        INSERT INTO frames (ad_id, frame_index, time_ms, path, kept)
        VALUES (?, ?, ?, ?, 1)
        """,
        [(ad_id, frame.frame_index, frame.time_ms, str(frame.path)) for frame in frames],
    )


def _replace_transcript_rows(
    conn: sqlite3.Connection,
    ad_id: str,
    segments: list[TranscriptSegment],
) -> None:
    conn.execute("DELETE FROM transcript_segments WHERE ad_id = ?", (ad_id,))
    conn.executemany(
        """
        INSERT INTO transcript_segments (ad_id, start_ms, end_ms, text, confidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (ad_id, segment.start_ms, segment.end_ms, segment.text, segment.confidence)
            for segment in segments
        ],
    )
