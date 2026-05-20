from __future__ import annotations

import os
import re
from contextlib import suppress
from pathlib import Path

_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{1,79}$")
_dotenv_cache: dict[str, str] | None = None
_dotenv_cache_path: Path | None = None
_dotenv_cache_mtime_ns: int | None = None
_configured_dotenv_path: Path | None = None


def dotenv_path(base_dir: Path | None = None) -> Path:
    if base_dir is None and _configured_dotenv_path is not None:
        return _configured_dotenv_path
    env_path = os.environ.get("ARGUS_DOTENV_PATH")
    if base_dir is None and env_path:
        return Path(env_path).expanduser().resolve()
    return ((base_dir or Path.cwd()) / ".env.local").expanduser().resolve()


def configure_dotenv_path(path: Path) -> None:
    global _configured_dotenv_path
    _configured_dotenv_path = path.expanduser().resolve()
    os.environ["ARGUS_DOTENV_PATH"] = str(_configured_dotenv_path)
    clear_dotenv_cache()


def validate_env_name(name: str) -> str:
    normalized = name.strip().upper()
    if not _ENV_NAME_RE.fullmatch(normalized):
        raise ValueError("Environment variable names must be uppercase letters, numbers, and underscores")
    return normalized


def _load_dotenv(path: Path | None = None) -> dict[str, str]:
    global _dotenv_cache, _dotenv_cache_mtime_ns, _dotenv_cache_path

    source = (path or dotenv_path()).expanduser().resolve()
    mtime = source.stat().st_mtime_ns if source.is_file() else None
    if (
        _dotenv_cache is not None
        and _dotenv_cache_path == source
        and _dotenv_cache_mtime_ns == mtime
    ):
        return _dotenv_cache

    loaded: dict[str, str] = {}
    if source.is_file():
        for line in source.read_text(encoding="utf-8").splitlines():
            parsed = _parse_dotenv_assignment(line)
            if parsed is not None:
                key, value = parsed
                loaded[key] = value

    _dotenv_cache = loaded
    _dotenv_cache_path = source
    _dotenv_cache_mtime_ns = mtime
    return loaded


def clear_dotenv_cache() -> None:
    global _dotenv_cache, _dotenv_cache_mtime_ns, _dotenv_cache_path
    _dotenv_cache = None
    _dotenv_cache_mtime_ns = None
    _dotenv_cache_path = None


def resolve_api_key(key_name: str | None) -> str | None:
    if not key_name:
        return None
    normalized = validate_env_name(key_name)
    dotenv = _load_dotenv()
    value = dotenv.get(normalized)
    if value:
        return value
    value = os.environ.get(normalized)
    if value:
        return value.strip()
    return None


def list_dotenv_key_names(path: Path | None = None) -> set[str]:
    return set(_load_dotenv(path).keys())


def set_dotenv_secret(name: str, value: str, path: Path | None = None) -> None:
    key = validate_env_name(name)
    secret = value.strip()
    if not secret:
        raise ValueError("API key value cannot be empty")

    source = (path or dotenv_path()).expanduser().resolve()
    lines = _read_dotenv_lines(source)
    assignment = f'{key}="{_escape_dotenv_value(secret)}"'
    replaced = False
    output: list[str] = []
    for line in lines:
        parsed = _parse_dotenv_assignment(line)
        if parsed is not None and parsed[0] == key:
            if not replaced:
                output.append(assignment)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append(assignment)

    _write_dotenv_lines(source, output)
    clear_dotenv_cache()


def delete_dotenv_secret(name: str, path: Path | None = None) -> bool:
    key = validate_env_name(name)
    source = (path or dotenv_path()).expanduser().resolve()
    lines = _read_dotenv_lines(source)
    removed = False
    output: list[str] = []
    for line in lines:
        parsed = _parse_dotenv_assignment(line)
        if parsed is not None and parsed[0] == key:
            removed = True
            continue
        output.append(line)
    if removed:
        _write_dotenv_lines(source, output)
        clear_dotenv_cache()
    return removed


def _parse_dotenv_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, _, value = stripped.partition("=")
    key = key.strip()
    if not _ENV_NAME_RE.fullmatch(key):
        return None
    return key, _unquote_dotenv_value(value.strip())


def _unquote_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def _escape_dotenv_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r"\"")


def _read_dotenv_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write_dotenv_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    with suppress(OSError):
        path.chmod(0o600)
