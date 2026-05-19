from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ad_classifier.iab_content_taxonomy import (
    DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
    render_iab_content_taxonomy_for_prompt,
)
from ad_classifier.iab_taxonomy import (
    DEFAULT_IAB_TAXONOMY_PATH,
    render_iab_taxonomy_for_prompt,
)

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "argus_ad_verifier.txt"
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
    iab_taxonomy_path: Path = DEFAULT_IAB_TAXONOMY_PATH,
    iab_content_taxonomy_path: Path = DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
    knowledge_manager: Any | None = None,
) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    taxonomy = _load_taxonomy(taxonomy_path)

    categories: list[dict] = taxonomy.get("categories", [])

    allowed_categories = "\n".join(f"- {c['id']}" for c in categories)

    if knowledge_manager is not None:
        iab_taxonomy = knowledge_manager.render_product_taxonomy_for_prompt()
        iab_content_taxonomy = knowledge_manager.render_content_taxonomy_for_prompt()
    else:
        iab_taxonomy = render_iab_taxonomy_for_prompt(iab_taxonomy_path)
        iab_content_taxonomy = render_iab_content_taxonomy_for_prompt(iab_content_taxonomy_path)

    return (
        template.replace("{ALLOWED_CATEGORIES}", allowed_categories)
        .replace("{IAB_PRODUCT_TAXONOMY}", iab_taxonomy)
        .replace("{IAB_CONTENT_TAXONOMY}", iab_content_taxonomy)
    )
