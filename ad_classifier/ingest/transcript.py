from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript

TIMESTAMP_RE = re.compile(r"(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)[,.](?P<millis>\d+)")


def _coerce_ms(value: Any, *, assume_seconds: bool) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        value = value.strip()
        match = TIMESTAMP_RE.fullmatch(value)
        if match:
            hours = int(match.group("hours"))
            minutes = int(match.group("minutes"))
            seconds = int(match.group("seconds"))
            millis = int(match.group("millis")[:3].ljust(3, "0"))
            return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis
        number = float(value)
    else:
        number = float(value)
    if assume_seconds:
        number *= 1000
    return max(0, int(round(number)))


def _segment_from_seconds(item: dict[str, Any]) -> TranscriptSegment:
    return TranscriptSegment(
        start_ms=_coerce_ms(item.get("start"), assume_seconds=True),
        end_ms=_coerce_ms(item.get("end"), assume_seconds=True),
        text=str(item.get("text") or "").strip(),
        confidence=item.get("confidence"),
    )


def _segment_from_millis(item: dict[str, Any]) -> TranscriptSegment:
    return TranscriptSegment(
        start_ms=_coerce_ms(item.get("start_ms", item.get("start")), assume_seconds=False),
        end_ms=_coerce_ms(item.get("end_ms", item.get("end")), assume_seconds=False),
        text=str(item.get("text") or "").strip(),
        confidence=item.get("confidence"),
    )


def _segment_from_whisper_cpp(item: dict[str, Any]) -> TranscriptSegment:
    offsets = item.get("offsets")
    if isinstance(offsets, dict):
        start_ms = _coerce_ms(offsets.get("from"), assume_seconds=False)
        end_ms = _coerce_ms(offsets.get("to"), assume_seconds=False)
    else:
        timestamps = item.get("timestamps") if isinstance(item.get("timestamps"), dict) else {}
        start_ms = _coerce_ms(timestamps.get("from"), assume_seconds=False)
        end_ms = _coerce_ms(timestamps.get("to"), assume_seconds=False)

    return TranscriptSegment(
        start_ms=start_ms,
        end_ms=end_ms,
        text=str(item.get("text") or "").strip(),
        confidence=item.get("confidence"),
    )


def _joined_text(segments: list[TranscriptSegment]) -> str:
    return " ".join(segment.text for segment in segments if segment.text).strip()


def transcript_from_json(data: Any) -> WhisperTranscript:
    if isinstance(data, list):
        segments = [_segment_from_millis(item) for item in data if isinstance(item, dict)]
        return WhisperTranscript(segments=segments, text=_joined_text(segments))

    if not isinstance(data, dict):
        raise ValueError("Whisper transcript JSON must be an object or array")

    if isinstance(data.get("segments"), list):
        segments = [
            _segment_from_seconds(item) for item in data["segments"] if isinstance(item, dict)
        ]
        return WhisperTranscript(
            segments=segments,
            language=data.get("language"),
            duration_ms=data.get("duration_ms"),
            text=str(data.get("text") or _joined_text(segments)).strip(),
        )

    if isinstance(data.get("transcription"), list):
        segments = [
            _segment_from_whisper_cpp(item)
            for item in data["transcription"]
            if isinstance(item, dict)
        ]
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        return WhisperTranscript(
            segments=segments,
            language=result.get("language"),
            text=_joined_text(segments),
        )

    raise ValueError("Unsupported Whisper transcript JSON shape")


def load_transcript_json(path: Path) -> WhisperTranscript:
    data = json.loads(path.read_text(encoding="utf-8"))
    return transcript_from_json(data)


def transcript_to_json(transcript: WhisperTranscript) -> dict[str, Any]:
    return {
        "language": transcript.language,
        "duration_ms": transcript.duration_ms,
        "text": transcript.text or _joined_text(transcript.segments),
        "segments": [
            {
                "id": index,
                "start": segment.start_ms / 1000,
                "end": segment.end_ms / 1000,
                "text": segment.text,
                "confidence": segment.confidence,
            }
            for index, segment in enumerate(transcript.segments)
        ],
    }


def write_transcript_json(path: Path, transcript: WhisperTranscript) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(transcript_to_json(transcript), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
