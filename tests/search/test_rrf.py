from __future__ import annotations

from ad_classifier.search.rrf import rrf_fuse


def test_single_list_preserves_order():
    ids = ["a", "b", "c", "d"]
    result = rrf_fuse(ids)
    out_ids = [r[0] for r in result]
    assert out_ids == ids


def test_two_lists_boosts_overlap():
    list1 = ["a", "b", "c"]
    list2 = ["b", "d", "e"]
    result = rrf_fuse(list1, list2)
    scores = {r[0]: r[1] for r in result}
    # "b" appears in both lists so should have a higher score than "a" or "d"
    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["d"]


def test_higher_rank_means_higher_score():
    ids = ["first", "second", "third"]
    result = rrf_fuse(ids)
    scores = {r[0]: r[1] for r in result}
    assert scores["first"] > scores["second"] > scores["third"]


def test_empty_list_returns_empty():
    assert rrf_fuse([]) == []


def test_three_lists():
    l1 = ["x", "y", "z"]
    l2 = ["y", "z", "w"]
    l3 = ["z", "w", "x"]
    result = rrf_fuse(l1, l2, l3)
    scores = {r[0]: r[1] for r in result}
    # z appears in all 3 lists at positions 3, 2, 1 — should dominate
    assert scores["z"] == max(scores.values())


def test_result_sorted_descending():
    result = rrf_fuse(["a", "b", "c"], ["b", "a", "d"])
    scores = [r[1] for r in result]
    assert scores == sorted(scores, reverse=True)


def test_custom_k():
    result = rrf_fuse(["a", "b"], k=1)
    # With k=1, rank 1 → score 1/(1+1)=0.5
    assert abs(result[0][1] - 0.5) < 1e-9
