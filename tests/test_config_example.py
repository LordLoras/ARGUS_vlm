from __future__ import annotations

from pathlib import Path

from ad_classifier.config import load_config


def test_example_config_uses_current_vlm_schema_and_model():
    config, source = load_config(Path("config.example.yaml"))

    assert source.name == "config.example.yaml"
    assert config.vlm.mode == "local"
    assert config.vlm.local.model == "Qwen3.6-27B-Q4_K_M"
    assert config.vlm.local.endpoint == "http://127.0.0.1:1234/v1"
    assert config.vlm.local.timeout_s >= 240
    assert config.vlm.local.temperature == 0.1
    assert config.vlm.local.max_tokens == 8192


def test_vlm_mode_resolves_endpoint():
    config, source = load_config(Path("config.example.yaml"))

    assert config.vlm.mode == "local"
    assert config.vlm.endpoint.model == config.vlm.local.model
    assert config.vlm.endpoint.endpoint == config.vlm.local.endpoint


def test_vlm_remote_mode():
    from ad_classifier.config import AppConfig

    data = {
        "vlm": {
            "mode": "remote",
            "remote": {
                "endpoint": "https://api.example.com/v1",
                "model": "gpt-4o",
                "api_key_env": "API_KEY",
            },
        }
    }
    config = AppConfig.model_validate(data)
    assert config.vlm.mode == "remote"
    assert config.vlm.endpoint.model == "gpt-4o"
    assert config.vlm.endpoint.endpoint == "https://api.example.com/v1"
    assert config.vlm.endpoint.api_key_env == "API_KEY"


def test_agent_inherits_vlm_mode_endpoint():
    from ad_classifier.config import AppConfig

    data = {
        "vlm": {
            "mode": "remote",
            "remote": {
                "endpoint": "https://api.example.com/v1",
                "model": "gpt-4o",
                "api_key_env": "MY_KEY",
                "timeout_s": 60,
                "max_retries": 3,
                "retry_delay_s": 5,
                "stream": False,
            },
        },
        "agent": {"inherit_vlm": True},
    }
    config = AppConfig.model_validate(data)
    assert config.agent.inherit_vlm is True
    assert config.agent.endpoint.endpoint == "https://api.example.com/v1"
    assert config.agent.endpoint.model == "gpt-4o"
    assert config.agent.endpoint.api_key_env == "MY_KEY"
    assert config.agent.endpoint.timeout_s == 60
    assert config.agent.endpoint.max_retries == 3
    assert config.agent.endpoint.retry_delay_s == 5
    assert config.agent.endpoint.stream is False
