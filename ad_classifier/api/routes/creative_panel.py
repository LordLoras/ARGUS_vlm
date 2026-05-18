from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, HTTPException, Request

from ad_classifier.agent.client import AgentClient, HTTPAgentClient
from ad_classifier.api.deps import get_config, get_config_file, open_request_db
from ad_classifier.config import AppConfig, resolve_config_path
from ad_classifier.creative.panel import (
    CreativeDebateRequest,
    CreativePanelRequest,
    build_creative_debate,
    build_creative_panel,
    list_personas,
)

router = APIRouter(tags=["creative-panel"])

PanelClientFactory = Callable[[AppConfig], AgentClient]
CREATIVE_PANEL_BODY = Body(default_factory=CreativePanelRequest)
CREATIVE_DEBATE_BODY = Body(default_factory=CreativeDebateRequest)


@router.get("/creative-panel/personas")
def get_creative_panel_personas() -> dict[str, list[dict[str, str]]]:
    return {"items": list_personas()}


@router.post("/ads/{ad_id}/creative-panel")
def create_creative_panel(
    ad_id: str,
    request: Request,
    body: CreativePanelRequest = CREATIVE_PANEL_BODY,
) -> dict:
    config = get_config(request)
    config_file = get_config_file(request)
    out_root = resolve_config_path(config.paths.out, config_file)
    llm_client = _panel_client_factory(request)(config) if body.use_vlm else None
    conn = open_request_db(request)
    try:
        try:
            report = build_creative_panel(
                conn,
                ad_id,
                out_root,
                body.persona_ids,
                use_vlm=body.use_vlm,
                llm_client=llm_client,
                source_model=config.vlm.endpoint.model,
                thinking=body.enable_reasoning,
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "ad not found" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return report.model_dump(mode="json")
    finally:
        conn.close()


@router.post("/ads/{ad_id}/creative-panel/debate")
def create_creative_debate(
    ad_id: str,
    request: Request,
    body: CreativeDebateRequest = CREATIVE_DEBATE_BODY,
) -> dict:
    config = get_config(request)
    config_file = get_config_file(request)
    out_root = resolve_config_path(config.paths.out, config_file)
    llm_client = _panel_client_factory(request)(config) if body.use_vlm else None
    conn = open_request_db(request)
    try:
        try:
            report = build_creative_debate(
                conn,
                ad_id,
                out_root,
                body.persona_ids,
                topic=body.topic,
                use_vlm=body.use_vlm,
                llm_client=llm_client,
                source_model=config.vlm.endpoint.model,
                thinking=body.enable_reasoning,
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "ad not found" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return report.model_dump(mode="json")
    finally:
        conn.close()


def _panel_client_factory(request: Request) -> PanelClientFactory:
    factory = getattr(request.app.state, "creative_panel_client_factory", None)
    if factory is not None:
        return factory  # type: ignore[no-any-return]
    return _default_panel_client_factory


def _default_panel_client_factory(config: AppConfig) -> AgentClient:
    endpoint = config.vlm.endpoint
    return HTTPAgentClient(
        endpoint=endpoint.endpoint,
        model=endpoint.model,
        api_key_env=endpoint.api_key_env,
        timeout_s=endpoint.timeout_s,
        max_retries=endpoint.max_retries,
        retry_delay_s=endpoint.retry_delay_s,
        temperature=endpoint.temperature,
        max_tokens=endpoint.max_tokens,
        stream=endpoint.stream,
    )
