from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ad_classifier.agent.client import AgentMessage, MockAgentClient
from ad_classifier.creative.panel import build_creative_panel
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
                        '{"personas":[{"persona_id":"budget_parent",'
                        '"first_impression":"The VLM sees the offer first.",'
                        '"understood_product_or_offer":"Wrangler financing.",'
                        '"emotional_reaction":"Value interest.",'
                        '"trust_points":["Specific financing text."],'
                        '"confusion_points":["Need terms."],'
                        '"likely_objection":"What is the full cost?",'
                        '"memorable_moment":"0% APR",'
                        '"cta_likelihood":"Would consider clicking; not a forecast.",'
                        '"citation_ids":["c0"]}],'
                        '"moderator_summary":{"consensus":["Offer leads."],'
                        '"disagreements":[],"message_clarity_issues":["Need terms."],'
                        '"strongest_hooks":["0% APR"],'
                        '"suggested_ab_variants":["Test offer-first opening."]}}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                )
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
        )

        assert report.analysis_source == "vlm"
        assert report.source_model == "mock-vlm"
        assert report.personas[0].first_impression == "The VLM sees the offer first."
        assert report.personas[0].citations[0].text == "0% APR"
        assert client.calls[0]["enable_thinking"] is False
    finally:
        conn.close()
