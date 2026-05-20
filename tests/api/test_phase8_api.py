from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ad_classifier.agent.client import AgentMessage, MockAgentClient
from ad_classifier.api.app import create_app
from ad_classifier.brand_profiles.wikimedia import BrandProfileNotFoundError
from ad_classifier.db.connection import load_sqlite_vec, open_database
from ad_classifier.db.repositories import JobRepository
from ad_classifier.db.repositories.brand_profiles import BrandProfileRepository
from ad_classifier.models.ads import utc_now
from ad_classifier.models.brand_profiles import BrandProfile, BrandProfileLookupStep
from ad_classifier.models.jobs import JobRecord
from ad_classifier.search.fts import fts_update
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    config = {
        "paths": {
            "data_root": str(data_root),
            "uploads": str(data_root / "uploads"),
            "frames": str(data_root / "frames"),
            "audio": str(data_root / "audio"),
            "whisper": str(data_root / "whisper"),
            "out": str(data_root / "out"),
            "sqlite_path": str(tmp_path / "api.db"),
        },
        "api": {
            "cors_origins": ["http://localhost:5173"],
            "upload": {"max_bytes": 1024 * 1024, "allowed_mime": ["video/mp4"]},
        },
        "worker": {"poll_interval_ms": 50},
        "vector_store": {"text_dim": 8, "visual_dim": 8},
        "campaigns": {"discover": {"clusterer": "agglomerative"}},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.fixture()
def client(config_path: Path) -> TestClient:
    def agent_client_factory(_config):
        return MockAgentClient(
            [
                AgentMessage(
                    content=(
                        '{"findings":[{"priority":"high","title":"LLM offer read",'
                        '"detail":"The LLM client identifies 0% APR as the main offer.",'
                        '"evidence_ad_ids":["ad_campaign"]}],'
                        '"creative_review":[{"area":"Direction","status":"present",'
                        '"detail":"The LLM client sees a clear Shop now CTA."}],'
                        '"suggested_edits":[{"field":"description",'
                        '"value":"Campaign centered on 0% APR.",'
                        '"reason":"LLM client summarized the offer."}],'
                        '"open_questions":["Which ad has the clearest offer hierarchy?"],'
                        '"question_answer":{"question":"How should we improve the offer?",'
                        '"answer":"The LLM client says to make 0% APR the lead message.",'
                        '"evidence_ad_ids":["ad_campaign"],'
                        '"limits":"Local campaign evidence only."}}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                )
            ]
        )

    def creative_panel_client_factory(_config):
        return MockAgentClient(
            [
                AgentMessage(
                    content=(
                        '{"persona_id":"budget_parent",'
                        '"first_impression":"The offer is easy to notice.",'
                        '"understood_product_or_offer":"Wrangler with 0% APR.",'
                        '"emotional_reaction":"Value interest.",'
                        '"trust_points":["The offer is specific."],'
                        '"confusion_points":["Terms still need clarity."],'
                        '"likely_objection":"I need total cost details.",'
                        '"memorable_moment":"0% APR",'
                        '"cta_likelihood":"Would consider the CTA; not a forecast.",'
                        '"citation_ids":["c0"]}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                ),
                AgentMessage(
                    content=(
                        '{"persona_id":"skeptical_buyer",'
                        '"first_impression":"The claim needs support.",'
                        '"understood_product_or_offer":"Wrangler financing offer.",'
                        '"emotional_reaction":"Cautious interest.",'
                        '"trust_points":["The CTA is direct."],'
                        '"confusion_points":["Offer terms are thin."],'
                        '"likely_objection":"I need proof and terms.",'
                        '"memorable_moment":"Shop now",'
                        '"cta_likelihood":"CTA depends on term clarity.",'
                        '"citation_ids":["c1"]}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                ),
                AgentMessage(
                    content=(
                        '{"consensus":["Offer is the clearest hook."],'
                        '"disagreements":["Value and proof lenses differ."],'
                        '"message_clarity_issues":["Terms need clarity."],'
                        '"strongest_hooks":["0% APR"],'
                        '"suggested_ab_variants":["Test offer-first copy."]}'
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                ),
            ]
        )

    app = create_app(
        config_path=config_path,
        upload_probe=lambda _path: object(),
        agent_client_factory=agent_client_factory,
        creative_panel_client_factory=creative_panel_client_factory,
    )
    return TestClient(app)


def _db(config_path: Path) -> sqlite3.Connection:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return open_database(Path(data["paths"]["sqlite_path"]))


def test_api_health_alias_supports_frontend_proxy(client: TestClient):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ad-classifier"}


def test_upload_queues_job_and_lists_ad(client: TestClient):
    response = client.post(
        "/api/ads/upload",
        files={"file": ("ad.mp4", b"fake mp4 bytes", "video/mp4")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ad_id"].startswith("ad_")
    assert payload["job_id"].startswith("job_")
    assert payload["state"] == "queued"

    job = client.get(f"/api/jobs/{payload['job_id']}")
    assert job.status_code == 200
    assert job.json()["state"] == "queued"

    ads = client.get("/api/ads").json()["items"]
    assert ads[0]["id"] == payload["ad_id"]


def test_upload_exact_duplicate_short_circuits(client: TestClient):
    first = client.post(
        "/api/ads/upload",
        files={"file": ("ad.mp4", b"same file", "video/mp4")},
    ).json()

    second = client.post(
        "/api/ads/upload",
        files={"file": ("ad.mp4", b"same file", "video/mp4")},
    )

    assert second.status_code == 200
    payload = second.json()
    assert payload["state"] == "duplicate"
    assert payload["ad_id"] == first["ad_id"]
    assert payload["job_id"] is None


def test_evidence_endpoints_stats_and_risk_filters(client: TestClient, config_path: Path):
    conn = _db(config_path)
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
                "ad_evidence",
                "/tmp/evidence.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        conn.execute(
            """
            INSERT INTO frames (ad_id, frame_index, time_ms, path, kept)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ad_evidence", 0, 500, "/tmp/frame.jpg", 1),
        )
        frame_id = conn.execute(
            "SELECT id FROM frames WHERE ad_id = ? AND frame_index = 0",
            ("ad_evidence",),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO ocr_items (frame_id, engine, text, bbox_json, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (frame_id, "paddleocr", "Limited time Wrangler offer", "[0,1,2,3]", 0.91),
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (ad_id, start_ms, end_ms, text, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ad_evidence", 0, 1000, "This Wrangler offer ends soon", 0.97),
        )
        conn.execute(
            """
            INSERT INTO classifications (
                ad_id, primary_category, risk_labels_json, confidence,
                ocr_quality_json, vlm_raw_json, evidence_json, vlm_model,
                vlm_prompt_version, embedder_text_model, embedder_visual_model,
                pipeline_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_evidence",
                "automotive",
                '["urgency_pressure"]',
                0.88,
                "null",
                "{}",
                '[{"time_ms":500,"frame_index":0,"source":"ocr","text":"Limited time Wrangler offer"}]',
                "mock",
                "test",
                "text",
                "visual",
                "test",
                datetime.now(UTC).isoformat(),
            ),
        )
        fts_update(
            conn,
            "ad_evidence",
            brand="Jeep",
            products="Wrangler",
            primary_category="automotive",
            transcript_text="This Wrangler offer ends soon",
            ocr_text="Limited time Wrangler offer",
        )
        conn.commit()
    finally:
        conn.close()

    transcript = client.get("/api/ads/ad_evidence/transcript")
    assert transcript.status_code == 200
    assert transcript.json()["full_text"] == "This Wrangler offer ends soon"

    ocr = client.get("/api/ads/ad_evidence/ocr")
    assert ocr.status_code == 200
    assert ocr.json()["items"][0]["bbox"] == [0, 1, 2, 3]

    listed = client.get("/api/ads", params={"risk_label": "urgency_pressure"})
    assert [item["id"] for item in listed.json()["items"]] == ["ad_evidence"]

    searched = client.get(
        "/api/search",
        params={"mode": "keyword", "q": "Wrangler", "risk_label": "urgency_pressure"},
    )
    assert [item["ad_id"] for item in searched.json()["items"]] == ["ad_evidence"]

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json()["risk_labels"][0] == {"value": "urgency_pressure", "count": 1}

    export_json = client.get("/api/ads/ad_evidence/export/evidence")
    assert export_json.status_code == 200
    assert export_json.json()["ocr_items"][0]["text"] == "Limited time Wrangler offer"

    export_html = client.get("/api/ads/ad_evidence/export/evidence", params={"format": "html"})
    assert export_html.status_code == 200
    assert "Limited time Wrangler offer" in export_html.text


def test_creative_panel_endpoint_creates_simulated_report(client: TestClient, config_path: Path):
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    conn = _db(config_path)
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
                "ad_panel_api",
                "/tmp/panel.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (ad_id, products_json, offers_json, ctas_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                "ad_panel_api",
                '["Wrangler"]',
                '[{"text":"0% APR", "evidence":[{"time_ms":0,"frame_index":0,"source":"ocr","text":"0% APR"}]}]',
                '[{"text":"Shop now", "evidence":[{"time_ms":0,"frame_index":0,"source":"ocr","text":"Shop now"}]}]',
            ),
        )
        conn.commit()
    finally:
        conn.close()

    personas = client.get("/api/creative-panel/personas")
    assert personas.status_code == 200
    assert personas.json()["items"]

    response = client.post(
        "/api/ads/ad_panel_api/creative-panel",
        json={"persona_ids": ["budget_parent", "skeptical_buyer"]},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["report_type"] == "simulated_creative_review"
    assert payload["analysis_source"] == "vlm"
    assert [item["persona_id"] for item in payload["personas"]] == [
        "budget_parent",
        "skeptical_buyer",
    ]
    assert payload["personas"][0]["first_impression"] == "The offer is easy to notice."
    assert "not a real focus group" in payload["caveat"]
    assert Path(data["paths"]["out"], "ad_panel_api", "creative_panel.json").exists()

    debate = client.post(
        "/api/ads/ad_panel_api/creative-panel/debate",
        json={
            "persona_ids": ["budget_parent", "skeptical_buyer"],
            "topic": "Should the ad lead with offer or proof?",
            "use_vlm": False,
        },
    )

    assert debate.status_code == 200, debate.text
    debate_payload = debate.json()
    assert debate_payload["report_type"] == "simulated_creative_debate"
    assert debate_payload["topic"] == "Should the ad lead with offer or proof?"
    assert debate_payload["opening_statements"]
    assert debate_payload["cross_examination"]
    assert debate_payload["scorecard"]["recommended_tests"]
    assert Path(data["paths"]["out"], "ad_panel_api", "creative_debate.json").exists()


def test_delete_ad_can_cleanup_database_and_local_artifacts(client: TestClient, config_path: Path):
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = Path(data["paths"]["data_root"])
    ad_id = "ad_delete"
    upload_path = Path(data["paths"]["uploads"]) / f"{ad_id}.mp4"
    frame_dir = Path(data["paths"]["frames"]) / ad_id
    audio_dir = Path(data["paths"]["audio"]) / ad_id
    whisper_dir = Path(data["paths"]["whisper"]) / ad_id
    out_dir = Path(data["paths"]["out"]) / ad_id

    for directory in [upload_path.parent, frame_dir, audio_dir, whisper_dir, out_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(b"video")
    (frame_dir / "frame.png").write_bytes(b"frame")
    (audio_dir / "audio.wav").write_bytes(b"audio")
    (whisper_dir / "whisper.json").write_text("{}", encoding="utf-8")
    (out_dir / "manifest.json").write_text("{}", encoding="utf-8")

    conn = _db(config_path)
    try:
        conn.execute(
            "INSERT INTO ads (id, source_path, ingested_at, status) VALUES (?, ?, ?, ?)",
            (ad_id, str(upload_path), datetime.now(UTC).isoformat(), "completed"),
        )
        conn.execute(
            """
            INSERT INTO frames (ad_id, frame_index, time_ms, path, kept)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ad_id, 0, 0, str(frame_dir / "frame.png"), True),
        )
        fts_update(conn, ad_id, brand="Jeep")
        load_sqlite_vec(conn)
        store = SqliteVecStore(conn, text_dim=8, visual_dim=8)
        store.ensure_tables()
        store.upsert_text(ad_id, [0.1] * 8)
        store.upsert_visual(ad_id, [0.2] * 8)
        conn.commit()
    finally:
        conn.close()

    response = client.delete(f"/api/ads/{ad_id}", params={"cleanup_artifacts": True})

    assert response.status_code == 200, response.text
    removed = response.json()["artifacts_removed"]
    assert str(upload_path.resolve()) in removed
    assert str(frame_dir.resolve()) in removed
    assert str(audio_dir.resolve()) in removed
    assert str(whisper_dir.resolve()) in removed
    assert str(out_dir.resolve()) in removed
    assert not upload_path.exists()
    assert not frame_dir.exists()
    assert not audio_dir.exists()
    assert not whisper_dir.exists()
    assert not out_dir.exists()
    assert data_root.exists()

    conn = _db(config_path)
    try:
        load_sqlite_vec(conn)
        assert conn.execute("SELECT COUNT(*) FROM ads WHERE id = ?", (ad_id,)).fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM frames WHERE ad_id = ?", (ad_id,)).fetchone()[0] == 0
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM ads_fts WHERE ad_id = ?", (ad_id,)).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM vec_ads_text WHERE ad_id = ?", (ad_id,)).fetchone()[
                0
            ]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM vec_ads_visual WHERE ad_id = ?", (ad_id,)
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


def test_completed_job_sse_emits_done(config_path: Path):
    app = create_app(config_path=config_path, upload_probe=lambda _path: object())
    conn = _db(config_path)
    try:
        JobRepository(conn).create(
            JobRecord(
                id="job_done",
                state="completed",
                progress=1.0,
                message="completed",
            )
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as client, client.stream("GET", "/api/jobs/job_done/events") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"state": "completed"' in body
    assert "event: done" in body


def test_campaign_crud_endpoints(client: TestClient, config_path: Path):
    conn = _db(config_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, brand_name, products_text, primary_category
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_campaign",
                "/tmp/ad.mp4",
                datetime.now(UTC).isoformat(),
                "Jeep",
                "Wrangler",
                "automotive",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
                ad_id, products_json, offers_json, ctas_json, disclaimers_json,
                creative_format_json, creative_attributes_json, campaign_suggestions_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_campaign",
                '["Wrangler"]',
                '[{"text":"0% APR"}]',
                '[{"text":"Shop now"}]',
                '[{"text":"Offer terms apply", "is_small_print": true}]',
                '{"has_voiceover": true, "has_on_screen_text": true, "aspect_ratio": "16:9"}',
                '{"format": "offer_end_card", "disclaimer_density": "medium"}',
                '[{"name":"Declaration of Deals","confidence":0.92}]',
            ),
        )
        conn.execute(
            """
            INSERT INTO classifications (
                ad_id, primary_category, risk_labels_json, confidence,
                ocr_quality_json, vlm_raw_json, evidence_json, vlm_model,
                vlm_prompt_version, embedder_text_model, embedder_visual_model,
                pipeline_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_campaign",
                "automotive",
                '["urgency_pressure"]',
                0.82,
                "{}",
                "{}",
                "[]",
                "mock",
                "test",
                "text",
                "visual",
                "test",
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    created = client.post(
        "/api/campaigns",
        json={"id": "c_test", "name": "Test Campaign", "brand": "Jeep"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["created_by"] == "user"

    assign = client.post("/api/campaigns/c_test/ads", json={"ad_ids": ["ad_campaign"]})
    assert assign.status_code == 200

    detail = client.get("/api/campaigns/c_test").json()
    assert detail["campaign"]["name"] == "Test Campaign"
    assert detail["ads"][0]["ad_id"] == "ad_campaign"
    assert detail["ads"][0]["offers"] == ["0% APR"]
    assert detail["research"]["summary"]["ad_count"] == 1
    assert detail["research"]["messaging"]["top_products"][0]["value"] == "Wrangler"
    assert detail["research"]["creative"]["small_print_ads"] == 1
    deep = client.post(
        "/api/campaigns/c_test/research/deep",
        json={
            "include_web": False,
            "question": "How should we improve the offer?",
            "thinking": True,
        },
    )
    assert deep.status_code == 200, deep.text
    deep_json = deep.json()
    assert deep_json["mode"] == "local"
    assert deep_json["web_available"] is False
    assert deep_json["requested_question"] == "How should we improve the offer?"
    assert deep_json["question_answer"]["question"] == "How should we improve the offer?"
    assert deep_json["research_source"] == "llm"
    assert deep_json["question_answer"]["source"] == "llm"
    assert "LLM client" in deep_json["question_answer"]["answer"]
    assert deep_json["generated_from"]["ad_ids"] == ["ad_campaign"]
    assert deep_json["findings"][0]["title"] == "LLM offer read"
    assert any(item["area"] == "Direction" for item in deep_json["creative_review"])
    assert deep_json["suggested_edits"]

    patched = client.patch("/api/campaigns/c_test", json={"theme": "summer"})
    assert patched.status_code == 200
    assert patched.json()["theme"] == "summer"
    cleared = client.patch("/api/campaigns/c_test", json={"theme": None})
    assert cleared.status_code == 200
    assert cleared.json()["theme"] is None

    unassign = client.delete("/api/campaigns/c_test/ads/ad_campaign")
    assert unassign.status_code == 200

    deleted = client.delete("/api/campaigns/c_test")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == "c_test"


def test_campaign_discover_accepts_reviewed_proposals(client: TestClient, config_path: Path):
    conn = _db(config_path)
    try:
        load_sqlite_vec(conn)
        store = SqliteVecStore(conn, text_dim=8, visual_dim=8)
        store.ensure_tables()
        for idx, vector in enumerate(([1.0, 0.0], [0.999, 0.001], [0.998, 0.002])):
            ad_id = f"ad_campaign_scan_{idx}"
            conn.execute(
                """
                INSERT INTO ads (
                    id, source_path, ingested_at, status, brand_name, products_text
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ad_id,
                    f"/tmp/{ad_id}.mp4",
                    datetime.now(UTC).isoformat(),
                    "completed",
                    "Jeep",
                    "Wrangler",
                ),
            )
            store.upsert_visual(ad_id, [*vector, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        conn.commit()
    finally:
        conn.close()

    scan = client.post("/api/campaigns/discover")
    assert scan.status_code == 200, scan.text
    proposals = scan.json()["proposals"]
    assert len(proposals) == 1

    before_accept = client.get("/api/campaigns").json()["items"]
    assert before_accept == []

    proposal = proposals[0]
    accepted = client.post(
        "/api/campaigns/discover/accept",
        json={"campaign_ids": [proposal["id"]], "proposals": proposals},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["accepted"][0]["created_by"] == "user"

    campaigns = client.get("/api/campaigns").json()["items"]
    assert campaigns[0]["id"] == proposal["id"]
    assert campaigns[0]["ad_count"] == 3
    detail = client.get(f"/api/campaigns/{proposal['id']}").json()
    assert {item["assigned_by"] for item in detail["ads"]} == {"user"}


def test_cancel_job_endpoint(client: TestClient, config_path: Path):
    conn = _db(config_path)
    try:
        JobRepository(conn).create(JobRecord(id="job_cancel", state="queued"))
        conn.commit()
    finally:
        conn.close()

    response = client.post("/api/jobs/job_cancel/cancel")

    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert response.json()["job"]["state"] == "cancelled"


def test_list_jobs_endpoint_includes_ad_context(client: TestClient, config_path: Path):
    conn = _db(config_path)
    try:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO ads (id, source_path, ingested_at, status, brand_name) VALUES (?, ?, ?, ?, ?)",
            ("ad_job", "/tmp/ad.mp4", now, "processing", "Test Brand"),
        )
        JobRepository(conn).create(
            JobRecord(id="job_running", ad_id="ad_job", state="running", progress=0.25)
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/jobs")

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["id"] == "job_running"
    assert item["ad_id"] == "ad_job"
    assert item["ad_status"] == "processing"
    assert item["brand_name"] == "Test Brand"


def test_delete_job_removes_ad_rows_and_artifacts(client: TestClient, config_path: Path):
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = Path(cfg["paths"]["data_root"])
    upload = data_root / "uploads" / "ad_job.mp4"
    frame_dir = data_root / "frames" / "ad_job"
    out_dir = data_root / "out" / "ad_job"
    upload.parent.mkdir(parents=True, exist_ok=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(b"video")
    (frame_dir / "frame.png").write_bytes(b"frame")
    (out_dir / "evidence.json").write_text("{}", encoding="utf-8")

    conn = _db(config_path)
    try:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO ads (id, source_path, ingested_at, status) VALUES (?, ?, ?, ?)",
            ("ad_job", str(upload), now, "processing"),
        )
        JobRepository(conn).create(
            JobRecord(id="job_running", ad_id="ad_job", state="running", progress=0.5)
        )
        conn.commit()
    finally:
        conn.close()

    response = client.delete("/api/jobs/job_running")

    assert response.status_code == 200, response.text
    assert response.json()["ad_id"] == "ad_job"
    assert not upload.exists()
    assert not frame_dir.exists()
    assert not out_dir.exists()

    conn = _db(config_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE id = 'job_running'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ads WHERE id = 'ad_job'").fetchone()[0] == 0
    finally:
        conn.close()


def test_vector_search_route_loads_sqlite_vec(client: TestClient):
    response = client.get("/api/search", params={"mode": "visual", "ad_id": "missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "visual vector not found"


def test_brand_profile_enrichment_persists_cache_and_returns_on_detail(config_path: Path):
    calls: list[str] = []

    class FakeBrandProfileClient:
        def fetch(self, name: str, *, context=None) -> BrandProfile:
            calls.append(name)
            now = utc_now()
            return BrandProfile(
                normalized_name="jeep",
                query_name=name,
                display_name="Jeep",
                description="American automobile brand",
                summary="Jeep is an American automobile brand now owned by Stellantis.",
                wikipedia_title="Jeep",
                wikipedia_url="https://en.wikipedia.org/wiki/Jeep",
                wikidata_qid="Q43193",
                parent_companies=["Stellantis"],
                owners=["Stellantis"],
                corporate_chain=["Stellantis", "Exor"],
                industries=["automotive industry"],
                key_metrics={"employees": "10,000"},
                lookup_steps=[
                    BrandProfileLookupStep(
                        source="wikipedia",
                        action="search",
                        query=name,
                        result_count=1,
                    )
                ],
                source_urls=["https://en.wikipedia.org/wiki/Jeep"],
                fetched_at=now,
                expires_at=now + timedelta(days=90),
            )

    app = create_app(
        config_path=config_path,
        brand_profile_client_factory=lambda _config: FakeBrandProfileClient(),
    )
    conn = _db(config_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name, advertiser_name
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_profile",
                "/tmp/profile.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Stellantis",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as profile_client:
        response = profile_client.post(
            "/api/ads/ad_profile/brand-profile/enrich",
            json={"target": "brand"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["cached"] is False
        assert payload["profile"]["parent_companies"] == ["Stellantis"]
        assert payload["profile"]["corporate_chain"] == ["Stellantis", "Exor"]
        assert calls == ["Jeep"]

        detail = profile_client.get("/api/ads/ad_profile")
        assert detail.status_code == 200, detail.text
        assert detail.json()["brand_profile"]["display_name"] == "Jeep"
        assert detail.json()["brand_profile"]["key_metrics"]["employees"] == "10,000"

        cached = profile_client.post(
            "/api/ads/ad_profile/brand-profile/enrich",
            json={"target": "brand"},
        )
        assert cached.status_code == 200
        assert cached.json()["cached"] is True
        assert calls == ["Jeep"]


def test_brand_profile_refresh_deletes_stale_cache_when_lookup_not_found(config_path: Path):
    class MissingBrandProfileClient:
        def fetch(self, name: str, *, context=None) -> BrandProfile:
            raise BrandProfileNotFoundError(f"no relevant Wikimedia profile found for {name}")

    app = create_app(
        config_path=config_path,
        brand_profile_client_factory=lambda _config: MissingBrandProfileClient(),
    )
    conn = _db(config_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "ad_profile_missing",
                "/tmp/profile.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Prillaman Homestead",
            ),
        )
        now = utc_now()
        BrandProfileRepository(conn).upsert(
            BrandProfile(
                normalized_name="prillaman homestead",
                query_name="Prillaman Homestead",
                display_name="Prillaman Homestead",
                description="historic site",
                wikidata_qid="Q105887726",
                fetched_at=now,
                expires_at=now + timedelta(days=90),
            )
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as profile_client:
        before = profile_client.get("/api/ads/ad_profile_missing")
        assert before.status_code == 200
        assert before.json()["brand_profile"]["description"] == "historic site"

        response = profile_client.post(
            "/api/ads/ad_profile_missing/brand-profile/enrich",
            json={"target": "brand", "force": True},
        )
        assert response.status_code == 404

        after = profile_client.get("/api/ads/ad_profile_missing")
        assert after.status_code == 200
        assert after.json()["brand_profile"] is None


def test_brand_profile_manual_search_select_and_reset(config_path: Path):
    class SearchableBrandProfileClient:
        def search_wikipedia_candidates(self, query: str):
            return [
                {
                    "title": "Thor Motor Coach",
                    "pageid": 123,
                    "snippet": "American recreational vehicle manufacturer",
                    "url": "https://en.wikipedia.org/wiki/Thor_Motor_Coach",
                }
            ]

        def fetch(
            self,
            name: str,
            *,
            context=None,
            search_query=None,
            wikipedia_title=None,
            wikidata_qid=None,
            allow_non_brand=False,
        ) -> BrandProfile:
            now = utc_now()
            return BrandProfile(
                normalized_name="thor",
                query_name=name,
                display_name=wikipedia_title,
                description="American recreational vehicle manufacturer",
                wikipedia_title=wikipedia_title,
                wikipedia_url="https://en.wikipedia.org/wiki/Thor_Motor_Coach",
                wikidata_qid="QTHORCOACH",
                source_json={
                    "search_query": search_query,
                    "manual_title": wikipedia_title,
                    "allow_non_brand": allow_non_brand,
                },
                fetched_at=now,
                expires_at=now + timedelta(days=90),
            )

    app = create_app(
        config_path=config_path,
        brand_profile_client_factory=lambda _config: SearchableBrandProfileClient(),
    )
    conn = _db(config_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name,
                primary_category, subcategory
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_profile_select",
                "/tmp/thor.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Thor",
                "automotive",
                "RV",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as profile_client:
        search = profile_client.get(
            "/api/ads/ad_profile_select/brand-profile/search",
            params={"target": "brand", "q": "Thor RV"},
        )
        assert search.status_code == 200, search.text
        assert search.json()["items"][0]["title"] == "Thor Motor Coach"

        enrich = profile_client.post(
            "/api/ads/ad_profile_select/brand-profile/enrich",
            json={
                "target": "brand",
                "force": True,
                "query": "Thor RV",
                "wikipedia_title": "Thor Motor Coach",
            },
        )
        assert enrich.status_code == 200, enrich.text
        assert enrich.json()["profile"]["display_name"] == "Thor Motor Coach"

        reset = profile_client.delete("/api/ads/ad_profile_select/brand-profile/brand")
        assert reset.status_code == 200, reset.text
        detail = profile_client.get("/api/ads/ad_profile_select")
        assert detail.status_code == 200
        assert detail.json()["brand_profile"] is None


def test_patch_ad_updates_manual_iab_projection_and_classification(client: TestClient, config_path: Path):
    load = client.post("/api/knowledge/load-taxonomies", json={})
    assert load.status_code == 200, load.text

    conn = _db(config_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (
                id, source_path, ingested_at, status, brand_name,
                primary_category, iab_unique_id, iab_content_ids
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_iab_edit",
                "/tmp/iab.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "FOX5",
                "other",
                "338",
                "338,641",
            ),
        )
        conn.execute(
            """
            INSERT INTO classifications (
                ad_id, primary_category, risk_labels_json, confidence,
                ocr_quality_json, vlm_raw_json, evidence_json,
                vlm_model, vlm_prompt_version, embedder_text_model,
                embedder_visual_model, pipeline_version, created_at,
                iab_category_json, iab_content_categories_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_iab_edit",
                "other",
                "[]",
                0.8,
                None,
                "{}",
                "[]",
                "model",
                "prompt",
                "text",
                "visual",
                "test",
                datetime.now(UTC).isoformat(),
                None,
                "[]",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.patch(
        "/api/ads/ad_iab_edit",
        json={
            "primary_category": "entertainment_media",
            "iab_product_id": "1429",
            "iab_content_ids": ["483"],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["primary_category"] == "entertainment_media"
    assert payload["iab_unique_id"] == "1429"
    assert payload["iab_content_ids"] == "483"

    detail = client.get("/api/ads/ad_iab_edit")
    assert detail.status_code == 200
    classification = detail.json()["classification"]
    assert classification["primary_category"] == "entertainment_media"
    assert classification["iab_category"]["iab_unique_id"] == "1429"
    assert classification["iab_content_categories"][0]["iab_unique_id"] == "483"


def test_search_keyword_returns_preview(client: TestClient, config_path: Path):
    conn = _db(config_path)
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
                "ad_search_jeep",
                "/tmp/jeep.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Grand Cherokee",
                "automotive",
            ),
        )
        conn.execute(
            """
            INSERT INTO frames (ad_id, frame_index, time_ms, path, kept)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ad_search_jeep", 0, 0, "/tmp/frame.jpg", True),
        )
        fts_update(
            conn,
            "ad_search_jeep",
            brand="Jeep",
            products="Grand Cherokee",
            primary_category="automotive",
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/search", params={"mode": "keyword", "q": "Jeep"})

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["ad_id"] == "ad_search_jeep"
    assert item["ad"]["brand_name"] == "Jeep"
    assert item["ad"]["products_text"] == "Grand Cherokee"
    assert item["thumbnail_path"] == "/tmp/frame.jpg"
    assert item["source"] == "keyword"


def test_hybrid_keyword_query_excludes_vector_only_noise(client: TestClient, config_path: Path):
    conn = _db(config_path)
    try:
        rows = [
            ("ad_search_jeep", "Jeep", "Grand Cherokee", "automotive"),
            ("ad_search_hvac", "Prillaman", "Heating systems", "other"),
        ]
        for ad_id, brand, products, category in rows:
            conn.execute(
                """
                INSERT INTO ads (
                    id, source_path, ingested_at, status, brand_name, products_text,
                    primary_category
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ad_id,
                    f"/tmp/{ad_id}.mp4",
                    datetime.now(UTC).isoformat(),
                    "completed",
                    brand,
                    products,
                    category,
                ),
            )
            fts_update(
                conn,
                ad_id,
                brand=brand,
                products=products,
                primary_category=category,
            )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/search", params={"mode": "hybrid", "q": "Jeep", "k": 20})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["strategy"] == "keyword_first"
    assert [item["ad_id"] for item in payload["items"]] == ["ad_search_jeep"]


def test_hybrid_keyword_query_expands_business_aliases(client: TestClient, config_path: Path):
    conn = _db(config_path)
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
                "ad_search_hvac",
                "/tmp/hvac.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Prillaman Mechanical, Heating & AC",
                "Heating systems, Cooling systems, Air Conditioning Check",
                "other",
            ),
        )
        fts_update(
            conn,
            "ad_search_hvac",
            brand="Prillaman Mechanical, Heating & AC",
            products="Heating systems, Cooling systems, Air Conditioning Check",
            primary_category="other",
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/search", params={"mode": "hybrid", "q": "HVAC", "k": 20})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["strategy"] == "keyword_first"
    assert [item["ad_id"] for item in payload["items"]] == ["ad_search_hvac"]


def test_hybrid_restaurant_query_does_not_match_retail_delivery(
    client: TestClient, config_path: Path
):
    conn = _db(config_path)
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
                "ad_search_jeep",
                "/tmp/jeep.mp4",
                datetime.now(UTC).isoformat(),
                "completed",
                "Jeep",
                "Grand Cherokee",
                "automotive",
            ),
        )
        fts_update(
            conn,
            "ad_search_jeep",
            brand="Jeep",
            products="Grand Cherokee",
            primary_category="automotive",
            marketing_entities_text="subject to taking retail delivery by April 30",
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/search", params={"mode": "hybrid", "q": "restaurants", "k": 20})

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


def test_hybrid_service_alias_ignores_financial_services_disclaimer(
    client: TestClient, config_path: Path
):
    conn = _db(config_path)
    try:
        rows = [
            (
                "ad_search_jeep",
                "Jeep",
                "Grand Cherokee",
                "automotive",
                "Stellantis Financial Services retail delivery disclosure",
            ),
            (
                "ad_search_hvac",
                "Prillaman Mechanical, Heating & AC",
                "Heating systems, Cooling systems, Air Conditioning Check",
                "other",
                "",
            ),
        ]
        for ad_id, brand, products, category, marketing_text in rows:
            conn.execute(
                """
                INSERT INTO ads (
                    id, source_path, ingested_at, status, brand_name, products_text,
                    primary_category
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ad_id,
                    f"/tmp/{ad_id}.mp4",
                    datetime.now(UTC).isoformat(),
                    "completed",
                    brand,
                    products,
                    category,
                ),
            )
            fts_update(
                conn,
                ad_id,
                brand=brand,
                products=products,
                primary_category=category,
                marketing_entities_text=marketing_text,
            )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/search", params={"mode": "hybrid", "q": "repairs"})

    assert response.status_code == 200, response.text
    assert [item["ad_id"] for item in response.json()["items"]] == ["ad_search_hvac"]
