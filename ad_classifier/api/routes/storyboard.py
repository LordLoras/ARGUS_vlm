from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ad_classifier.api.deps import get_config, get_config_file, open_request_db
from ad_classifier.config import resolve_config_path
from ad_classifier.creative.storyboard import build_storyboard

router = APIRouter(tags=["storyboard"])


@router.post("/ads/{ad_id}/storyboard")
def create_storyboard(ad_id: str, request: Request) -> dict:
    config = get_config(request)
    config_file = get_config_file(request)
    out_root = resolve_config_path(config.paths.out, config_file)
    conn = open_request_db(request)
    try:
        try:
            storyboard = build_storyboard(conn, ad_id, out_root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return storyboard.model_dump(mode="json")
    finally:
        conn.close()
