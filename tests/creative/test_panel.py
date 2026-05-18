from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ad_classifier.agent.client import AgentMessage, MockAgentClient
from ad_classifier.creative.panel import build_creative_debate, build_creative_panel
from ad_classifier.creative.panel.service import PERSONAS, _persona_messages
from ad_classifier.db.connection import initialize_database, open_database
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.models.classification import ClassificationRecord
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import CTAEntity, MarketingEntities, OfferEntity, PriceEntity


def _conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "panel.db"
    initialize_database(db_path)
    return open_database(db_path)


def test_creative_panel_generates_grounded_persona_reactions(tmp_path: Path):
    conn = _conn(tmp_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name, products_text,
                primary_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_panel",
                "/tmp/panel.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        evidence = EvidenceItem(
            time_ms=500,
            frame_index=1,
            source="ocr",
            text="0% APR for 72 months",
        )
        MarketingEntityRepository(conn).upsert(
            "ad_panel",
            MarketingEntities(
                products=["Wrangler"],
                offers=[OfferEntity(text="0% APR for 72 months", evidence=[evidence])],
                prices=[PriceEntity(text="$399/month", evidence=[evidence])],
                ctas=[CTAEntity(text="Shop now", evidence=[evidence])],
            ),
        )
        ClassificationRepository(conn).upsert(
            ClassificationRecord(
                ad_id="ad_panel",
                primary_category="automotive",
                risk_labels=["urgency_pressure"],
                confidence=0.88,
                evidence=[evidence],
                vlm_model="mock",
                vlm_prompt_version="test",
                embedder_text_model="mock",
                embedder_visual_model="mock",
                pipeline_version="test",
            )
        )
        conn.commit()

        report = build_creative_panel(
            conn,
            "ad_panel",
            tmp_path / "out",
            persona_ids=["budget_parent", "compliance_reviewer"],
        )

        assert report.report_type == "simulated_creative_review"
        assert "not a real focus group" in report.caveat
        assert [reaction.persona_id for reaction in report.personas] == [
            "budget_parent",
            "compliance_reviewer",
        ]
        assert report.personas[0].citations[0].ad_id == "ad_panel"
        assert report.moderator_summary.strongest_hooks[0] == "0% APR for 72 months"
        assert Path(report.json_path).exists()
    finally:
        conn.close()


def test_creative_debate_generates_argument_sections(tmp_path: Path):
    conn = _conn(tmp_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name, products_text,
                primary_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_debate",
                "/tmp/debate.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        evidence = EvidenceItem(
            time_ms=750,
            frame_index=2,
            source="ocr",
            text="0% APR for 72 months",
        )
        MarketingEntityRepository(conn).upsert(
            "ad_debate",
            MarketingEntities(
                products=["Wrangler"],
                offers=[OfferEntity(text="0% APR for 72 months", evidence=[evidence])],
                ctas=[CTAEntity(text="Shop now", evidence=[evidence])],
            ),
        )
        conn.commit()

        report = build_creative_debate(
            conn,
            "ad_debate",
            tmp_path / "out",
            persona_ids=["budget_parent", "skeptical_buyer"],
            topic="Should the ad lead with financing or proof?",
        )

        assert report.report_type == "simulated_creative_debate"
        assert report.topic == "Should the ad lead with financing or proof?"
        assert [item.persona_id for item in report.participants] == [
            "budget_parent",
            "skeptical_buyer",
        ]
        assert report.opening_statements
        assert report.cross_examination
        assert report.closing_statements
        assert report.tensions[0].axis == "Value vs proof"
        assert report.scorecard.recommended_tests
        assert Path(report.json_path).exists()
    finally:
        conn.close()


