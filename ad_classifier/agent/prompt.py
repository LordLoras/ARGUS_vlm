from __future__ import annotations

from importlib import resources
from pathlib import Path

from ad_classifier.agent.catalog import ToolCatalog

DEFAULT_PROMPT_FILENAME = "gemma_agent_system.txt"


def _load_template(prompt_path: Path | None = None) -> str:
    if prompt_path is not None:
        return prompt_path.read_text(encoding="utf-8")
    # Project root next to ad_classifier/ holds prompts/. Fall back to a built-in
    # minimal template if the project directory isn't available (eg. installed wheel).
    candidate = Path(__file__).resolve().parents[2] / "prompts" / DEFAULT_PROMPT_FILENAME
    if candidate.exists():
        return candidate.read_text(encoding="utf-8")
    try:
        return (
            resources.files("ad_classifier")
            .joinpath(f"../prompts/{DEFAULT_PROMPT_FILENAME}")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return _FALLBACK_TEMPLATE


_FALLBACK_TEMPLATE = (
    "You are a helpful analyst answering questions about a local database of "
    "classified video ads.\n\n"
    "You have read-only access to the following schema:\n{SCHEMA_SUMMARY}\n\n"
    "You can call these tools:\n{TOOL_CATALOG}\n\n"
    "Rules:\n"
    "- Prefer structured tools over sql_readonly when possible.\n"
    "- Always cite ad_ids and campaign_ids in your answer when referencing records.\n"
    "- If a tool returns truncated results, ask the user to narrow the filter.\n"
    "- Never fabricate ad_ids, brand names, or counts. If you don't know, call a tool.\n"
    "- Keep answers under 200 words unless asked for detail.\n"
)


def render_agent_prompt(
    catalog: ToolCatalog,
    schema_summary: str,
    *,
    prompt_path: Path | None = None,
) -> str:
    template = _load_template(prompt_path)
    return template.replace("{SCHEMA_SUMMARY}", schema_summary).replace(
        "{TOOL_CATALOG}", catalog.render_text_summary()
    )
