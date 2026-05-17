from __future__ import annotations

import html
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from ad_classifier.creative.storyboard.models import Storyboard, StoryboardShot
from ad_classifier.db.repositories import AdRepository
from ad_classifier.dedup.phash import hamming_distance
from ad_classifier.models.common import EvidenceItem

PHASH_CUT_DISTANCE = 12
SCENE_GAP_MS = 2500
DEFAULT_FRAME_INTERVAL_MS = 500


@dataclass(frozen=True)
class FrameRow:
    frame_index: int
    time_ms: int
    path: str
    phash: str | None


@dataclass(frozen=True)
class TranscriptRow:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None


@dataclass(frozen=True)
class OCRRow:
    frame_index: int
    time_ms: int
    engine: str
    text: str
    confidence: float | None


def build_storyboard(conn: sqlite3.Connection, ad_id: str, out_root: Path) -> Storyboard:
    ad = AdRepository(conn).get(ad_id)
    if ad is None:
        raise ValueError("ad not found")

    frames = _load_frames(conn, ad_id)
    transcript = _load_transcript(conn, ad_id)
    ocr_by_frame = _load_ocr_by_frame(conn, ad_id)
    output_dir = out_root / ad_id
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "storyboard.json"
    html_path = output_dir / "storyboard.html"

    frame_interval_ms = _infer_frame_interval_ms(frames)
    groups = _segment_frames(frames)
    shots = [
        _build_shot(
            shot_index=index,
            frames=group,
            next_start_ms=groups[index + 1][0].time_ms if index + 1 < len(groups) else None,
            ad_duration_ms=ad.duration_ms,
            frame_interval_ms=frame_interval_ms,
            transcript=transcript,
            ocr_by_frame=ocr_by_frame,
        )
        for index, group in enumerate(groups)
    ]

    storyboard = Storyboard(
        ad_id=ad_id,
        generated_at=datetime.now(UTC),
        json_path=str(json_path),
        html_path=str(html_path),
        shot_count=len(shots),
        method="deterministic_phash_transcript_ocr_v1",
        shots=shots,
    )
    json_path.write_text(
        json.dumps(storyboard.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    html_path.write_text(_storyboard_html(storyboard), encoding="utf-8")
    return storyboard


def _load_frames(conn: sqlite3.Connection, ad_id: str) -> list[FrameRow]:
    rows = conn.execute(
        """
        SELECT frame_index, time_ms, path, phash
        FROM frames
        WHERE ad_id = ? AND kept = 1
        ORDER BY frame_index
        """,
        (ad_id,),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """
            SELECT frame_index, time_ms, path, phash
            FROM frames
            WHERE ad_id = ?
            ORDER BY frame_index
            """,
            (ad_id,),
        ).fetchall()
    return [
        FrameRow(
            frame_index=int(row["frame_index"]),
            time_ms=int(row["time_ms"]),
            path=str(row["path"]),
            phash=row["phash"],
        )
        for row in rows
    ]


def _load_transcript(conn: sqlite3.Connection, ad_id: str) -> list[TranscriptRow]:
    rows = conn.execute(
        """
        SELECT start_ms, end_ms, text, confidence
        FROM transcript_segments
        WHERE ad_id = ?
        ORDER BY start_ms, id
        """,
        (ad_id,),
    ).fetchall()
    return [
        TranscriptRow(
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            text=str(row["text"]),
            confidence=row["confidence"],
        )
        for row in rows
    ]


def _load_ocr_by_frame(conn: sqlite3.Connection, ad_id: str) -> dict[int, list[OCRRow]]:
    rows = conn.execute(
        """
        SELECT f.frame_index, f.time_ms, o.engine, o.text, o.confidence
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE f.ad_id = ?
        ORDER BY f.frame_index, o.id
        """,
        (ad_id,),
    ).fetchall()
    by_frame: dict[int, list[OCRRow]] = defaultdict(list)
    for row in rows:
        by_frame[int(row["frame_index"])].append(
            OCRRow(
                frame_index=int(row["frame_index"]),
                time_ms=int(row["time_ms"]),
                engine=str(row["engine"]),
                text=str(row["text"]),
                confidence=row["confidence"],
            )
        )
    return dict(by_frame)


def _infer_frame_interval_ms(frames: list[FrameRow]) -> int:
    diffs = [
        right.time_ms - left.time_ms
        for left, right in zip(frames, frames[1:], strict=False)
        if right.time_ms > left.time_ms
    ]
    if not diffs:
        return DEFAULT_FRAME_INTERVAL_MS
    return max(1, int(median(diffs)))


def _segment_frames(frames: list[FrameRow]) -> list[list[FrameRow]]:
    if not frames:
        return []
    groups: list[list[FrameRow]] = [[frames[0]]]
    for previous, frame in zip(frames, frames[1:], strict=False):
        if _starts_new_shot(previous, frame):
            groups.append([frame])
        else:
            groups[-1].append(frame)
    return groups


def _starts_new_shot(previous: FrameRow, frame: FrameRow) -> bool:
    if frame.time_ms - previous.time_ms > SCENE_GAP_MS:
        return True
    if not previous.phash or not frame.phash:
        return False
    try:
        return hamming_distance(previous.phash, frame.phash) >= PHASH_CUT_DISTANCE
    except ValueError:
        return False


def _build_shot(
    *,
    shot_index: int,
    frames: list[FrameRow],
    next_start_ms: int | None,
    ad_duration_ms: int | None,
    frame_interval_ms: int,
    transcript: list[TranscriptRow],
    ocr_by_frame: dict[int, list[OCRRow]],
) -> StoryboardShot:
    first = frames[0]
    start_ms = first.time_ms
    end_ms = _shot_end_ms(frames, next_start_ms, ad_duration_ms, frame_interval_ms)
    shot_ocr = [
        item
        for frame in frames
        for item in ocr_by_frame.get(frame.frame_index, [])
        if item.text.strip()
    ]
    on_screen_text = _dedupe_text(item.text for item in shot_ocr)
    voice_segments = [
        segment for segment in transcript if segment.start_ms < end_ms and segment.end_ms > start_ms
    ]
    voiceover = _join_text(segment.text for segment in voice_segments)
    narrative_function = _narrative_function(shot_index, next_start_ms is None, on_screen_text, voiceover)
    emotional_beat = _emotional_beat(on_screen_text, voiceover)

    evidence: list[EvidenceItem] = [
        EvidenceItem(
            time_ms=start_ms,
            frame_index=first.frame_index,
            source="visual",
            text=f"Shot {shot_index + 1} starts at frame {first.frame_index}.",
            reason="Representative frame selected from chronological frame order.",
        )
    ]
    if shot_ocr:
        first_ocr = shot_ocr[0]
        evidence.append(
            EvidenceItem(
                time_ms=first_ocr.time_ms,
                frame_index=first_ocr.frame_index,
                source="ocr",
                text=first_ocr.text,
                confidence=first_ocr.confidence,
                reason=f"Visible text from {first_ocr.engine}.",
            )
        )
    if voice_segments:
        first_voice = voice_segments[0]
        evidence.append(
            EvidenceItem(
                time_ms=first_voice.start_ms,
                frame_index=None,
                source="transcript",
                text=first_voice.text,
                confidence=first_voice.confidence,
                reason="Voiceover segment overlaps the shot window.",
            )
        )

    return StoryboardShot(
        shot_index=shot_index,
        start_ms=start_ms,
        end_ms=end_ms,
        duration_ms=max(0, end_ms - start_ms),
        representative_frame_index=first.frame_index,
        representative_frame_path=first.path,
        transition="cut" if shot_index > 0 else "start",
        camera_motion=_camera_motion(frames),
        shot_type=_shot_type(on_screen_text, next_start_ms is None),
        camera_angle="undetermined_from_stored_evidence",
        on_screen_text=on_screen_text,
        voiceover=voiceover or None,
        emotional_beat=emotional_beat,
        narrative_function=narrative_function,
        evidence=evidence,
    )


def _shot_end_ms(
    frames: list[FrameRow],
    next_start_ms: int | None,
    ad_duration_ms: int | None,
    frame_interval_ms: int,
) -> int:
    last_end = frames[-1].time_ms + frame_interval_ms
    if next_start_ms is not None:
        return max(frames[0].time_ms, next_start_ms)
    if ad_duration_ms is not None:
        return max(last_end, ad_duration_ms)
    return last_end


def _camera_motion(frames: list[FrameRow]) -> str:
    distances = []
    for left, right in zip(frames, frames[1:], strict=False):
        if not left.phash or not right.phash:
            continue
        try:
            distances.append(hamming_distance(left.phash, right.phash))
        except ValueError:
            continue
    if not distances:
        return "insufficient_visual_motion_evidence"
    average = sum(distances) / len(distances)
    if average <= 2:
        return "static_or_locked_off"
    if average <= 8:
        return "subtle_motion"
    return "high_visual_change"


def _shot_type(on_screen_text: list[str], is_last: bool) -> str:
    text = " ".join(on_screen_text).lower()
    if is_last and _contains_any(text, {"call", "shop", "visit", "learn", "apply", "order", "save"}):
        return "end_card_or_cta"
    if _contains_any(text, {"$", "%", "apr", "off", "deal", "offer", "sale", "save"}):
        return "offer_or_price_card"
    if on_screen_text:
        return "text_driven_scene"
    return "visual_scene"


def _narrative_function(
    shot_index: int,
    is_last: bool,
    on_screen_text: list[str],
    voiceover: str,
) -> str:
    text = f"{' '.join(on_screen_text)} {voiceover}".lower()
    if shot_index == 0:
        return "hook_or_opening_setup"
    if is_last and _contains_any(text, {"call", "shop", "visit", "learn", "order", "apply"}):
        return "cta_or_resolution"
    if _contains_any(text, {"$", "%", "apr", "off", "deal", "offer", "sale", "save"}):
        return "offer_reveal"
    if _contains_any(text, {"rated", "review", "testimonial", "trusted", "guarantee"}):
        return "proof_point"
    return "supporting_detail"


def _emotional_beat(on_screen_text: list[str], voiceover: str) -> str:
    text = f"{' '.join(on_screen_text)} {voiceover}".lower()
    if _contains_any(text, {"limited", "ends", "now", "today", "hurry"}):
        return "urgency"
    if _contains_any(text, {"save", "deal", "offer", "sale", "$", "%", "apr"}):
        return "value"
    if _contains_any(text, {"trusted", "rated", "review", "guarantee"}):
        return "trust"
    return "informative"


def _contains_any(text: str, needles: set[str]) -> bool:
    return any(needle in text for needle in needles)


def _dedupe_text(values) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for raw in values:
        text = " ".join(str(raw).split())
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            results.append(text)
    return results[:12]


def _join_text(values) -> str:
    return " ".join(_dedupe_text(values))


def _storyboard_html(storyboard: Storyboard) -> str:
    rows = "\n".join(_shot_html(shot) for shot in storyboard.shots)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>ARGUS Storyboard - {html.escape(storyboard.ad_id)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 32px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ text-align: left; background: #f3f4f6; }}
    img {{ width: 160px; max-height: 100px; object-fit: contain; background: #111827; }}
    .meta {{ color: #4b5563; }}
  </style>
</head>
<body>
  <h1>{html.escape(storyboard.ad_id)} Storyboard</h1>
  <p class="meta">Generated by {html.escape(storyboard.method)}.</p>
  <table>
    <thead>
      <tr>
        <th>Shot</th>
        <th>Frame</th>
        <th>Timing</th>
        <th>Transition</th>
        <th>Text</th>
        <th>Voiceover</th>
        <th>Beat</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""


def _shot_html(shot: StoryboardShot) -> str:
    src = _image_src(shot.representative_frame_path)
    image = f'<img src="{html.escape(src)}" alt="" />' if src else ""
    text = "<br />".join(html.escape(value) for value in shot.on_screen_text) or "-"
    return (
        "<tr>"
        f"<td>{shot.shot_index + 1}</td>"
        f"<td>{image}</td>"
        f"<td>{shot.start_ms}-{shot.end_ms} ms</td>"
        f"<td>{html.escape(shot.transition)}</td>"
        f"<td>{text}</td>"
        f"<td>{html.escape(shot.voiceover or '-')}</td>"
        f"<td>{html.escape(shot.emotional_beat)}<br />"
        f"{html.escape(shot.narrative_function)}</td>"
        "</tr>"
    )


def _image_src(path: str | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists():
        return ""
    return candidate.resolve().as_uri()
