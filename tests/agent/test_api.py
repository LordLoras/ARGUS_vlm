from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ad_classifier.agent.client import AgentMessage, MockAgentClient
from ad_classifier.agent.models import ToolCall
from ad_classifier.api.app import create_app


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
            "sqlite_path": str(tmp_path / "agent_api.db"),
        },
        "api": {"cors_origins": ["http://localhost:5173"]},
        "vector_store": {"text_dim": 8, "visual_dim": 8},
        "agent": {
            "max_iterations": 4,
            "list_max_rows": 10,
            "sql_readonly_max_rows": 10,
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _seed_some_ads(db_path: Path) -> None:
    from ad_classifier.db.connection import open_database
    from ad_classifier.db.repositories import AdRepository
    from ad_classifier.models.ads import AdRecord

    conn = open_database(db_path)
    try:
        repo = AdRepository(conn)
        repo.upsert_ingest(
            AdRecord(
                id="ad_one",
                source_path="/tmp/a.mp4",
                ingested_at=datetime.now(UTC),
                status="completed",
            )
        )
        repo.update_projection(
            "ad_one",
            brand_name="BrandX",
            brand_confidence=0.9,
            advertiser_name=None,
            website_domain=None,
            phone_number=None,
            landing_page_domain=None,
            products_text="Thing",
            primary_category="other",
            decision="allow",
        )
        conn.commit()
    finally:
        conn.close()


def _client_factory(messages):
    """Returns a function `(agent_config) -> AgentClient` that emits scripted messages."""

    def factory(_agent_config):
        return MockAgentClient(messages)

    return factory


def test_agent_session_create_and_list(config_path: Path):
    app = create_app(config_path=config_path)
    client = TestClient(app)
    response = client.post("/api/agent/sessions")
    assert response.status_code == 200, response.text
    sid = response.json()["session_id"]

    listed = client.get("/api/agent/sessions").json()
    assert any(item["id"] == sid for item in listed["items"])


def test_agent_query_runs_full_loop(config_path: Path):
    db_path = Path(yaml.safe_load(config_path.read_text())["paths"]["sqlite_path"])
    # Need to create the db before seeding
    app = create_app(
        config_path=config_path,
        agent_client_factory=_client_factory(
            [
                AgentMessage(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="c1", name="count_ads", arguments={"brand": "BrandX"}
                        )
                    ],
                    finish_reason="tool_calls",
                ),
                AgentMessage(
                    content="BrandX has one ad (ad_one).",
                    tool_calls=[],
                    finish_reason="stop",
                ),
            ]
        ),
    )
    _seed_some_ads(db_path)

    client = TestClient(app)
    sid = client.post("/api/agent/sessions").json()["session_id"]

    answer = client.post(
        f"/api/agent/sessions/{sid}/query", json={"text": "how many BrandX?"}
    ).json()
    assert answer["session_id"] == sid
    assert answer["iterations"] == 2
    assert answer["tool_calls"][0]["name"] == "count_ads"
    assert answer["tool_results"][0]["data"]["count"] == 1
    assert "BrandX" in answer["text"]


def test_agent_events_sse_ordering(config_path: Path):
    db_path = Path(yaml.safe_load(config_path.read_text())["paths"]["sqlite_path"])
    app = create_app(
        config_path=config_path,
        agent_client_factory=_client_factory(
            [
                AgentMessage(
                    content=None,
                    tool_calls=[ToolCall(id="c1", name="count_ads", arguments={})],
                    finish_reason="tool_calls",
                ),
                AgentMessage(content="done", tool_calls=[], finish_reason="stop"),
            ]
        ),
    )
    _seed_some_ads(db_path)

    with TestClient(app) as client:
        sid = client.post("/api/agent/sessions").json()["session_id"]
        with client.stream(
            "GET",
            f"/api/agent/sessions/{sid}/events",
            params={"q": "how many ads?"},
        ) as response:
            body = "".join(response.iter_text())

    # Verify the SSE event names appear in order
    sequence = [
        i
        for i in (
            body.find("event: session"),
            body.find("event: tool_call"),
            body.find("event: tool_result"),
            body.find("event: final"),
            body.find("event: done"),
        )
        if i != -1
    ]
    assert sequence == sorted(sequence)


def test_agent_tools_endpoint(config_path: Path):
    app = create_app(config_path=config_path)
    client = TestClient(app)
    response = client.get("/api/agent/tools")
    assert response.status_code == 200
    names = [tool["name"] for tool in response.json()["tools"]]
    assert "list_ads" in names
    assert "compare_ads" in names


def test_agent_schema_endpoint(config_path: Path):
    app = create_app(config_path=config_path)
    client = TestClient(app)
    response = client.get("/api/agent/schema")
    assert response.status_code == 200
    body = response.json()
    assert "ads(" in body["schema"]
    assert "{TOOL_CATALOG}" not in body["system_prompt"]
