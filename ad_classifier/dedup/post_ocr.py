from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher

from ad_classifier.config import PostOCRDedupConfig
from ad_classifier.dedup.models import PostOCRDuplicateMatch, PostOCRDuplicateVerdict
from ad_classifier.dedup.phash import hamming_distance

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_VALUE_RE = re.compile(
    r"(?:\$\s*)?\d+(?:[,.]\d+)*(?:\.\d+)?\s*(?:%|percent|apr|mo|mos|month|months|day|days|yr|year|years)?"
)
_COMMERCIAL_KEYWORDS = {
    "apr",
    "allowance",
    "bonus",
    "cash",
    "discount",
    "due",
    "finance",
    "financing",
    "free",
    "lease",
    "lessee",
    "lessees",
    "month",
    "monthly",
    "months",
    "offer",
    "offers",
    "payment",
    "payments",
    "price",
    "save",
    "signing",
    "tax",
}


@dataclass(frozen=True)
class _FrameHash:
    frame_index: int
    time_ms: int
    phash: str


@dataclass(frozen=True)
class _Fingerprint:
    ad_id: str
    duration_ms: int | None
    phash_mean: str | None
    frames: list[_FrameHash]
    ocr_text: str
    transcript_text: str
    text_chars: int
    signature_tokens: set[str]


@dataclass(frozen=True)
class _CandidateRow:
    ad_id: str
    duration_ms: int | None
    phash_mean: str | None
    phash_distance: int | None


def find_post_ocr_duplicate(
    conn: sqlite3.Connection,
    ad_id: str,
    config: PostOCRDedupConfig,
) -> PostOCRDuplicateMatch | None:
    if not config.enabled:
        return None

    current = _load_fingerprint(conn, ad_id)
    if current is None:
        return None

    best_exact: PostOCRDuplicateMatch | None = None
    best_related: PostOCRDuplicateMatch | None = None
    for candidate_row in _candidate_rows(conn, current, config):
        candidate = _load_fingerprint(conn, candidate_row.ad_id)
        if candidate is None:
            continue
        match = _compare(current, candidate, config, candidate_row.phash_distance)
        if match.verdict == "exact_duplicate":
            if best_exact is None or match.overall_score > best_exact.overall_score:
                best_exact = match
        elif match.verdict != "related" and (
            best_related is None or match.overall_score > best_related.overall_score
        ):
            best_related = match

    return best_exact or best_related


def _candidate_rows(
    conn: sqlite3.Connection,
    current: _Fingerprint,
    config: PostOCRDedupConfig,
) -> list[_CandidateRow]:
    rows = conn.execute(
        """
        SELECT id, duration_ms, phash_mean
        FROM ads
        WHERE id <> ?
          AND status = 'completed'
          AND duplicate_of IS NULL
        """,
        (current.ad_id,),
    ).fetchall()
    candidates: list[_CandidateRow] = []
    for row in rows:
        duration_ms = row["duration_ms"]
        if (
            current.duration_ms is not None
            and duration_ms is not None
            and abs(int(current.duration_ms) - int(duration_ms)) > config.duration_tolerance_ms
        ):
            continue

        phash_distance: int | None = None
        candidate_phash = row["phash_mean"]
        if current.phash_mean and candidate_phash:
            try:
                phash_distance = hamming_distance(current.phash_mean, str(candidate_phash))
            except ValueError:
                continue
            if phash_distance > config.candidate_phash_distance:
                continue

        candidates.append(
            _CandidateRow(
                ad_id=str(row["id"]),
                duration_ms=int(duration_ms) if duration_ms is not None else None,
                phash_mean=str(candidate_phash) if candidate_phash else None,
                phash_distance=phash_distance,
            )
        )

    candidates.sort(key=lambda c: (c.phash_distance is None, c.phash_distance or 0, c.ad_id))
    return candidates[: config.max_candidates]


def _load_fingerprint(conn: sqlite3.Connection, ad_id: str) -> _Fingerprint | None:
    ad_row = conn.execute(
        "SELECT id, duration_ms, phash_mean FROM ads WHERE id = ?",
        (ad_id,),
    ).fetchone()
    if ad_row is None:
        return None

    frame_rows = conn.execute(
        """
        SELECT frame_index, time_ms, phash
        FROM frames
        WHERE ad_id = ?
          AND kept = 1
          AND phash IS NOT NULL
        ORDER BY frame_index
        """,
        (ad_id,),
    ).fetchall()
    frames = [
        _FrameHash(int(row["frame_index"]), int(row["time_ms"]), str(row["phash"]))
        for row in frame_rows
    ]

    ocr_rows = conn.execute(
        """
        SELECT o.text
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE f.ad_id = ?
        ORDER BY f.frame_index, o.id
        """,
        (ad_id,),
    ).fetchall()
    ocr_text = " ".join(str(row["text"]) for row in ocr_rows if row["text"])

    transcript_rows = conn.execute(
        """
        SELECT text
        FROM transcript_segments
        WHERE ad_id = ?
        ORDER BY start_ms, id
        """,
        (ad_id,),
    ).fetchall()
    transcript_text = " ".join(str(row["text"]) for row in transcript_rows if row["text"])
    full_text = f"{ocr_text} {transcript_text}"

    return _Fingerprint(
        ad_id=str(ad_row["id"]),
        duration_ms=int(ad_row["duration_ms"]) if ad_row["duration_ms"] is not None else None,
        phash_mean=str(ad_row["phash_mean"]) if ad_row["phash_mean"] else None,
        frames=frames,
        ocr_text=ocr_text,
        transcript_text=transcript_text,
        text_chars=len(_compact_text(full_text)),
        signature_tokens=_signature_tokens(full_text),
    )


