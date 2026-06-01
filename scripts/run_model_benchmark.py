from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ad_classifier._env import resolve_api_key
from ad_classifier.config import load_config
from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.pipeline.evidence.builder import build_evidence_bundle
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from ad_classifier.pipeline.rules.models import RuleTrigger
from ad_classifier.vlm.verifier import _build_content

ROOT = Path(__file__).resolve().parents[1]
ADS = [
    "ad_61e6c407",
    "ad_3271eca8",
    "ad_23506859",
    "ad_e7b406e5",
    "ad_e20a0bc4",
]

OPENROUTER_MODELS = [
    "openai/gpt-5.5",
    "google/gemini-3.5-flash",
    "minimax/minimax-m3",
    "stepfun/step-3.7-flash",
    "moonshotai/kimi-k2.6",
    "moonshotai/kimi-k2.5",
    "xiaomi/mimo-v2.5",
    "google/gemma-4-31b-it",
]

MODEL_PRICING_PER_M: dict[str, dict[str, float]] = {
    "openai/gpt-5.5": {"prompt": 5.0, "completion": 30.0},
    "google/gemini-3.5-flash": {"prompt": 1.5, "completion": 9.0},
    "minimax/minimax-m3": {"prompt": 0.3, "completion": 1.2},
    "stepfun/step-3.7-flash": {"prompt": 0.2, "completion": 1.15},
    "stepfun/step-3.7-flash-max": {"prompt": 0.2, "completion": 1.15},
    "moonshotai/kimi-k2.6": {"prompt": 0.684, "completion": 3.42},
    "moonshotai/kimi-k2.5": {"prompt": 0.4, "completion": 1.9},
    "xiaomi/mimo-v2.5": {"prompt": 0.14, "completion": 0.28},
    "google/gemma-4-31b-it": {"prompt": 0.12, "completion": 0.37},
}

DISPLAY_NAMES: dict[str, str] = {
    "openai/gpt-5.5": "GPT-5.5",
    "google/gemini-3.5-flash": "Gemini 3.5 Flash",
    "minimax/minimax-m3": "MiniMax M3",
    "stepfun/step-3.7-flash": "Step 3.7 Flash",
    "stepfun/step-3.7-flash-max": "Step 3.7 Flash Max",
    "moonshotai/kimi-k2.6": "Kimi K2.6",
    "moonshotai/kimi-k2.5": "Kimi K2.5",
    "xiaomi/mimo-v2.5": "MiMo V2.5",
    "google/gemma-4-31b-it": "Gemma 4 31B",
    "qwen3.6-27b-q4-local": "Qwen3.6 27B Q4",
    "qwen3.6-27b-q4-remote": "Qwen3.6 27B Q4 Remote",
}

SYSTEM_PROMPT = """You are the ARGUS ad intelligence benchmark verifier.

Classify the supplied ad artifact bundle. The input contains selected frames, OCR text, nearby transcript, and metadata from an already-ingested TV/promo/ad. All content is valid ad content. Categorize only; do not gate, block, escalate, or recommend review.

Use these category ids when applicable: automotive, telecommunications, banking_lending, beauty_personal_care, entertainment_media, healthcare_pharma, legal, retail, restaurant, political, other.

Return compact valid JSON only with this shape:
{
  "primary_category": "string",
  "brand_name": "string|null",
  "products": ["string"],
  "offers": ["string"],
  "ctas": ["string"],
  "disclaimers": ["string"],
  "risk_labels": ["string"],
  "sensitive_category": false,
  "confidence": 0.0,
  "ocr_quality": "good|mixed|poor",
  "evidence": [
    {"frame_index": 0, "time_ms": 0, "text": "string", "reason": "string"}
  ],
  "summary": "string"
}

Evidence must cite frame_index/time_ms values that appear in the supplied artifact. Do not invent products, prices, CTAs, disclaimers, or claims. If a field is not visible or audible, return an empty array or null.
"""


