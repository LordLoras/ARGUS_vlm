from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "taxonomy.yaml"
_ALIASES_PATH = Path(__file__).with_name("brands_aliases.yaml")

_SYMBOL_RE = re.compile(r"[®™©]")
_WS_RE = re.compile(r"\s+")


@lru_cache(maxsize=1)
def _load_aliases(path: str = str(_TAXONOMY_PATH)) -> dict[str, str]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        aliases = {k.lower(): v for k, v in (data.get("brand_aliases") or {}).items()}
        if aliases:
            return aliases
    except Exception:
        pass
    try:
        data = yaml.safe_load(_ALIASES_PATH.read_text(encoding="utf-8")) or {}
        return {k.lower(): v for k, v in (data.get("aliases") or {}).items()}
    except Exception:
        return {}


def _normalize_key(name: str) -> str:
    name = _SYMBOL_RE.sub("", name)
    name = _WS_RE.sub(" ", name).strip().lower()
    return name


def brand_normalize(name: str | None, *, aliases_path: Path | None = None) -> str | None:
    if not name:
        return None
    key = _normalize_key(name)
    aliases = _load_aliases(str(aliases_path) if aliases_path else str(_TAXONOMY_PATH))
    return aliases.get(key, name.strip())
