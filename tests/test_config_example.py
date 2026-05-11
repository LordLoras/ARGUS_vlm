from __future__ import annotations

from pathlib import Path

from ad_classifier.config import load_config


def test_example_config_uses_current_vlm_schema_and_model():
    config, source = load_config(Path("config.example.yaml"))

    assert source.name == "config.example.yaml"
    assert config.vlm.endpoint.model == "argus/vlm"
    assert config.vlm.endpoint.endpoint == "http://127.0.0.1:1234/v1"
    assert config.vlm.endpoint.timeout_s >= 240
    assert config.vlm.endpoint.temperature == 0.1
    assert config.vlm.endpoint.max_tokens == 4096
