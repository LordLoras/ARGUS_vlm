from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "gemma_ad_verifier.txt"
_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "taxonomy.yaml"


def _load_taxonomy(path: Path = _TAXONOMY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _build_subcategory_hints(categories: list[dict]) -> str:
    lines = ["Allowed subcategory values per category:"]
    for cat in categories:
        subs = cat.get("subcategories")
        if subs:
            lines.append(f"- {cat['id']}: {', '.join(subs)}")
    return "\n".join(lines)


def render_verifier_prompt(
    *,
    prompt_path: Path = _PROMPT_PATH,
    taxonomy_path: Path = _TAXONOMY_PATH,
) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    taxonomy = _load_taxonomy(taxonomy_path)

    categories: list[dict] = taxonomy.get("categories", [])
    risk_labels: list[str] = taxonomy.get("risk_labels", [])

    allowed_categories = "\n".join(f"- {c['id']}" for c in categories)
    allowed_risk_labels = "\n".join(f"- {r}" for r in risk_labels)
    subcategory_hints = _build_subcategory_hints(categories)

    return (
        template.replace("{ALLOWED_CATEGORIES}", allowed_categories)
        .replace("{ALLOWED_RISK_LABELS}", allowed_risk_labels)
        .replace("{SUBCATEGORY_HINTS}", subcategory_hints)
    )
