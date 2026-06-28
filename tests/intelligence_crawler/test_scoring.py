from __future__ import annotations

from ad_classifier.intelligence_crawler.config import ScoringConfig
from ad_classifier.intelligence_crawler.models import RawSourceItem
from ad_classifier.intelligence_crawler.scoring import (
    ad_likelihood,
    is_ad_signal_candidate,
    score_signal,
)

CONFIG = ScoringConfig()


def _video(title: str = "", description: str = "", duration_ms: int | None = None) -> RawSourceItem:
    return RawSourceItem(
        external_id="v",
        url="https://u",
        resource_type="video",
        title=title,
        description=description,
        duration_ms=duration_ms,
    )


def test_keyword_video_is_ad_like():
    score, _ = ad_likelihood(_video(title="Camry Reborn official commercial"), CONFIG)
    assert score >= 0.5
    assert is_ad_signal_candidate(_video(title="official commercial"), CONFIG) is True


def test_generic_video_without_keyword_or_duration_is_filtered():
    item = _video(title="2026 RAV4 full walkaround")
    score, _ = ad_likelihood(item, CONFIG)
    assert score < CONFIG.min_ad_likelihood
    assert is_ad_signal_candidate(item, CONFIG) is False


def test_short_duration_passes_even_without_keyword():
    item = _video(title="RAV4 review clip", duration_ms=30_000)  # 30s
    score, breakdown = ad_likelihood(item, CONFIG)
    assert breakdown["duration_class"] == "ad_typical"
    assert score >= 0.5
    assert is_ad_signal_candidate(item, CONFIG) is True


def test_long_duration_vetoes_keyword():
    # 10-minute "official walkaround": keyword present, but long-form → not an ad.
    item = _video(title="official RAV4 walkaround", duration_ms=600_000)
    score, breakdown = ad_likelihood(item, CONFIG)
    assert breakdown["duration_class"] == "long_form"
    assert score < CONFIG.min_ad_likelihood
    assert is_ad_signal_candidate(item, CONFIG) is False


def test_press_items_always_pass_the_gate():
    press = RawSourceItem(
        external_id="p", url="https://u", resource_type="press", title="quarterly earnings"
    )
    assert is_ad_signal_candidate(press, CONFIG) is True


def test_score_signal_uses_continuous_ad_bonus():
    strong = _video(title="official commercial", duration_ms=30_000)  # likelihood 1.0
    weak = _video(title="company news update")  # likelihood 0.0
    c_strong, _, b_strong = score_signal(
        tier="A", item=strong, corroborating_count=0, config=CONFIG
    )
    c_weak, _, _ = score_signal(tier="A", item=weak, corroborating_count=0, config=CONFIG)
    assert c_strong > c_weak
    assert b_strong["ad_likelihood"] == 1.0
