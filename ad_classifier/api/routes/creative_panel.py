from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from ad_classifier.api.deps import get_config, get_config_file, open_request_db
from ad_classifier.config import resolve_config_path
from ad_classifier.creative.panel import CreativePanelRequest, build_creative_panel, list_personas

router = APIRouter(tags=["creative-panel"])


@router.get("/creative-panel/personas")
def get_creative_panel_personas() -> dict[str, list[dict[str, str]]]:
    return {"items": list_personas()}


@router.post("/ads/{ad_id}/creative-panel")
def create_creative_panel(
    ad_id: str,
    request: Request,
    body: CreativePanelRequest = Body(default_factory=CreativePanelRequest),
) -> dict:
    config = get_config(request)
    config_file = get_config_file(request)
    out_root = resolve_config_path(config.paths.out, config_file)
    conn = open_request_db(request)
    try:
        try:
            report = build_creative_panel(conn, ad_id, out_root, body.persona_ids)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message == "ad not found" else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return report.model_dump(mode="json")
    finally:
        conn.close()
