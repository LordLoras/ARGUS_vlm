from __future__ import annotations

from ad_classifier.config import CampaignDiscoveryConfig
from ad_classifier.dedup.similarity import cosine_similarity


def cluster_vectors(vectors: list[list[float]], config: CampaignDiscoveryConfig) -> list[int]:
    if not vectors:
        return []
    if config.clusterer == "hdbscan":
        labels = _hdbscan_labels(vectors, config.min_cluster_size)
        if labels is not None:
            return labels
    return agglomerative_cluster_labels(
        vectors,
        min_cluster_size=config.min_cluster_size,
        min_similarity=config.min_mean_similarity,
    )


def agglomerative_cluster_labels(
    vectors: list[list[float]],
    *,
    min_cluster_size: int,
    min_similarity: float,
) -> list[int]:
    """Average-linkage agglomerative clustering over cosine similarity."""
    clusters: list[set[int]] = [{i} for i in range(len(vectors))]
    while len(clusters) > 1:
        best_pair: tuple[int, int] | None = None
        best_score = -1.0
        for left_idx in range(len(clusters)):
            for right_idx in range(left_idx + 1, len(clusters)):
                score = _cluster_similarity(clusters[left_idx], clusters[right_idx], vectors)
                if score > best_score:
                    best_score = score
                    best_pair = (left_idx, right_idx)

        if best_pair is None or best_score < min_similarity:
            break

        left_idx, right_idx = best_pair
        clusters[left_idx] = clusters[left_idx] | clusters[right_idx]
        del clusters[right_idx]

    labels = [-1 for _ in vectors]
    next_label = 0
    for cluster in sorted(clusters, key=lambda c: min(c)):
        if len(cluster) < min_cluster_size:
            continue
        for index in cluster:
            labels[index] = next_label
        next_label += 1
    return labels


def mean_pairwise_similarity(vectors: list[list[float]]) -> float:
    if len(vectors) < 2:
        return 1.0
    scores = [
        cosine_similarity(vectors[left], vectors[right])
        for left in range(len(vectors))
        for right in range(left + 1, len(vectors))
    ]
    return sum(scores) / len(scores)


def _hdbscan_labels(vectors: list[list[float]], min_cluster_size: int) -> list[int] | None:
    try:
        import hdbscan  # type: ignore[import-not-found]  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except Exception:
        return None

    distances = [
        [max(0.0, 1.0 - cosine_similarity(left, right)) for right in vectors] for left in vectors
    ]
    try:
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="precomputed")
        return [int(label) for label in clusterer.fit_predict(np.array(distances))]
    except Exception:
        return None


def _cluster_similarity(
    left: set[int],
    right: set[int],
    vectors: list[list[float]],
) -> float:
    scores = [
        cosine_similarity(vectors[left_idx], vectors[right_idx])
        for left_idx in left
        for right_idx in right
    ]
    return sum(scores) / len(scores)
