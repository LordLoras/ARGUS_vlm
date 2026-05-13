import os
from pathlib import Path

_dotenv_cache: dict[str, str] | None = None


def _load_dotenv() -> dict[str, str]:
    global _dotenv_cache
    if _dotenv_cache is not None:
        return _dotenv_cache
    _dotenv_cache = {}
    dotenv_path = Path(".env.local")
    if dotenv_path.is_file():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            _dotenv_cache[key.strip()] = value.strip().strip('"').strip("'")
    return _dotenv_cache


def resolve_api_key(key_name: str | None) -> str | None:
    if not key_name:
        return None
    dotenv = _load_dotenv()
    value = dotenv.get(key_name)
    if value:
        return value
    value = os.environ.get(key_name)
    if value:
        return value.strip()
    return None
