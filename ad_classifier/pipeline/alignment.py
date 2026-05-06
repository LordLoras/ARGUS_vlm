from __future__ import annotations

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript


def align_transcript_to_frame(
    transcript: WhisperTranscript,
    frame_time_ms: int,
    window_ms: int = 1500,
) -> list[TranscriptSegment]:
    """
    Return transcript segments whose interval overlaps [frame_time_ms ± window_ms].

    A segment overlaps when its start_ms <= (frame_time_ms + window_ms)
    AND its end_ms >= (frame_time_ms - window_ms).
    """
    lo = frame_time_ms - window_ms
    hi = frame_time_ms + window_ms
    return [seg for seg in transcript.segments if seg.start_ms <= hi and seg.end_ms >= lo]


def align_transcript_to_frames(
    transcript: WhisperTranscript,
    frame_times_ms: list[int],
    window_ms: int = 1500,
) -> dict[int, list[TranscriptSegment]]:
    """Return a mapping of frame_time_ms → aligned segments for a list of frames."""
    return {
        t: align_transcript_to_frame(transcript, t, window_ms) for t in frame_times_ms
    }
