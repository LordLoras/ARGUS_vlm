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

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_PROMPT_PATH = _PROMPTS_DIR / "argus_ad_verifier.txt"
_FRONTIER_PROMPT_PATH = _PROMPTS_DIR / "argus_ad_verifier_frontier_strict.txt"
_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "taxonomy.yaml"

PROMPT_PROFILE_OPTIONS: dict[str, dict[str, str]] = {
    "auto": {
        "label": "Auto by route",
        "description": "Use the strict Frontier prompt for Frontier routing and the standard prompt elsewhere.",
    },
    "standard": {
        "label": "Standard",
        "description": "Full guided verifier prompt for local and smaller OpenAI-compatible models.",
    },
    "frontier_strict": {
        "label": "Frontier strict",
        "description": "Compact evidence-only extractor prompt for Kimi, Gemini, Qwen-VL, and other strong models.",
    },
}

_PROMPT_PATHS = {
    "standard": _PROMPT_PATH,
    "frontier_strict": _FRONTIER_PROMPT_PATH,
}


def resolve_prompt_profile(profile: str = "auto", *, mode: str | None = None) -> str:
    if profile == "auto":
        return "frontier_strict" if mode == "frontier" else "standard"
    if profile in _PROMPT_PATHS:
        return profile
    return "standard"


def _prompt_path_for_profile(profile: str) -> Path:
    return _PROMPT_PATHS[resolve_prompt_profile(profile)]


def get_prompt_version(profile: str = "standard", *, prompt_path: Path | None = None) -> str:
    path = prompt_path or _prompt_path_for_profile(profile)
    first_line = path.read_text(encoding="utf-8").split("\n")[0]
    for part in first_line.split(":"):
        part = part.strip()
        if part.startswith("verifier-"):
            return part
    return "unknown"


def _load_taxonomy(path: Path = _TAXONOMY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def render_verifier_prompt(
    *,
    prompt_profile: str = "standard",
    prompt_path: Path | None = None,
    taxonomy_path: Path = _TAXONOMY_PATH,
    iab_taxonomy_path: Path = DEFAULT_IAB_TAXONOMY_PATH,
    iab_content_taxonomy_path: Path = DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
    knowledge_manager: Any | None = None,
) -> str:
    template_path = prompt_path or _prompt_path_for_profile(prompt_profile)
    template = template_path.read_text(encoding="utf-8")
    taxonomy = _load_taxonomy(taxonomy_path)

    categories: list[dict] = taxonomy.get("categories", [])

    allowed_categories = "\n".join(f"- {c['id']}" for c in categories)

    if knowledge_manager is not None:
        iab_taxonomy = knowledge_manager.render_product_taxonomy_for_prompt()
        iab_content_taxonomy = knowledge_manager.render_content_taxonomy_for_prompt()
        render_guidance = getattr(knowledge_manager, "render_runtime_guidance_for_prompt", None)
        runtime_guidance = (
            render_guidance() if render_guidance else "- no editable taxonomy rules configured"
        )
        if "no IAB product taxonomy loaded" in iab_taxonomy:
            iab_taxonomy = render_iab_taxonomy_for_prompt(iab_taxonomy_path)
        if "no IAB content taxonomy loaded" in iab_content_taxonomy:
            iab_content_taxonomy = render_iab_content_taxonomy_for_prompt(iab_content_taxonomy_path)
    else:
        iab_taxonomy = render_iab_taxonomy_for_prompt(iab_taxonomy_path)
        iab_content_taxonomy = render_iab_content_taxonomy_for_prompt(iab_content_taxonomy_path)
        runtime_guidance = "- no editable taxonomy rules configured"

    return (
        template.replace("{ALLOWED_CATEGORIES}", allowed_categories)
        .replace("{IAB_PRODUCT_TAXONOMY}", iab_taxonomy)
        .replace("{IAB_CONTENT_TAXONOMY}", iab_content_taxonomy)
        .replace("{TAXONOMY_RUNTIME_GUIDANCE}", runtime_guidance)
    )
