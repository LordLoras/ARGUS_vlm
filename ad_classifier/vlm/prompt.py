from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "gemma_ad_verifier.txt"
_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "taxonomy.yaml"


def get_prompt_version() -> str:
    first_line = _PROMPT_PATH.read_text(encoding="utf-8").split("\n")[0]
    for part in first_line.split(":"):
        part = part.strip()
        if part.startswith("verifier-"):
            return part
    return "unknown"


def _load_taxonomy(path: Path = _TAXONOMY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def render_verifier_prompt(
    *,
    prompt_path: Path = _PROMPT_PATH,
    taxonomy_path: Path = _TAXONOMY_PATH,
) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    taxonomy = _load_taxonomy(taxonomy_path)

    categories: list[dict] = taxonomy.get("categories", [])

    allowed_categories = "\n".join(f"- {c['id']}" for c in categories)

    return template.replace("{ALLOWED_CATEGORIES}", allowed_categories)