def test_creative_panel_uses_vlm_when_client_is_provided(tmp_path: Path):
    conn = _conn(tmp_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name, products_text,
                primary_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_panel_vlm",
                "/tmp/panel.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        evidence = EvidenceItem(time_ms=500, frame_index=1, source="ocr", text="0% APR")
        MarketingEntityRepository(conn).upsert(
            "ad_panel_vlm",
            MarketingEntities(
                products=["Wrangler"],
                offers=[OfferEntity(text="0% APR", evidence=[evidence])],
                ctas=[CTAEntity(text="Shop now", evidence=[evidence])],
            ),
        )
        conn.commit()
        client = MockAgentClient(
            [
                AgentMessage(
                    content=(
                        '{"persona_id":"budget_parent",'
                        '"first_impression":"The VLM sees the offer first.",'
                        '"understood_product_or_offer":"Wrangler financing.",'
                        '"emotional_reaction":"Value interest.",'
                        '"trust_points":["Specific financing text."],'
                        '"confusion_points":["Need terms."],'
                        '"likely_objection":"What is the full cost?",'
                        '"memorable_moment":"0% APR",'
                        '"cta_likelihood":"Would consider clicking; not a forecast.",'
                        '"citation_ids":["c0"]}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                ),
                AgentMessage(
                    content=(
                        '{"consensus":["Offer leads."],'
                        '"disagreements":[],"message_clarity_issues":["Need terms."],'
                        '"strongest_hooks":["0% APR"],'
                        '"suggested_ab_variants":["Test offer-first opening."]}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                ),
            ]
        )

        report = build_creative_panel(
            conn,
            "ad_panel_vlm",
            tmp_path / "out",
            persona_ids=["budget_parent"],
            use_vlm=True,
            llm_client=client,
            source_model="mock-vlm",
            thinking=True,
        )

        assert report.analysis_source == "vlm"
        assert report.source_model == "mock-vlm"
        assert report.personas[0].first_impression == "The VLM sees the offer first."
        assert report.personas[0].citations[0].text == "0% APR"
        assert client.calls[0]["enable_thinking"] is True
        assert len(client.calls) == 2
    finally:
        conn.close()


def test_creative_debate_uses_vlm_with_reasoning(tmp_path: Path):
    conn = _conn(tmp_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name, products_text,
                primary_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_debate_vlm",
                "/tmp/debate.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        evidence = EvidenceItem(time_ms=500, frame_index=1, source="ocr", text="0% APR")
        MarketingEntityRepository(conn).upsert(
            "ad_debate_vlm",
            MarketingEntities(
                products=["Wrangler"],
                offers=[OfferEntity(text="0% APR", evidence=[evidence])],
                ctas=[CTAEntity(text="Shop now", evidence=[evidence])],
            ),
        )
        conn.commit()
        client = MockAgentClient(
            [
                AgentMessage(
                    content=(
                        '{"opening_statements":[{"speaker_persona_id":"budget_parent",'
                        '"stance":"advocate","claim":"Lead with the financing hook.",'
                        '"evidence_read":"0% APR is explicit.","pressure_test":"Terms must be clear.",'
                        '"citation_ids":["c0"]}],'
                        '"cross_examination":[{"speaker_persona_id":"skeptical_buyer",'
                        '"target_persona_id":"budget_parent","stance":"skeptic",'
                        '"claim":"The offer needs proof before it persuades.",'
                        '"evidence_read":"Only the hook is visible.","pressure_test":"Where are the terms?",'
                        '"citation_ids":["c0"]}],'
                        '"closing_statements":[{"speaker_persona_id":"budget_parent",'
                        '"stance":"advocate","claim":"Keep the offer, clarify the terms.",'
                        '"evidence_read":"0% APR is memorable.","pressure_test":"Can shoppers verify it?",'
                        '"citation_ids":["c0"]}],'
                        '"tensions":[{"axis":"Offer vs terms","advocate":"0% APR is strong.",'
                        '"skeptic":"Terms need visibility.","moderator_take":"Pair the hook with terms."}],'
                        '"scorecard":{"moderator_verdict":"Offer wins if terms are readable.",'
                        '"strongest_argument":"0% APR is explicit.",'
                        '"weakest_argument":"Terms are unresolved.",'
                        '"unresolved_questions":["What are the terms?"],'
                        '"recommended_tests":["Test offer-first with term card."]},'
                        '"moderator_summary":{"consensus":["Offer is clear."],'
                        '"disagreements":["Proof level differs."],'
                        '"message_clarity_issues":["Terms need clarity."],'
                        '"strongest_hooks":["0% APR"],'
                        '"suggested_ab_variants":["Test offer-first with terms."]}}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                )
            ]
        )

        report = build_creative_debate(
            conn,
            "ad_debate_vlm",
            tmp_path / "out",
            persona_ids=["budget_parent", "skeptical_buyer"],
            use_vlm=True,
            llm_client=client,
            source_model="mock-vlm",
            thinking=True,
        )

        assert report.analysis_source == "vlm"
        assert report.source_model == "mock-vlm"
        assert report.opening_statements[0].claim == "Lead with the financing hook."
        assert report.cross_examination[0].target_persona_id == "budget_parent"
        assert report.scorecard.moderator_verdict == "Offer wins if terms are readable."
        assert client.calls[0]["enable_thinking"] is True
    finally:
        conn.close()


def test_creative_debate_retries_compact_without_reasoning_after_length(tmp_path: Path):
    conn = _conn(tmp_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name, products_text,
                primary_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_debate_length",
                "/tmp/debate.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        evidence = EvidenceItem(time_ms=500, frame_index=1, source="ocr", text="0% APR")
        MarketingEntityRepository(conn).upsert(
            "ad_debate_length",
            MarketingEntities(
                products=["Wrangler"],
                offers=[OfferEntity(text="0% APR", evidence=[evidence])],
                ctas=[CTAEntity(text="Shop now", evidence=[evidence])],
            ),
        )
        conn.commit()
        client = MockAgentClient(
            [
                AgentMessage(
                    content='{"opening_statements":[{"speaker_persona_id":"budget_parent"',
                    tool_calls=[],
                    finish_reason="length",
                ),
                AgentMessage(
                    content=(
                        '{"opening_statements":[{"speaker_persona_id":"budget_parent",'
                        '"stance":"advocate","claim":"Lead with APR.",'
                        '"evidence_read":"APR is visible.","pressure_test":"Clarify terms.",'
                        '"citation_ids":["c0"]}],'
                        '"cross_examination":[{"speaker_persona_id":"skeptical_buyer",'
                        '"target_persona_id":"budget_parent","stance":"skeptic",'
                        '"claim":"Terms remain thin.","evidence_read":"Only APR appears.",'
                        '"pressure_test":"Show conditions.","citation_ids":["c0"]}],'
                        '"closing_statements":[{"speaker_persona_id":"budget_parent",'
                        '"stance":"advocate","claim":"Keep hook concise.",'
                        '"evidence_read":"APR anchors recall.","pressure_test":"Add terms.",'
                        '"citation_ids":["c0"]}],'
                        '"tensions":[{"axis":"Hook vs terms","advocate":"APR is strong.",'
                        '"skeptic":"Terms are missing.","moderator_take":"Pair hook with terms."}],'
                        '"scorecard":{"moderator_verdict":"Retry produced compact debate.",'
                        '"strongest_argument":"APR is explicit.",'
                        '"weakest_argument":"Terms remain thin.",'
                        '"unresolved_questions":["What terms apply?"],'
                        '"recommended_tests":["Test compact term card."]},'
                        '"moderator_summary":{"consensus":["Offer hook is clear."],'
                        '"disagreements":["Proof depth differs."],'
                        '"message_clarity_issues":["Terms need clarity."],'
                        '"strongest_hooks":["0% APR"],'
                        '"suggested_ab_variants":["Test terms card."]}}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                ),
            ]
        )

        report = build_creative_debate(
            conn,
            "ad_debate_length",
            tmp_path / "out",
            persona_ids=["budget_parent", "skeptical_buyer"],
            use_vlm=True,
            llm_client=client,
            source_model="mock-vlm",
            thinking=True,
        )

        assert report.analysis_source == "vlm"
        assert report.fallback_error is None
        assert report.scorecard.moderator_verdict == "Retry produced compact debate."
        assert [call["enable_thinking"] for call in client.calls] == [True, False]
        assert "prior response exceeded the token budget" in client.calls[1]["messages"][0]["content"]
    finally:
        conn.close()


def test_persona_prompt_requires_internal_evidence_reasoning():
    class Context:
        ad_id = "ad_prompt"
        brand = "Jeep"
        category = "automotive"
        products = ["Wrangler"]
        offers = ["0% APR"]
        prices = []
        ctas = ["Shop now"]
        risk_labels = []
        transcript_text = "Shop now for Wrangler"
        ocr_texts = ["0% APR", "Shop now"]
        citations = []

    messages = _persona_messages(PERSONAS["budget_parent"], Context())  # type: ignore[arg-type]
    system = messages[0]["content"]

    assert "Internally reason" in system
    assert "Do not reveal chain-of-thought" in system
    assert "Use only supplied evidence" in system
    assert "Ignore repetitive OCR boilerplate" in system


def test_creative_panel_falls_back_when_vlm_hits_length(tmp_path: Path):
    conn = _conn(tmp_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name, products_text,
                primary_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_panel_length",
                "/tmp/panel.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        evidence = EvidenceItem(time_ms=500, frame_index=1, source="ocr", text="0% APR")
        MarketingEntityRepository(conn).upsert(
            "ad_panel_length",
            MarketingEntities(
                products=["Wrangler"],
                offers=[OfferEntity(text="0% APR", evidence=[evidence])],
            ),
        )
        conn.commit()
        client = MockAgentClient(
            [
                AgentMessage(
                    content='{"persona_id":"budget_parent","first_impression":"unfinished"',
                    tool_calls=[],
                    finish_reason="length",
                ),
                AgentMessage(
                    content='{"consensus":["fallback summary not enough"]}',
                    tool_calls=[],
                    finish_reason="stop",
                ),
            ]
        )

        report = build_creative_panel(
            conn,
            "ad_panel_length",
            tmp_path / "out",
            persona_ids=["budget_parent"],
            use_vlm=True,
            llm_client=client,
            source_model="mock-vlm",
        )

        assert report.analysis_source == "vlm_with_fallback"
        assert report.personas[0].first_impression.startswith("The ad reads as")
        assert report.moderator_summary.consensus == ["fallback summary not enough"]
    finally:
        conn.close()
