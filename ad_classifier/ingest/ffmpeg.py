from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any, Protocol

from ad_classifier.ingest.models import IngestFrame, VideoMetadata
from ad_classifier.pipeline.manifest import frames_from_directory


class MediaExtractor(Protocol):
    def probe(self, video_path: Path) -> VideoMetadata: ...

    def extract_frames(
        self,
        video_path: Path,
        frames_dir: Path,
        *,
        frame_interval_ms: int,
    ) -> list[IngestFrame]: ...

    def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        *,
        sample_rate: int,
        has_audio: bool,
    ) -> Path | None: ...


def existing_frames(frames_dir: Path, frame_interval_ms: int) -> list[IngestFrame]:
    if not frames_dir.exists():
        return []
    manifest_frames = frames_from_directory(frames_dir, frame_interval_ms)
    return [
        IngestFrame(
            frame_index=frame.frame_index,
            time_ms=frame.time_ms,
            path=Path(frame.path),
        )
        for frame in manifest_frames
    ]


def write_silent_wav(path: Path, *, sample_rate: int, duration_ms: int = 250) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)
    return path


class FFmpegMediaExtractor:
    def __init__(self, *, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def probe(self, video_path: Path) -> VideoMetadata:
        cmd = [
            self.ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
        result = self._run(cmd)
        data = json.loads(result.stdout)
        return _metadata_from_ffprobe(data)

    def extract_frames(
        self,
        video_path: Path,
        frames_dir: Path,
        *,
        frame_interval_ms: int,
    ) -> list[IngestFrame]:
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        frames_dir.mkdir(parents=True, exist_ok=True)

        output_pattern = frames_dir / "frame_%06d.png"
        fps = 1000 / frame_interval_ms
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps:.6f}",
            "-start_number",
            "0",
            str(output_pattern),
        ]
        self._run(cmd)

        raw_frames = sorted(frames_dir.glob("frame_*.png"))
        if not raw_frames:
            raise RuntimeError(f"ffmpeg produced no frames for {video_path}")

        for raw_frame in raw_frames:
            parts = raw_frame.stem.split("_")
            frame_index = int(parts[-1])
            time_ms = frame_index * frame_interval_ms
            canonical = frames_dir / f"frame_{frame_index:06d}_t{time_ms:06d}ms.png"
            if raw_frame != canonical:
                raw_frame.rename(canonical)

        return existing_frames(frames_dir, frame_interval_ms)

    def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        *,
        sample_rate: int,
        has_audio: bool,
    ) -> Path | None:
        if not has_audio:
            return write_silent_wav(audio_path, sample_rate=sample_rate)

        audio_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ]
        self._run(cmd)
        return audio_path

    @staticmethod
    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Command failed ({cmd[0]}): {stderr}")
        return result


def _metadata_from_ffprobe(data: dict[str, Any]) -> VideoMetadata:
    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError("Input file has no decodable video stream")

    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )
    format_data = data.get("format") if isinstance(data.get("format"), dict) else {}
    duration = format_data.get("duration") or video_stream.get("duration")
    duration_ms = int(round(float(duration) * 1000)) if duration is not None else None

    return VideoMetadata(
        duration_ms=duration_ms,
        width=video_stream.get("width"),
        height=video_stream.get("height"),
        fps=_parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        video_codec=video_stream.get("codec_name"),
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
    )


def _parse_fps(value: Any) -> float | None:
    if value in (None, "0/0"):
        return None
    text = str(value)
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        denominator_float = float(denominator)
        if denominator_float == 0:
            return None
        return float(numerator) / denominator_float
    return float(text)
