from __future__ import annotations

from ad_classifier.search.visual_query import expand_visual_query_texts, mean_pool


def test_expand_visual_query_keeps_original_and_adds_aliases():
    terms = expand_visual_query_texts("red car")

    assert terms[0] == "red car"
    assert "automobile" in terms
    assert "red colored car" in terms


def test_mean_pool_vectors():
    assert mean_pool([[1.0, 3.0], [3.0, 5.0]]) == [2.0, 4.0]
