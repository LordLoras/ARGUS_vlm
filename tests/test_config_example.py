from __future__ import annotations

from pathlib import Path

from ad_classifier.config import load_config


def test_example_config_uses_current_vlm_schema_and_model():
    config, source = load_config(Path("config.example.yaml"))

    assert source.name == "config.example.yaml"
    assert config.vlm.endpoint.model == "google/gemma-4-26b-a4b"
    assert config.vlm.endpoint.endpoint == "http://127.0.0.1:1234/v1"
