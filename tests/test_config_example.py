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


def test_vlm_frontier_mode():
    from ad_classifier.config import AppConfig

    data = {
        "vlm": {
            "mode": "frontier",
            "frontier": {
                "endpoint": "https://openrouter.ai/api/v1",
                "model": "openrouter/auto",
                "api_key_env": "OPENROUTER_API_KEY",
            },
        }
    }
    config = AppConfig.model_validate(data)
    assert config.vlm.mode == "frontier"
    assert config.vlm.endpoint.model == "openrouter/auto"
    assert config.vlm.endpoint.endpoint == "https://openrouter.ai/api/v1"
    assert config.vlm.endpoint.api_key_env == "OPENROUTER_API_KEY"


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


def test_agent_can_inherit_specific_vlm_endpoint():
    from ad_classifier.config import AppConfig

    data = {
        "vlm": {
            "mode": "frontier",
            "remote": {
                "endpoint": "https://api.example.com/v1",
                "model": "gpt-4o-mini",
                "api_key_env": "REMOTE_KEY",
                "timeout_s": 70,
            },
            "frontier": {
                "endpoint": "https://openrouter.ai/api/v1",
                "model": "openrouter/auto",
                "api_key_env": "OPENROUTER_KEY",
            },
        },
        "agent": {"inherit_vlm": True, "inherit_vlm_mode": "remote"},
    }
    config = AppConfig.model_validate(data)
    assert config.vlm.endpoint.model == "openrouter/auto"
    assert config.agent.inherit_vlm_mode == "remote"
    assert config.agent.endpoint.endpoint == "https://api.example.com/v1"
    assert config.agent.endpoint.model == "gpt-4o-mini"
    assert config.agent.endpoint.api_key_env == "REMOTE_KEY"
    assert config.agent.endpoint.timeout_s == 70


def test_creative_panel_inherits_vlm_mode_endpoint():
    from ad_classifier.config import AppConfig

    data = {
        "vlm": {
            "mode": "frontier",
            "frontier": {
                "endpoint": "https://openrouter.ai/api/v1",
                "model": "anthropic/claude-sonnet-4.5",
                "api_key_env": "OPENROUTER_KEY",
                "timeout_s": 180,
                "max_retries": 4,
                "retry_delay_s": 3,
                "stream": False,
            },
        },
        "creative_panel": {"inherit_vlm": True},
    }
    config = AppConfig.model_validate(data)
    assert config.creative_panel.inherit_vlm is True
    assert config.creative_panel.endpoint.endpoint == "https://openrouter.ai/api/v1"
    assert config.creative_panel.endpoint.model == "anthropic/claude-sonnet-4.5"
    assert config.creative_panel.endpoint.api_key_env == "OPENROUTER_KEY"
    assert config.creative_panel.endpoint.timeout_s == 180
    assert config.creative_panel.endpoint.max_retries == 4
    assert config.creative_panel.endpoint.retry_delay_s == 3
    assert config.creative_panel.endpoint.stream is False


def test_creative_panel_can_use_independent_endpoint():
    from ad_classifier.config import AppConfig

    data = {
        "vlm": {
            "mode": "frontier",
            "frontier": {
                "endpoint": "https://openrouter.ai/api/v1",
                "model": "openrouter/auto",
                "api_key_env": "OPENROUTER_KEY",
            },
        },
        "creative_panel": {
            "inherit_vlm": False,
            "endpoint": {
                "endpoint": "http://127.0.0.1:1234/v1",
                "model": "local-creative",
            },
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    }
    config = AppConfig.model_validate(data)
    assert config.creative_panel.inherit_vlm is False
    assert config.creative_panel.endpoint.endpoint == "http://127.0.0.1:1234/v1"
    assert config.creative_panel.endpoint.model == "local-creative"
    assert config.creative_panel.endpoint.api_key_env is None
    assert config.creative_panel.max_tokens == 4096
    assert config.creative_panel.temperature == 0.2
