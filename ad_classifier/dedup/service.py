from __future__ import annotations

import sqlite3
from pathlib import Path

from ad_classifier.config import DedupConfig
from ad_classifier.db.repositories import AdRepository
from ad_classifier.dedup.file_hash import source_sha256
from ad_classifier.dedup.models import DedupResult, ExactDuplicateMatch, NearDuplicateMatch
from ad_classifier.dedup.phash import mean_phash


class DedupService:
    def __init__(self, *, conn: sqlite3.Connection, config: DedupConfig) -> None:
        self.conn = conn
        self.config = config
        self.ads = AdRepository(conn)

    def check_exact(
        self,
        *,
        source_hash: str,
        exclude_ad_id: str | None = None,
    ) -> ExactDuplicateMatch | None:
        ad = self.ads.find_by_source_hash(source_hash, exclude_ad_id=exclude_ad_id)
        if ad is None:
            return None
        return ExactDuplicateMatch(ad_id=ad.id, source_hash=source_hash)

    def check_near(
        self,
        *,
        phash_mean: str,
        exclude_ad_id: str | None = None,
    ) -> NearDuplicateMatch | None:
        match = self.ads.find_nearest_phash(phash_mean, exclude_ad_id=exclude_ad_id)
        if match is None:
            return None
        ad, distance = match
        if distance > self.config.phash_distance_threshold:
            return None
        if ad.phash_mean is None:
            return None
        return NearDuplicateMatch(ad_id=ad.id, phash_mean=ad.phash_mean, distance=distance)


def check_video_file(
    *,
    conn: sqlite3.Connection,
    config: DedupConfig,
    video_path: Path,
    exclude_ad_id: str | None = None,
) -> DedupResult:
    file_hash = source_sha256(video_path)
    exact = DedupService(conn=conn, config=config).check_exact(
        source_hash=file_hash,
        exclude_ad_id=exclude_ad_id,
    )
    return DedupResult(
        source_hash=file_hash,
        exact_duplicate_of=exact.ad_id if exact else None,
        skipped=exact is not None and config.skip_on_exact,
        skip_reason="exact_duplicate" if exact is not None and config.skip_on_exact else None,
    )


def check_frame_phashes(
    *,
    conn: sqlite3.Connection,
    config: DedupConfig,
    frame_paths: list[Path],
    exclude_ad_id: str | None = None,
    source_hash: str | None = None,
) -> DedupResult:
    phash_value = mean_phash(frame_paths)
    if phash_value is None:
        return DedupResult(source_hash=source_hash)

    near = DedupService(conn=conn, config=config).check_near(
        phash_mean=phash_value,
        exclude_ad_id=exclude_ad_id,
    )
    return DedupResult(
        source_hash=source_hash,
        phash_mean=phash_value,
        near_duplicate_of=near.ad_id if near else None,
        phash_distance=near.distance if near else None,
        skipped=near is not None and config.skip_on_near_duplicate,
        skip_reason=(
            "near_duplicate" if near is not None and config.skip_on_near_duplicate else None
        ),
    )
