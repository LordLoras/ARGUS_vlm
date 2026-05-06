from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ad_classifier.api.app import create_app
from ad_classifier.db.connection import open_database
from ad_classifier.db.repositories import JobRepository
from ad_classifier.models.jobs import JobRecord


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
    app = create_app(config_path=config_path, upload_probe=lambda _path: object())
    return TestClient(app)


def _db(config_path: Path) -> sqlite3.Connection:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return open_database(Path(data["paths"]["sqlite_path"]))


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
            "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
            ("ad_campaign", "/tmp/ad.mp4", datetime.now(UTC).isoformat()),
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

    patched = client.patch("/api/campaigns/c_test", json={"theme": "summer"})
    assert patched.status_code == 200
    assert patched.json()["theme"] == "summer"

    unassign = client.delete("/api/campaigns/c_test/ads/ad_campaign")
    assert unassign.status_code == 200

    deleted = client.delete("/api/campaigns/c_test")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == "c_test"


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
