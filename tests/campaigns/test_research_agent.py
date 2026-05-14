from __future__ import annotations

from ad_classifier.campaigns.research_agent import answer_campaign_question


def test_local_campaign_question_fallback_handles_product_relationships():
    detail = {
        "campaign": {"id": "c_test", "name": "Test Campaign"},
        "ads": [
            {"ad_id": "ad_a", "products": ["Wrangler"], "offers": ["$299/mo"]},
            {"ad_id": "ad_b", "products": ["Grand Cherokee"], "offers": ["$299/mo"]},
        ],
        "research": {
            "summary": {
                "brands": [{"value": "Jeep", "count": 2, "share": 1.0}],
                "categories": [{"value": "automotive", "count": 2, "share": 1.0}],
            },
            "messaging": {
                "top_products": [
                    {"value": "Wrangler", "count": 1, "share": 0.5},
                    {"value": "Grand Cherokee", "count": 1, "share": 0.5},
                ],
                "top_offers": [{"value": "$299/mo", "count": 2, "share": 1.0}],
                "top_ctas": [],
            },
            "creative": {
                "disclaimer_ads": 0,
                "small_print_ads": 0,
            },
            "watchouts": {"small_print_count": 0},
        },
    }

    answer = answer_campaign_question(
        client=None,
        question="how are the products in this campaign related",
        detail=detail,
        findings=[],
        creative_review=[],
        assignment_review={"outliers": []},
        suggested_edits=[],
    )

    assert answer is not None
    assert answer["source"] == "local"
    assert "shared brand signal Jeep" in answer["answer"]
    assert answer["evidence_ad_ids"] == ["ad_a", "ad_b"]
