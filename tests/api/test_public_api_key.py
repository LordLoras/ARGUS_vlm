from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ad_classifier.api.app import create_app


def _public_config(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    config = {
        "paths": {
            "data_root": str(data_root),
            "uploads": str(data_root / "uploads"),
            "frames": str(data_root / "frames"),
            "audio": str(data_root / "audio"),
            "whisper": str(data_root / "whisper"),
            "out": str(data_root / "out"),
            "sqlite_path": str(tmp_path / "public.db"),
        },
        "vector_store": {"text_dim": 8, "visual_dim": 8},
        "api": {"public": {"enabled": True, "api_key_env": "PUBLIC_TEST_KEY"}},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_public_api_key_resolved_from_dotenv(tmp_path: Path):
    (tmp_path / ".env.local").write_text('PUBLIC_TEST_KEY="dotenv-secret"\n', encoding="utf-8")
    client = TestClient(create_app(config_path=_public_config(tmp_path)))

    assert client.get("/api/public/stats").status_code == 401
    assert client.get("/api/public/stats", headers={"X-API-Key": "wrong"}).status_code == 403
    ok = client.get("/api/public/stats", headers={"X-API-Key": "dotenv-secret"})
    assert ok.status_code == 200, ok.text


def test_public_api_without_any_key_returns_403(tmp_path: Path):
    client = TestClient(create_app(config_path=_public_config(tmp_path)))

    rejected = client.get("/api/public/stats", headers={"X-API-Key": "anything"})
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "public api key is not configured"


def test_settings_save_keeps_public_key_working(tmp_path: Path):
    (tmp_path / ".env.local").write_text('PUBLIC_TEST_KEY="dotenv-secret"\n', encoding="utf-8")
    config_path = _public_config(tmp_path)
    client = TestClient(create_app(config_path=config_path))

    snapshot = client.get("/api/settings").json()
    assert any(item["name"] == "PUBLIC_TEST_KEY" for item in snapshot["api_keys"])
    updated = client.put("/api/settings", json={"config": snapshot["config"]})
    assert updated.status_code == 200, updated.text

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["api"]["public"]["api_key_env"] == "PUBLIC_TEST_KEY"
    assert "api_key" not in saved["api"]["public"]

    reloaded = TestClient(create_app(config_path=config_path))
    ok = reloaded.get("/api/public/stats", headers={"X-API-Key": "dotenv-secret"})
    assert ok.status_code == 200, ok.text