def _compare(
    left: _Fingerprint,
    right: _Fingerprint,
    config: PostOCRDedupConfig,
    phash_distance: int | None,
) -> PostOCRDuplicateMatch:
    frame_ratio = _frame_match_ratio(left.frames, right.frames, config.per_frame_phash_distance)
    ocr_similarity = _text_similarity(left.ocr_text, right.ocr_text)
    transcript_similarity = _optional_text_similarity(left.transcript_text, right.transcript_text)
    signature_similarity = _jaccard(left.signature_tokens, right.signature_tokens)
    enough_text = min(left.text_chars, right.text_chars) >= config.min_text_chars
    verdict = _verdict(
        config=config,
        enough_text=enough_text,
        frame_ratio=frame_ratio,
        ocr_similarity=ocr_similarity,
        transcript_similarity=transcript_similarity,
        signature_similarity=signature_similarity,
    )
    overall = _bounded(
        (0.40 * frame_ratio)
        + (0.30 * ocr_similarity)
        + (0.15 * transcript_similarity)
        + (0.15 * signature_similarity)
    )
    return PostOCRDuplicateMatch(
        ad_id=right.ad_id,
        verdict=verdict,
        overall_score=overall,
        frame_match_ratio=frame_ratio,
        ocr_text_similarity=ocr_similarity,
        transcript_similarity=transcript_similarity,
        signature_similarity=signature_similarity,
        phash_distance=phash_distance,
    )


def _verdict(
    *,
    config: PostOCRDedupConfig,
    enough_text: bool,
    frame_ratio: float,
    ocr_similarity: float,
    transcript_similarity: float,
    signature_similarity: float,
) -> PostOCRDuplicateVerdict:
    frame_ok = frame_ratio >= config.min_frame_match_ratio
    ocr_ok = ocr_similarity >= config.min_text_similarity
    transcript_ok = transcript_similarity >= config.min_transcript_similarity
    signature_ok = signature_similarity >= config.min_signature_similarity
    if frame_ok and enough_text and ocr_ok and transcript_ok and signature_ok:
        return "exact_duplicate"
    if frame_ok and enough_text and not signature_ok:
        return "same_campaign_different_offer"
    if frame_ok and enough_text and (ocr_ok or transcript_ok):
        return "near_duplicate"
    return "related"


def _frame_match_ratio(
    left: list[_FrameHash],
    right: list[_FrameHash],
    per_frame_threshold: int,
) -> float:
    if not left or not right:
        return 0.0
    right_by_index = {frame.frame_index: frame for frame in right}
    distances: list[int] = []
    for left_frame in left:
        right_frame = right_by_index.get(left_frame.frame_index)
        if right_frame is None:
            continue
        try:
            distances.append(hamming_distance(left_frame.phash, right_frame.phash))
        except ValueError:
            continue
    if not distances:
        return 0.0
    matched = sum(1 for distance in distances if distance <= per_frame_threshold)
    coverage = len(distances) / max(min(len(left), len(right)), 1)
    return _bounded((matched / len(distances)) * coverage)


def _optional_text_similarity(left: str, right: str) -> float:
    if not _compact_text(left) and not _compact_text(right):
        return 1.0
    return _text_similarity(left, right)


def _text_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    left_text = " ".join(left_tokens)
    right_text = " ".join(right_tokens)
    sequence = SequenceMatcher(None, left_text, right_text).ratio()
    return max(sequence, _jaccard(_ngrams(left_tokens, 2), _ngrams(right_tokens, 2)))


def _signature_tokens(text: str) -> set[str]:
    normalized = _normalize_text(text)
    tokens = {f"value:{_compact_text(match.group(0))}" for match in _VALUE_RE.finditer(normalized)}
    words = _tokens(normalized)
    for index, word in enumerate(words):
        if word in _COMMERCIAL_KEYWORDS:
            tokens.add(f"term:{word}")
            window = words[max(0, index - 2) : index + 3]
            if len(window) >= 2:
                tokens.add(f"context:{' '.join(window)}")
    return tokens


def _ngrams(tokens: list[str], n: int) -> set[str]:
    if len(tokens) <= n:
        return set(tokens)
    return {" ".join(tokens[index : index + n]) for index in range(len(tokens) - n + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize_text(text))


def _normalize_text(text: str) -> str:
    return text.lower().replace("\n", " ")


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", _normalize_text(text))


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))
