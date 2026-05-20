from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ad_classifier._env import (
    delete_dotenv_secret,
    dotenv_path,
    list_dotenv_key_names,
    set_dotenv_secret,
    validate_env_name,
)
from ad_classifier.api.deps import get_config, get_config_file
from ad_classifier.config import AppConfig, config_file_payload, save_config

router = APIRouter(tags=["settings"])


class SettingsUpdate(BaseModel):
    config: dict[str, Any]


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    value: str = Field(min_length=1)


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    return _settings_snapshot(request)


@router.put("/settings")
def update_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
    config_file = get_config_file(request)
    try:
        next_config = AppConfig.model_validate(body.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    save_config(next_config, config_file)
    request.app.state.config = next_config
    return _settings_snapshot(request)


@router.post("/settings/api-keys")
def add_api_key(body: ApiKeyCreate, request: Request) -> dict[str, Any]:
    config_file = get_config_file(request)
    try:
        set_dotenv_secret(
            body.name,
            body.value,
            dotenv_path(config_file.parent),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _settings_snapshot(request)


@router.delete("/settings/api-keys/{name}")
def remove_api_key(name: str, request: Request) -> dict[str, Any]:
    config_file = get_config_file(request)
    try:
        delete_dotenv_secret(name, dotenv_path(config_file.parent))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _settings_snapshot(request)


def _settings_snapshot(request: Request) -> dict[str, Any]:
    config = get_config(request)
    config_file = get_config_file(request)
    return {
        "config_path": str(config_file),
        "dotenv_path": str(dotenv_path(config_file.parent)),
        "config": config_file_payload(config),
        "api_keys": _api_key_records(config, config_file),
        "options": {
            "vlm_modes": [
                {
                    "value": "local",
                    "label": "Local",
                    "description": "LM Studio or another OpenAI-compatible model on this machine.",
                },
                {
                    "value": "remote",
                    "label": "Remote",
                    "description": "Direct OpenAI-compatible hosted endpoint.",
                },
                {
                    "value": "frontier",
                    "label": "Frontier",
                    "description": "OpenRouter/frontier-model route using an API key variable.",
                },
            ],
            "response_formats": ["json_object", "json_schema"],
            "glm_ocr_modes": ["local", "remote"],
            "devices": ["cpu", "cuda"],
        },
    }


def _api_key_records(config: AppConfig, config_file: Path) -> list[dict[str, Any]]:
    managed_keys = list_dotenv_key_names(dotenv_path(config_file.parent))
    configured = _configured_key_usage(config)
    names = sorted(managed_keys | set(configured))
    records: list[dict[str, Any]] = []
    for name in names:
        sources: list[str] = []
        if name in managed_keys:
            sources.append("env.local")
        if os.environ.get(name):
            sources.append("process")
        records.append(
            {
                "name": name,
                "available": bool(sources),
                "managed": name in managed_keys,
                "sources": sources,
                "used_by": sorted(configured.get(name, [])),
                "value": None,
                "redacted": True,
            }
        )
    return records


def _configured_key_usage(config: AppConfig) -> dict[str, set[str]]:
    usage: dict[str, set[str]] = {}

    def add(path: str, value: str | None) -> None:
        if not value:
            return
        try:
            name = validate_env_name(value)
        except ValueError:
            return
        usage.setdefault(name, set()).add(path)

    for mode in ("local", "remote", "frontier"):
        add(f"vlm.{mode}", getattr(config.vlm, mode).api_key_env)
    for mode in ("local", "remote"):
        add(f"glm_ocr.{mode}", getattr(config.glm_ocr, mode).api_key_env)
    add("agent.endpoint", config.agent.endpoint.api_key_env)
    add("creative_panel.endpoint", config.creative_panel.endpoint.api_key_env)
    return usage
