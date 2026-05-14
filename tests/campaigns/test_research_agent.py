from __future__ import annotations

from ad_classifier.agent.client import AgentMessage, MockAgentClient
from ad_classifier.campaigns.research_agent import answer_campaign_question


def _detail():
    return {
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


def test_local_campaign_question_fallback_handles_product_relationships():
    detail = _detail()

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


def test_local_campaign_question_fallback_handles_important_points():
    answer = answer_campaign_question(
        client=None,
        question="what are the most important things in this campaign",
        detail=_detail(),
        findings=[
            {
                "priority": "medium",
                "title": "Offer strategy is identifiable",
                "detail": "$299/mo appears in 2 of 2 assigned ads.",
                "evidence_ad_ids": ["ad_a", "ad_b"],
            }
        ],
        creative_review=[],
        assignment_review={"outliers": []},
        suggested_edits=[],
    )

    assert answer is not None
    assert answer["source"] == "local"
    assert "Most important local campaign points" in answer["answer"]
    assert "$299/mo appears" in answer["answer"]


def test_campaign_question_retries_without_thinking_when_length_empty():
    client = MockAgentClient(
        [
            AgentMessage(content="", tool_calls=[], finish_reason="length"),
            AgentMessage(content="Products are variants in the same Jeep campaign.", tool_calls=[], finish_reason="stop"),
        ]
    )

    answer = answer_campaign_question(
        client=client,
        question="what are the most important things in this campaign",
        detail=_detail(),
        findings=[],
        creative_review=[],
        assignment_review={"outliers": []},
        suggested_edits=[],
        thinking=True,
    )

    assert answer is not None
    assert answer["source"] == "llm"
    assert answer["answer"] == "Products are variants in the same Jeep campaign."
    assert [call["enable_thinking"] for call in client.calls] == [True, False]
