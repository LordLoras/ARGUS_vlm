from __future__ import annotations

from pydantic import Field

from ad_classifier.models.common import StrictModel


class ExactDuplicateMatch(StrictModel):
    ad_id: str
    source_hash: str


class NearDuplicateMatch(StrictModel):
    ad_id: str
    phash_mean: str
    distance: int = Field(ge=0)


class DedupResult(StrictModel):
    source_hash: str | None = None
    phash_mean: str | None = None
    exact_duplicate_of: str | None = None
    near_duplicate_of: str | None = None
    phash_distance: int | None = Field(default=None, ge=0)
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def is_duplicate(self) -> bool:
        return self.exact_duplicate_of is not None or self.near_duplicate_of is not None
