from __future__ import annotations


def rrf_fuse(
    *ranked_lists: list[str],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion over multiple ranked lists of ad_ids.

    Returns (ad_id, rrf_score) sorted descending by score.
    k=60 is the standard RRF constant that dampens high-rank differences.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, ad_id in enumerate(ranked, start=1):
            scores[ad_id] = scores.get(ad_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
