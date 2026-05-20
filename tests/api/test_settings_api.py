from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ad_classifier.api.app import create_app


def _settings_config(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    config = {
        "paths": {
            "data_root": str(data_root),
            "uploads": str(data_root / "uploads"),
            "frames": str(data_root / "frames"),
            "audio": str(data_root / "audio"),
            "whisper": str(data_root / "whisper"),
            "out": str(data_root / "out"),
            "sqlite_path": str(tmp_path / "settings.db"),
        },
        "vector_store": {"text_dim": 8, "visual_dim": 8},
        "vlm": {
            "mode": "local",
            "remote": {
                "endpoint": "https://api.example.com/v1",
                "model": "mock-remote",
                "api_key_env": "REMOTE_TEST_KEY",
            },
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_settings_api_redacts_and_manages_api_keys(tmp_path: Path):
    config_path = _settings_config(tmp_path)
    client = TestClient(create_app(config_path=config_path))

    initial = client.get("/api/settings")
    assert initial.status_code == 200
    payload = initial.json()
    assert payload["config"]["vlm"]["frontier"]["api_key_env"] == "OPENROUTER_API_KEY"
    assert payload["config"]["vlm"]["prompt_profile"] == "auto"
    assert any(item["value"] == "frontier_strict" for item in payload["options"]["prompt_profiles"])
    assert any(item["name"] == "REMOTE_TEST_KEY" for item in payload["api_keys"])

    created = client.post(
        "/api/settings/api-keys",
        json={"name": "REMOTE_TEST_KEY", "value": "secret-value"},
    )
    assert created.status_code == 200, created.text
    key_record = next(item for item in created.json()["api_keys"] if item["name"] == "REMOTE_TEST_KEY")
    assert key_record["available"] is True
    assert key_record["managed"] is True
    assert key_record["redacted"] is True
    assert key_record["value"] is None
    assert "secret-value" not in created.text
    assert "secret-value" in (tmp_path / ".env.local").read_text(encoding="utf-8")

    removed = client.delete("/api/settings/api-keys/REMOTE_TEST_KEY")
    assert removed.status_code == 200
    key_record = next(item for item in removed.json()["api_keys"] if item["name"] == "REMOTE_TEST_KEY")
    assert key_record["managed"] is False
    assert key_record["available"] is False
    assert "secret-value" not in (tmp_path / ".env.local").read_text(encoding="utf-8")


def test_settings_api_persists_config_updates(tmp_path: Path):
    config_path = _settings_config(tmp_path)
    client = TestClient(create_app(config_path=config_path))
    snapshot = client.get("/api/settings").json()
    config = snapshot["config"]
    config["vlm"]["mode"] = "frontier"
    config["vlm"]["prompt_profile"] = "frontier_strict"
    config["vlm"]["frontier"]["model"] = "anthropic/claude-sonnet-4.5"
    config["vlm"]["frontier"]["api_key_env"] = "OPENROUTER_TEST_KEY"
    config["worker"]["poll_interval_ms"] = 250

    updated = client.put("/api/settings", json={"config": config})

    assert updated.status_code == 200, updated.text
    assert updated.json()["config"]["vlm"]["mode"] == "frontier"
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["vlm"]["mode"] == "frontier"
    assert saved["vlm"]["prompt_profile"] == "frontier_strict"
    assert saved["vlm"]["frontier"]["model"] == "anthropic/claude-sonnet-4.5"
    assert saved["vlm"]["frontier"]["api_key_env"] == "OPENROUTER_TEST_KEY"
    assert saved["worker"]["poll_interval_ms"] == 250
    assert "endpoint" not in saved["vlm"]
    assert saved["agent"]["endpoint"] == {}
    assert saved["creative_panel"]["endpoint"] == {}


def test_settings_api_persists_independent_ai_tool_routes(tmp_path: Path):
    config_path = _settings_config(tmp_path)
    client = TestClient(create_app(config_path=config_path))
    snapshot = client.get("/api/settings").json()
    config = snapshot["config"]
    config["agent"]["inherit_vlm"] = False
    config["agent"]["endpoint"] = {
        "endpoint": "http://127.0.0.1:1234/v1",
        "model": "local-agent",
        "api_key_env": None,
        "timeout_s": 45,
        "max_retries": 1,
        "retry_delay_s": 1,
        "stream": True,
    }
    config["creative_panel"]["inherit_vlm"] = False
    config["creative_panel"]["endpoint"] = {
        "endpoint": "http://127.0.0.1:1234/v1",
        "model": "local-debate",
        "api_key_env": None,
        "timeout_s": 90,
        "max_retries": 1,
        "retry_delay_s": 1,
        "stream": True,
    }
    config["creative_panel"]["max_tokens"] = 4096

    updated = client.put("/api/settings", json={"config": config})

    assert updated.status_code == 200, updated.text
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["agent"]["inherit_vlm"] is False
    assert saved["agent"]["endpoint"]["model"] == "local-agent"
    assert saved["creative_panel"]["inherit_vlm"] is False
    assert saved["creative_panel"]["endpoint"]["model"] == "local-debate"
    assert saved["creative_panel"]["max_tokens"] == 4096
