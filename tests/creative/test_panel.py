from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

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