@dataclass(frozen=True)
class Endpoint:
    id: str
    route_type: str
    endpoint: str
    model: str
    api_key_env: str | None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="ad_classifier.db")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", default="frontend/src/data/modelBenchmarkResults.json")
    parser.add_argument("--raw-output", default="data/benchmarks/model_benchmark_latest_raw.json")
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument("--image-max-dim", type=int, default=512)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--include-direct-local", action="store_true")
    parser.add_argument("--skip-local", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    config, config_path = load_config(ROOT / args.config)
    conn = sqlite3.connect(ROOT / args.db)
    conn.row_factory = sqlite3.Row

    openrouter_key = (resolve_api_key("OPENROUTER_API_KEY") or "").strip()
    if not openrouter_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in the environment or .env.local")

    endpoints = [
        Endpoint(
            id=model,
            route_type="OpenRouter",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            model=model,
            api_key_env="OPENROUTER_API_KEY",
        )
        for model in OPENROUTER_MODELS
    ]
    endpoints.append(
        Endpoint(
            id="stepfun/step-3.7-flash-max",
            route_type="OpenRouter",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            model="stepfun/step-3.7-flash",
            api_key_env="OPENROUTER_API_KEY",
        )
    )
    endpoints.append(
        Endpoint(
            id="qwen3.6-27b-q4-remote",
            route_type="Remote",
            endpoint=normalize_chat_endpoint(config.vlm.remote.endpoint),
            model=config.vlm.remote.model,
            api_key_env=config.vlm.remote.api_key_env,
        )
    )
    if args.include_direct_local and not args.skip_local:
        endpoints.append(
            Endpoint(
                id="qwen3.6-27b-q4-local",
                route_type="Local",
                endpoint=normalize_chat_endpoint(config.vlm.local.endpoint),
                model=config.vlm.local.model,
                api_key_env=config.vlm.local.api_key_env,
            )
        )
    if args.only:
        only = set(args.only)
        endpoints = [endpoint for endpoint in endpoints if endpoint.id in only]
        if not endpoints:
            raise RuntimeError(f"No endpoints matched --only values: {sorted(only)}")

    references = {ad_id: reference_for_ad(conn, ad_id) for ad_id in ADS}
    ad_summaries = [ad_summary(conn, ad_id) for ad_id in ADS]
    bundles = {
        ad_id: build_benchmark_content(
            conn,
            ad_id,
            max_frames=args.max_frames,
            image_max_dim=args.image_max_dim,
        )
        for ad_id in ADS
    }

    raw_runs: list[dict[str, Any]] = []
    for endpoint in endpoints:
        print(f"== {endpoint.id} ==")
        for ad_id in ADS:
            print(f"  calling {ad_id}...", flush=True)
            run = call_model(endpoint, bundles[ad_id], timeout_s=args.timeout_s)
            score = score_output(run.get("parsed"), references[ad_id], run["parse_ok"])
            run.update(
                {
                    "ad_id": ad_id,
                    "score": score["total"],
                    "score_breakdown": score,
                }
            )
            print(
                "  ->",
                "ok" if run["ok"] else "failed",
                f"{run['elapsed_s']:.1f}s",
                f"score={score['total']:.1f}",
                flush=True,
            )
            raw_runs.append(run | {"model_id": endpoint.id})

    result = summarize_results(
        raw_runs=raw_runs,
        endpoints=endpoints,
        ads=ad_summaries,
        raw_output_path=args.raw_output,
    )

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    raw_path = ROOT / args.raw_output
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(
            {
                "generated_at": result["generated_at"],
                "config_path": str(config_path),
                "system_prompt": SYSTEM_PROMPT,
                "runs": raw_runs,
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    print(f"Wrote {raw_path}")


def build_benchmark_content(
    conn: sqlite3.Connection,
    ad_id: str,
    *,
    max_frames: int,
    image_max_dim: int,
) -> list[dict[str, Any]]:
    ad = conn.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)).fetchone()
    if ad is None:
        raise RuntimeError(f"Missing ad: {ad_id}")

    frames = [
        FrameAnalysis(
            frame_index=int(row["frame_index"]),
            time_ms=int(row["time_ms"]),
            path=ROOT / row["path"],
            phash=row["phash"],
            blur_score=row["blur_score"],
            kept=bool(row["kept"]),
            drop_reason=row["drop_reason"],
        )
        for row in conn.execute(
            """
            SELECT frame_index, time_ms, path, kept, drop_reason, phash, blur_score
            FROM frames
            WHERE ad_id = ? AND kept = 1
            ORDER BY frame_index
            """,
            (ad_id,),
        )
    ]

    segments = [
        TranscriptSegment(
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            text=row["text"],
            confidence=row["confidence"],
        )
        for row in conn.execute(
            """
            SELECT start_ms, end_ms, text, confidence
            FROM transcript_segments
            WHERE ad_id = ?
            ORDER BY start_ms, end_ms
            """,
            (ad_id,),
        )
    ]
    transcript = WhisperTranscript(
        segments=segments,
        duration_ms=ad["duration_ms"],
        text=" ".join(segment.text for segment in segments),
    )

    ocr_by_frame: dict[int, list[OCRItem]] = {}
    for row in conn.execute(
        """
        SELECT f.frame_index, f.time_ms, o.text, o.confidence, o.bbox_json, o.engine
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE f.ad_id = ?
        ORDER BY f.frame_index, o.id
        """,
        (ad_id,),
    ):
        bbox = json.loads(row["bbox_json"]) if row["bbox_json"] else None
        item = OCRItem(
            frame_index=int(row["frame_index"]),
            time_ms=int(row["time_ms"]),
            text=row["text"],
            confidence=row["confidence"],
            bbox=bbox,
            engine=row["engine"],
        )
        ocr_by_frame.setdefault(item.frame_index, []).append(item)

    rules = [
        RuleTrigger(
            rule_id=row["rule_id"],
            category=row["category"],
            risk_label=row["risk_label"],
            severity=row["severity"] or "medium",
            evidence_text=row["evidence_text"] or "",
            source="ocr" if row["frame_index"] is not None else "transcript",
            time_ms=row["time_ms"],
            frame_index=row["frame_index"],
        )
        for row in conn.execute(
            """
            SELECT rule_id, category, risk_label, severity, evidence_text, time_ms, frame_index
            FROM rule_triggers
            WHERE ad_id = ?
            ORDER BY frame_index, time_ms
            """,
            (ad_id,),
        )
    ]

    metadata = {
        "duration_ms": ad["duration_ms"],
        "width": ad["width"],
        "height": ad["height"],
        "fps": ad["fps"],
        "source_filename": Path(ad["source_path"]).name,
    }
    bundle = build_evidence_bundle(
        ad_id=ad_id,
        kept_frames=frames,
        transcript=transcript,
        rules_triggered=rules,
        ocr_by_frame=ocr_by_frame,
        alignment_window_ms=1500,
        max_frames=max_frames,
        metadata=metadata,
    )
    return _build_content(bundle, image_max_dim=image_max_dim)


def call_model(endpoint: Endpoint, content: list[dict[str, Any]], *, timeout_s: float) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if endpoint.api_key_env:
        api_key = (resolve_api_key(endpoint.api_key_env) or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    if endpoint.route_type == "OpenRouter":
        headers["HTTP-Referer"] = "https://argus.rest"
        headers["X-Title"] = "ARGUS model benchmark"

    payload: dict[str, Any] = {
        "model": endpoint.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
        "max_tokens": max_tokens_for(endpoint.id),
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    if endpoint.id == "openai/gpt-5.5":
        payload.pop("temperature", None)
    if endpoint.route_type == "OpenRouter":
        if endpoint.id == "stepfun/step-3.7-flash":
            payload["reasoning"] = {"effort": "low", "exclude": True}
        elif endpoint.id == "stepfun/step-3.7-flash-max":
            payload["reasoning"] = {"effort": "xhigh", "exclude": True}
        elif endpoint.id == "google/gemini-3.5-flash":
            payload["reasoning"] = {"effort": "low", "exclude": True}
        else:
            payload["reasoning"] = {"effort": "none", "exclude": True}
            payload["include_reasoning"] = False
    else:
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(endpoint.endpoint, headers=headers, json=payload)
        elapsed = time.perf_counter() - started
        text = response.text
        if response.status_code >= 400:
            return {
                "ok": False,
                "parse_ok": False,
                "elapsed_s": round(elapsed, 3),
                "status_code": response.status_code,
                "error": sanitize_error(text[:1200]),
                "raw_content": "",
                "parsed": None,
                "usage": {},
            }
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        raw = message.get("content") or message.get("reasoning_content") or ""
        parsed, parse_error = parse_json(raw)
        return {
            "ok": True,
            "parse_ok": parsed is not None,
            "elapsed_s": round(elapsed, 3),
            "status_code": response.status_code,
            "finish_reason": data.get("choices", [{}])[0].get("finish_reason"),
            "error": parse_error,
            "raw_content": raw,
            "parsed": parsed,
            "usage": data.get("usage", {}),
        }
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return {
            "ok": False,
            "parse_ok": False,
            "elapsed_s": round(elapsed, 3),
            "status_code": None,
            "error": sanitize_error(str(exc)),
            "raw_content": "",
            "parsed": None,
            "usage": {},
        }


def parse_json(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    if not raw.strip():
        return None, "empty response"
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else None, None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None, "no JSON object found"
    try:
        loaded = json.loads(match.group(0))
        return loaded if isinstance(loaded, dict) else None, None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def reference_for_ad(conn: sqlite3.Connection, ad_id: str) -> dict[str, Any]:
    ad = conn.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)).fetchone()
    cls = conn.execute("SELECT * FROM classifications WHERE ad_id = ?", (ad_id,)).fetchone()
    ent = conn.execute("SELECT * FROM marketing_entities WHERE ad_id = ?", (ad_id,)).fetchone()
    if ad is None:
        raise RuntimeError(f"Missing ad: {ad_id}")

    return {
        "primary_category": ad["primary_category"] or (cls["primary_category"] if cls else None),
        "brand_name": ad["brand_name"],
        "products": json_load(ent["products_json"] if ent else None, fallback=[]),
        "products_text": ad["products_text"] or "",
        "offers": json_load(ent["offers_json"] if ent else None, fallback=[]),
        "ctas": json_load(ent["ctas_json"] if ent else None, fallback=[]),
        "disclaimers": json_load(ent["disclaimers_json"] if ent else None, fallback=[]),
        "risk_labels": json_load(cls["risk_labels_json"] if cls else None, fallback=[]),
        "evidence": json_load(cls["evidence_json"] if cls else None, fallback=[]),
    }


def ad_summary(conn: sqlite3.Connection, ad_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT a.id, a.brand_name, a.products_text, a.primary_category, a.duration_ms,
               COUNT(f.id) AS frame_count,
               SUM(CASE WHEN f.kept THEN 1 ELSE 0 END) AS kept_frames,
               (SELECT COUNT(*) FROM transcript_segments t WHERE t.ad_id = a.id) AS transcript_segments,
               (SELECT COUNT(*) FROM ocr_items o JOIN frames fx ON fx.id = o.frame_id WHERE fx.ad_id = a.id) AS ocr_items
        FROM ads a
        LEFT JOIN frames f ON f.ad_id = a.id
        WHERE a.id = ?
        GROUP BY a.id
        """,
        (ad_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Missing ad: {ad_id}")
    return {
        "id": row["id"],
        "label": label_for_ad(row),
        "brand": row["brand_name"] or "Unknown",
        "category": row["primary_category"] or "other",
        "duration_s": round((row["duration_ms"] or 0) / 1000, 1),
        "frame_count": row["frame_count"],
        "kept_frames": row["kept_frames"],
        "ocr_items": row["ocr_items"],
        "transcript_segments": row["transcript_segments"],
        "difficulty": difficulty_for_ad(ad_id),
        "focus": focus_for_ad(ad_id),
    }


def score_output(parsed: dict[str, Any] | None, ref: dict[str, Any], parse_ok: bool) -> dict[str, float]:
    if not parsed:
        return {
            "total": 0.0,
            "parse": 0.0,
            "category": 0.0,
            "brand": 0.0,
            "products": 0.0,
            "offers_ctas_disclaimers": 0.0,
            "evidence": 0.0,
            "confidence_quality": 0.0,
        }

    category = 20.0 if normalize(parsed.get("primary_category")) == normalize(ref["primary_category"]) else 0.0
    brand = soft_text_score(parsed.get("brand_name"), ref.get("brand_name")) * 15.0
    products = list_overlap_score(
        as_text_list(parsed.get("products")),
        as_text_list(ref.get("products")) or [ref.get("products_text", "")],
    ) * 15.0
    offer_parts = (
        as_text_list(parsed.get("offers"))
        + as_text_list(parsed.get("ctas"))
        + as_text_list(parsed.get("disclaimers"))
    )
    ref_offer_parts = (
        as_text_list(ref.get("offers"))
        + as_text_list(ref.get("ctas"))
        + as_text_list(ref.get("disclaimers"))
    )
    if not ref_offer_parts:
        offers = 15.0 if offer_parts == [] else 11.0
    else:
        offers = list_overlap_score(offer_parts, ref_offer_parts) * 15.0

    evidence = evidence_score(parsed.get("evidence")) * 15.0
    confidence_quality = 0.0
    if isinstance(parsed.get("confidence"), int | float) and 0 <= float(parsed["confidence"]) <= 1:
        confidence_quality += 4.0
    if str(parsed.get("ocr_quality", "")).casefold() in {"good", "mixed", "poor"}:
        confidence_quality += 3.0
    if isinstance(parsed.get("summary"), str) and len(parsed["summary"].strip()) >= 20:
        confidence_quality += 3.0

    total = (
        (10.0 if parse_ok else 0.0)
        + category
        + brand
        + products
        + offers
        + evidence
        + confidence_quality
    )
    return {
        "total": round(min(100.0, total), 2),
        "parse": round(10.0 if parse_ok else 0.0, 2),
        "category": round(category, 2),
        "brand": round(brand, 2),
        "products": round(products, 2),
        "offers_ctas_disclaimers": round(offers, 2),
        "evidence": round(evidence, 2),
        "confidence_quality": round(confidence_quality, 2),
    }


def evidence_score(value: Any) -> float:
    if not isinstance(value, list):
        return 0.0
    valid = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("frame_index"), int):
            continue
        if not isinstance(item.get("time_ms"), int):
            continue
        if not str(item.get("text") or item.get("reason") or "").strip():
            continue
        valid += 1
    return min(1.0, valid / 3.0)


def list_overlap_score(predicted: list[str], reference: list[str]) -> float:
    pred_tokens = tokens(" ".join(predicted))
    ref_tokens = tokens(" ".join(reference))
    if not ref_tokens:
        return 1.0 if not pred_tokens else 0.55
    if not pred_tokens:
        return 0.0
    precision = len(pred_tokens & ref_tokens) / len(pred_tokens)
    recall = len(pred_tokens & ref_tokens) / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def soft_text_score(predicted: Any, reference: Any) -> float:
    pred = normalize(predicted)
    ref = normalize(reference)
    if not ref:
        return 1.0 if not pred else 0.5
    if not pred:
        return 0.0
    if pred == ref or pred in ref or ref in pred:
        return 1.0
    return list_overlap_score([pred], [ref])


def tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) >= 2}


def normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("&", "and").split())


def as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    out.append(item)
            elif isinstance(item, dict):
                text = " ".join(str(v) for v in item.values() if v is not None and not isinstance(v, list | dict))
                if text.strip():
                    out.append(text)
        return out
    if isinstance(value, dict):
        text = " ".join(str(v) for v in value.values() if v is not None and not isinstance(v, list | dict))
        return [text] if text.strip() else []
    return [str(value)]


def summarize_results(
    *,
    raw_runs: list[dict[str, Any]],
    endpoints: list[Endpoint],
    ads: list[dict[str, Any]],
    raw_output_path: str,
) -> dict[str, Any]:
    by_model: list[dict[str, Any]] = []
    for endpoint in endpoints:
        runs = [run for run in raw_runs if run["model_id"] == endpoint.id]
        successful = [run for run in runs if run["ok"]]
        score = sum(run["score"] for run in runs) / len(runs) if runs else 0.0
        elapsed = sum(float(run["elapsed_s"]) for run in runs)
        prompt_tokens = sum(int(run.get("usage", {}).get("prompt_tokens") or 0) for run in runs)
        completion_tokens = sum(int(run.get("usage", {}).get("completion_tokens") or 0) for run in runs)
        cost = cost_for_model(endpoint.id, prompt_tokens, completion_tokens)
        by_model.append(
            {
                "id": endpoint.id,
                "name": DISPLAY_NAMES.get(endpoint.id, endpoint.id),
                "provider": provider_for_endpoint(endpoint.id),
                "route_type": endpoint.route_type,
                "endpoint": endpoint.endpoint,
                "model": endpoint.model,
                "thinking_off": thinking_off_for(endpoint.id, endpoint.route_type),
                "score": round(score, 2),
                "completion_seconds": round(elapsed, 2),
                "successful_ads": len(successful),
                "total_ads": len(runs),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_cost_usd": cost,
                "readout": readout_for_model(endpoint.id),
                "cases": [
                    {
                        "ad_id": run["ad_id"],
                        "score": run["score"],
                        "seconds": run["elapsed_s"],
                        "ok": run["ok"],
                        "parse_ok": run["parse_ok"],
                        "error": run.get("error"),
                        "note": note_for_case(run),
                        "breakdown": run["score_breakdown"],
                    }
                    for run in runs
                ],
            }
        )

    leader = max((row["score"] for row in by_model), default=1.0)
    paid_values = [
        row["score"] / row["estimated_cost_usd"]
        for row in by_model
        if row["route_type"] == "OpenRouter" and row["estimated_cost_usd"] > 0
    ]
    best_value = max(paid_values, default=1.0)
    for row in by_model:
        row["relative_performance_pct"] = round((row["score"] / leader) * 100, 1) if leader else 0.0
        if row["route_type"] == "OpenRouter" and row["estimated_cost_usd"] > 0:
            row["performance_price_index"] = round(
                ((row["score"] / row["estimated_cost_usd"]) / best_value) * 100,
                1,
            )
        elif row["route_type"] == "Local":
            row["performance_price_index"] = None
        else:
            row["performance_price_index"] = None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_date_label": "June 1, 2026",
        "source": "actual OpenRouter/local endpoint calls",
        "raw_output_path": raw_output_path,
        "protocol": {
            "temperature": "0 where supported; GPT-5.5 uses provider default because temperature is not listed for that route",
            "max_tokens": "1600, StepFun low uses 4096, StepFun Max uses 8192",
            "response_format": "json_object",
            "openrouter_thinking": (
                'reasoning.effort="none" except mandatory-reasoning routes: '
                'StepFun low and Gemini 3.5 Flash use "low"; StepFun Max uses "xhigh"'
            ),
            "local_thinking": "chat_template_kwargs.enable_thinking=false",
            "scoring": "Automatic rubric: parse/schema 10, category 20, brand 15, products 15, offers/CTAs/disclaimers 15, timestamp evidence 15, confidence/OCR/summary 10.",
        },
        "ads": ads,
        "models": sorted(by_model, key=lambda row: row["score"], reverse=True),
    }


def cost_for_model(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = MODEL_PRICING_PER_M.get(model_id)
    if not pricing:
        return 0.0
    return round(
        (prompt_tokens * pricing["prompt"] / 1_000_000)
        + (completion_tokens * pricing["completion"] / 1_000_000),
        6,
    )


def json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def label_for_ad(row: sqlite3.Row) -> str:
    product = row["products_text"]
    if product:
        return str(product).split(",")[0][:48]
    return f"{row['brand_name'] or 'Ad'} spot"


def difficulty_for_ad(ad_id: str) -> str:
    return {
        "ad_61e6c407": "Easy",
        "ad_3271eca8": "Medium",
        "ad_23506859": "Hard",
        "ad_e7b406e5": "Hard",
        "ad_e20a0bc4": "Stress",
    }.get(ad_id, "Medium")


def focus_for_ad(ad_id: str) -> list[str]:
    return {
        "ad_61e6c407": ["category", "brand", "basic evidence"],
        "ad_3271eca8": ["product", "CTA", "offer copy"],
        "ad_23506859": ["regulated category", "claim grounding", "offer terms"],
        "ad_e7b406e5": ["dense OCR", "claims", "disclaimers"],
        "ad_e20a0bc4": ["multi-product", "fine print", "timestamp evidence"],
    }.get(ad_id, [])


def provider_for_endpoint(model_id: str) -> str:
    if model_id.startswith("stepfun/"):
        return "StepFun"
    if model_id.startswith("moonshotai/"):
        return "MoonshotAI"
    if model_id.startswith("xiaomi/"):
        return "Xiaomi"
    if model_id.startswith("google/"):
        return "Google"
    if model_id.startswith("minimax/"):
        return "MiniMax"
    if model_id.startswith("openai/"):
        return "OpenAI"
    if model_id.startswith("qwen"):
        return "Qwen endpoint"
    return "Reference"


def readout_for_model(model_id: str) -> str:
    return {
        "openai/gpt-5.5": "Measured frontier route; highest expected reasoning quality with materially higher provider cost.",
        "google/gemini-3.5-flash": "Measured current high-efficiency Gemini route; OpenRouter requires low reasoning on this endpoint.",
        "minimax/minimax-m3": "Measured MiniMax multimodal long-context route; currently priced as a low-cost OpenRouter route.",
        "moonshotai/kimi-k2.6": "Measured strongest overall quality on the selected artifact ladder.",
        "moonshotai/kimi-k2.5": "Measured balanced quality and cost with a lower dense-OCR ceiling than K2.6.",
        "stepfun/step-3.7-flash": "Measured fast paid route; useful for cleaner artifacts.",
        "xiaomi/mimo-v2.5": "Measured low-cost route; schema and dense extraction decide its usefulness.",
        "google/gemma-4-31b-it": "Measured low-cost route with strong price/performance when parse quality holds.",
        "stepfun/step-3.7-flash-max": "Measured StepFun with maximum OpenRouter reasoning effort for comparison.",
        "qwen3.6-27b-q4-local": "Measured local quantized route; provider cost is zero but latency is local hardware bound.",
        "qwen3.6-27b-q4-remote": "Measured custom remote-compatible endpoint for the Qwen quantized model.",
    }.get(model_id, "Measured benchmark row.")


def note_for_case(run: dict[str, Any]) -> str:
    if not run["ok"]:
        return "Call failed."
    if not run["parse_ok"]:
        return "Response did not parse as JSON."
    breakdown = run["score_breakdown"]
    weak = min(
        (
            ("category", breakdown["category"]),
            ("brand", breakdown["brand"]),
            ("products", breakdown["products"]),
            ("offers/CTA", breakdown["offers_ctas_disclaimers"]),
            ("evidence", breakdown["evidence"]),
        ),
        key=lambda item: item[1],
    )
    if weak[1] >= 12:
        return "Strong rubric match."
    return f"Weakest area: {weak[0]}."


def sanitize_error(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'"user_id"\s*:\s*"[^"]+"', '"user_id":"redacted"', text)
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer redacted", cleaned)
    return cleaned


def max_tokens_for(model_id: str) -> int:
    if model_id == "stepfun/step-3.7-flash":
        return 4096
    if model_id == "stepfun/step-3.7-flash-max":
        return 8192
    return 1600


def thinking_off_for(model_id: str, route_type: str) -> str:
    if route_type == "OpenRouter":
        if model_id == "stepfun/step-3.7-flash":
            return 'reasoning.effort="low"'
        if model_id == "stepfun/step-3.7-flash-max":
            return 'reasoning.effort="xhigh"'
        if model_id == "google/gemini-3.5-flash":
            return 'reasoning.effort="low"'
        return 'reasoning.effort="none"'
    return "enable_thinking=false"


def normalize_chat_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    if endpoint.endswith("/v1"):
        return f"{endpoint}/chat/completions"
    return f"{endpoint}/v1/chat/completions"


if __name__ == "__main__":
    main()
