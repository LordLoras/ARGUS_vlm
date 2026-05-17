from __future__ import annotations

import html
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from ad_classifier.api.deps import open_request_db
from ad_classifier.db.repositories import AdCampaignRepository, AdRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository

router = APIRouter(tags=["evidence"])


@router.get("/ads/{ad_id}/transcript")
def get_transcript(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        _require_ad(conn, ad_id)
        rows = conn.execute(
            """
            SELECT id, ad_id, start_ms, end_ms, text, confidence
            FROM transcript_segments
            WHERE ad_id = ?
            ORDER BY start_ms, id
            """,
            (ad_id,),
        ).fetchall()
        items = [dict(row) for row in rows]
        return {
            "ad_id": ad_id,
            "items": items,
            "full_text": " ".join(item["text"] for item in items if item.get("text")),
        }
    finally:
        conn.close()


@router.get("/ads/{ad_id}/ocr")
def get_ocr(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        _require_ad(conn, ad_id)
        rows = conn.execute(
            """
            SELECT
              o.id,
              f.ad_id,
              f.frame_index,
              f.time_ms,
              f.path AS frame_path,
              o.engine,
              o.text,
              o.bbox_json,
              o.confidence
            FROM frames f
            JOIN ocr_items o ON o.frame_id = f.id
            WHERE f.ad_id = ?
            ORDER BY f.frame_index, o.id
            """,
            (ad_id,),
        ).fetchall()
        return {"ad_id": ad_id, "items": [_ocr_row(row) for row in rows]}
    finally:
        conn.close()


@router.get("/ads/{ad_id}/export/evidence", response_model=None)
def export_evidence(
    ad_id: str,
    request: Request,
    format: Literal["json", "html"] = Query(default="json"),
):
    conn = open_request_db(request)
    try:
        payload = _evidence_payload(conn, ad_id)
        if format == "html":
            return HTMLResponse(_evidence_html(payload))
        return payload
    finally:
        conn.close()


def _require_ad(conn, ad_id: str):
    ad = AdRepository(conn).get(ad_id)
    if ad is None:
        raise HTTPException(status_code=404, detail="ad not found")
    return ad


def _evidence_payload(conn, ad_id: str) -> dict[str, Any]:
    ad = _require_ad(conn, ad_id)
    classification = ClassificationRepository(conn).get(ad_id)
    marketing = MarketingEntityRepository(conn).get(ad_id)
    campaigns = AdCampaignRepository(conn).list_for_ad(ad_id)
    frames = conn.execute(
        "SELECT * FROM frames WHERE ad_id = ? ORDER BY frame_index",
        (ad_id,),
    ).fetchall()
    rule_rows = conn.execute(
        "SELECT * FROM rule_triggers WHERE ad_id = ? ORDER BY time_ms, id",
        (ad_id,),
    ).fetchall()
    transcript = conn.execute(
        """
        SELECT id, ad_id, start_ms, end_ms, text, confidence
        FROM transcript_segments
        WHERE ad_id = ?
        ORDER BY start_ms, id
        """,
        (ad_id,),
    ).fetchall()
    ocr_rows = conn.execute(
        """
        SELECT
          o.id,
          f.ad_id,
          f.frame_index,
          f.time_ms,
          f.path AS frame_path,
          o.engine,
          o.text,
          o.bbox_json,
          o.confidence
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE f.ad_id = ?
        ORDER BY f.frame_index, o.id
        """,
        (ad_id,),
    ).fetchall()
    return {
        "ad": _dump(ad),
        "frames": [dict(row) for row in frames],
        "transcript": {
            "items": [dict(row) for row in transcript],
            "full_text": " ".join(row["text"] for row in transcript if row["text"]),
        },
        "ocr_items": [_ocr_row(row) for row in ocr_rows],
        "classification": _dump(classification),
        "marketing_entities": _dump(marketing),
        "campaigns": [_dump(campaign) for campaign in campaigns],
        "rule_triggers": [dict(row) for row in rule_rows],
    }


def _ocr_row(row) -> dict[str, Any]:
    item = dict(row)
    bbox = item.pop("bbox_json", None)
    item["bbox"] = json.loads(bbox) if bbox else None
    return item


def _evidence_html(payload: dict[str, Any]) -> str:
    ad = payload["ad"]
    title = html.escape(ad.get("id", "ad"))
    brand = html.escape(str(ad.get("brand_name") or "Unknown brand"))
    category = html.escape(str(ad.get("primary_category") or "Uncategorized"))
    transcript = html.escape(payload["transcript"]["full_text"] or "")
    ocr_items = payload["ocr_items"]
    evidence = (payload.get("classification") or {}).get("evidence") or []
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('time_ms') or 0))}</td>"
        f"<td>{html.escape(str(item.get('frame_index') or ''))}</td>"
        f"<td>{html.escape(str(item.get('source') or item.get('engine') or ''))}</td>"
        f"<td>{html.escape(str(item.get('text') or ''))}</td>"
        "</tr>"
        for item in [*ocr_items, *evidence]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>ARGUS Evidence Export - {title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 32px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ text-align: left; background: #f3f4f6; }}
    .meta {{ color: #4b5563; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">{brand} / {category}</p>
  <h2>Transcript</h2>
  <p>{transcript}</p>
  <h2>Evidence</h2>
  <table>
    <thead><tr><th>Time ms</th><th>Frame</th><th>Source</th><th>Text</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""


def _dump(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
