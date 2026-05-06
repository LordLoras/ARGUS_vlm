from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ad_classifier.config import AppConfig, resolve_config_path
from ad_classifier.db.connection import initialize_database, open_database
from ad_classifier.db.repositories import AdRepository
from ad_classifier.dedup.file_hash import source_sha256
from ad_classifier.dedup.models import DedupResult
from ad_classifier.dedup.service import DedupService, check_frame_phashes
from ad_classifier.ingest.ffmpeg import FFmpegMediaExtractor, MediaExtractor, existing_frames
from ad_classifier.ingest.models import (
    IngestArtifacts,
    IngestEvent,
    IngestFrame,
    IngestStage,
    VideoMetadata,
    WhisperTranscript,
)
from ad_classifier.ingest.persistence import persist_ingest
from ad_classifier.ingest.transcript import load_transcript_json, write_transcript_json
from ad_classifier.ingest.whisper import WhisperTranscriber, build_transcriber
from ad_classifier.paths import validate_ad_id
from ad_classifier.pipeline.manifest import build_manifest, write_manifest

ProgressCallback = Callable[[IngestEvent], None]


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
        self.events = []
        source_path = video_path.expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Video file not found: {source_path}")

        file_hash = source_sha256(source_path)
        resolved_ad_id = validate_ad_id(ad_id) if ad_id else ad_id_from_source_hash(file_hash)
        paths = self._paths_for_ad(resolved_ad_id)
        dedup = DedupResult(source_hash=file_hash)

        exact_artifacts = self._exact_duplicate_artifacts(
            source_path=source_path,
            source_hash=file_hash,
            requested_ad_id=resolved_ad_id,
            explicit_ad_id=ad_id is not None,
            force=force,
            persist=persist,
        )
        if exact_artifacts is not None:
            return exact_artifacts

        metadata = self._probe(source_path)
        frames = self._frames(source_path, paths["frames_dir"], force=force)
        dedup = self._near_duplicate_result(
            frames=frames,
            source_hash=file_hash,
            ad_id=resolved_ad_id,
            persist=persist,
        )
        if dedup.skipped:
            transcript = WhisperTranscript(
                segments=[],
                language=self.config.whisper.language,
                duration_ms=metadata.duration_ms,
                text="",
            )
            manifest_path = self._manifest(
                paths["frames_dir"],
                paths["manifest_path"],
                resolved_ad_id,
                transcript,
            )
            if persist:
                persist_ingest(
                    config=self.config,
                    config_file=self.config_file,
                    ad_id=resolved_ad_id,
                    source_path=source_path,
                    source_hash=file_hash,
                    metadata=metadata,
                    frames=frames,
                    transcript=transcript,
                    dedup=dedup,
                    status="duplicate",
                )
                self._event("persist", "ingest metadata persisted", done=1, total=1)
            return IngestArtifacts(
                ad_id=resolved_ad_id,
                source_path=source_path,
                metadata=metadata,
                frames_dir=paths["frames_dir"],
                frames=frames,
                audio_path=None,
                whisper_path=paths["whisper_path"],
                manifest_path=manifest_path,
                transcript=transcript,
                dedup=dedup,
                events=self.events,
            )

        audio_path = self._audio(source_path, paths["audio_path"], metadata, force=force)
        transcript = self._transcript(audio_path, paths["whisper_path"], metadata, force=force)
        manifest_path = self._manifest(
            paths["frames_dir"],
            paths["manifest_path"],
            resolved_ad_id,
            transcript,
        )
        if persist:
            persist_ingest(
                config=self.config,
                config_file=self.config_file,
                ad_id=resolved_ad_id,
                source_path=source_path,
                source_hash=file_hash,
                metadata=metadata,
                frames=frames,
                transcript=transcript,
                dedup=dedup,
                status="new",
            )
            self._event("persist", "ingest metadata persisted", done=1, total=1)

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
            dedup=dedup,
            events=self.events,
        )

    def _exact_duplicate_artifacts(
        self,
        *,
        source_path: Path,
        source_hash: str,
        requested_ad_id: str,
        explicit_ad_id: bool,
        force: bool,
        persist: bool,
    ) -> IngestArtifacts | None:
        if force or not persist or not self.config.dedup.skip_on_exact:
            return None

        db_path = resolve_config_path(self.config.paths.sqlite_path, self.config_file)
        initialize_database(db_path)
        conn = open_database(db_path)
        try:
            match = DedupService(conn=conn, config=self.config.dedup).check_exact(
                source_hash=source_hash,
                exclude_ad_id=requested_ad_id if explicit_ad_id else None,
            )
            if match is None:
                return None
            existing_ad = AdRepository(conn).get(match.ad_id)
        finally:
            conn.close()

        existing_paths = self._paths_for_ad(match.ad_id)
        frames = existing_frames(existing_paths["frames_dir"], self.config.ingest.frame_interval_ms)
        metadata = (
            VideoMetadata(
                duration_ms=existing_ad.duration_ms,
                width=existing_ad.width,
                height=existing_ad.height,
                fps=existing_ad.fps,
            )
            if existing_ad is not None
            else None
        )
        dedup = DedupResult(
            source_hash=source_hash,
            exact_duplicate_of=match.ad_id,
            skipped=True,
            skip_reason="exact_duplicate",
        )
        transcript = (
            load_transcript_json(existing_paths["whisper_path"])
            if existing_paths["whisper_path"].exists()
            else WhisperTranscript()
        )
        self._event("dedup", f"exact duplicate of {match.ad_id}", done=1, total=1, reused=True)
        return IngestArtifacts(
            ad_id=match.ad_id,
            source_path=source_path,
            metadata=metadata,
            frames_dir=existing_paths["frames_dir"],
            frames=frames,
            audio_path=(
                existing_paths["audio_path"] if existing_paths["audio_path"].exists() else None
            ),
            whisper_path=existing_paths["whisper_path"],
            manifest_path=existing_paths["manifest_path"],
            transcript=transcript,
            dedup=dedup,
            events=self.events,
        )

    def _near_duplicate_result(
        self,
        *,
        frames: list[IngestFrame],
        source_hash: str,
        ad_id: str,
        persist: bool,
    ) -> DedupResult:
        if not persist:
            return DedupResult(source_hash=source_hash)

        db_path = resolve_config_path(self.config.paths.sqlite_path, self.config_file)
        initialize_database(db_path)
        conn = open_database(db_path)
        try:
            result = check_frame_phashes(
                conn=conn,
                config=self.config.dedup,
                frame_paths=[frame.path for frame in frames],
                exclude_ad_id=ad_id,
                source_hash=source_hash,
            )
        finally:
            conn.close()

        if result.near_duplicate_of is not None:
            self._event(
                "dedup",
                f"near duplicate of {result.near_duplicate_of}",
                done=1,
                total=1,
                reused=result.skipped,
            )
        elif result.phash_mean is not None:
            self._event("dedup", "perceptual hash computed", done=1, total=1)
        return result

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

    def _event(
        self,
        stage: IngestStage,
        message: str,
        *,
        done: int | None = None,
        total: int | None = None,
        reused: bool = False,
    ) -> None:
        event = IngestEvent(
            stage=stage,
            message=message,
            done=done,
            total=total,
            reused=reused,
        )
        self.events.append(event)
        if self.progress is not None:
            self.progress(event)
