from __future__ import annotations

import json
import re
from pathlib import Path

from ad_classifier.ingest.models import Manifest, ManifestFrame, WhisperTranscript
from ad_classifier.ingest.transcript import load_transcript_json, transcript_to_json

FRAME_NAME_RE = re.compile(
    r"(?:.*?_)?(?:frame|screenshot)_(?P<index>\d+)(?:_t(?P<time_ms>\d+)ms)?\.(?:png|jpg|jpeg)$",
    re.IGNORECASE,
)


def parse_frame_filename(path: Path, frame_interval_ms: int) -> ManifestFrame:
    match = FRAME_NAME_RE.fullmatch(path.name)
    if match is None:
        raise ValueError(f"Unsupported frame filename: {path.name}")

    frame_index = int(match.group("index"))
    time_ms = (
        int(match.group("time_ms"))
        if match.group("time_ms") is not None
        else frame_index * frame_interval_ms
    )
    return ManifestFrame(frame_index=frame_index, time_ms=time_ms, path=str(path))


def frames_from_directory(frames_dir: Path, frame_interval_ms: int) -> list[ManifestFrame]:
    frames = [
        parse_frame_filename(path, frame_interval_ms)
        for path in frames_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]
    frames.sort(key=lambda frame: (frame.frame_index, frame.time_ms))

    seen_indices: set[int] = set()
    seen_times: set[int] = set()
    for frame in frames:
        if frame.frame_index in seen_indices:
            raise ValueError(f"Duplicate frame index in manifest: {frame.frame_index}")
        if frame.time_ms in seen_times:
            raise ValueError(f"Duplicate frame timestamp in manifest: {frame.time_ms}")
        seen_indices.add(frame.frame_index)
        seen_times.add(frame.time_ms)

    return frames


def build_manifest(
    *,
    frames_dir: Path,
    transcript: WhisperTranscript,
    ad_id: str | None = None,
    frame_interval_ms: int = 500,
) -> Manifest:
    return Manifest(
        ad_id=ad_id,
        frame_interval_ms=frame_interval_ms,
        frames=frames_from_directory(frames_dir, frame_interval_ms),
        transcript=transcript,
    )


def build_manifest_from_files(
    *,
    frames_dir: Path,
    transcript_path: Path,
    ad_id: str | None = None,
    frame_interval_ms: int = 500,
) -> Manifest:
    return build_manifest(
        frames_dir=frames_dir,
        transcript=load_transcript_json(transcript_path),
        ad_id=ad_id,
        frame_interval_ms=frame_interval_ms,
    )


def write_manifest(path: Path, manifest: Manifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = manifest.model_dump(mode="json")
    data["transcript"] = transcript_to_json(manifest.transcript)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
