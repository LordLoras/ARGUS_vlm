from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_ALIASES_PATH = Path(__file__).with_name("brands_aliases.yaml")

# Strips registered/trademark/copyright symbols
_SYMBOL_RE = re.compile(r"[®™©]")
_WS_RE = re.compile(r"\s+")


@lru_cache(maxsize=1)
def _load_aliases(path: str = str(_ALIASES_PATH)) -> dict[str, str]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {k.lower(): v for k, v in (data.get("aliases") or {}).items()}


def _normalize_key(name: str) -> str:
    name = _SYMBOL_RE.sub("", name)
    name = _WS_RE.sub(" ", name).strip().lower()
    return name


def brand_normalize(name: str | None, *, aliases_path: Path = _ALIASES_PATH) -> str | None:
    if not name:
        return None
    key = _normalize_key(name)
    aliases = _load_aliases(str(aliases_path))
    return aliases.get(key, name.strip())
