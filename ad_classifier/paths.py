from __future__ import annotations

import re
from pathlib import Path

AD_ID_RE = re.compile(r"^ad_[a-z0-9]{8}$")


def validate_ad_id(ad_id: str) -> str:
    if not AD_ID_RE.fullmatch(ad_id):
        raise ValueError(f"Invalid ad_id: {ad_id!r}")
    return ad_id


def validate_frame_index(frame_index: int) -> int:
    if frame_index < 0:
        raise ValueError("frame_index must be non-negative")
    return frame_index


def ensure_within_root(root: Path, candidate: Path) -> Path:
    resolved_root = root.expanduser().resolve()
    resolved_candidate = candidate.expanduser().resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ValueError(f"Path escapes configured root: {resolved_candidate}")
    return resolved_candidate


def ad_root(data_root: Path, ad_id: str) -> Path:
    return ensure_within_root(data_root, data_root / validate_ad_id(ad_id))


def ad_frame_path(data_root: Path, ad_id: str, frame_index: int) -> Path:
    validate_frame_index(frame_index)
    return ad_root(data_root, ad_id) / "frames" / f"frame_{frame_index:06d}.png"
