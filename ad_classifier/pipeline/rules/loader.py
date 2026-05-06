from __future__ import annotations

from pathlib import Path

import yaml

from ad_classifier.pipeline.rules.models import Rule

_DEFAULT_RULES_PATH = Path(__file__).parent / "default_rules.yaml"


def load_rules(path: Path | None = None) -> list[Rule]:
    """Load rules from a YAML file. Falls back to the built-in default_rules.yaml."""
    source = path if path is not None else _DEFAULT_RULES_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    raw_rules = data.get("rules", [])
    return [Rule.model_validate(r) for r in raw_rules]
