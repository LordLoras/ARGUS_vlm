from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

from ad_classifier.config import AppConfig
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.db.repositories import AdRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.dedup.similarity import enrich_related_ads
from ad_classifier.embeddings.image.base import ImageEmbedder
from ad_classifier.embeddings.image.siglip2 import SigLIP2ImageEmbedder
from ad_classifier.embeddings.text.base import TextEmbedder
from ad_classifier.embeddings.text.sentence_transformer import SentenceTransformerEmbedder
from ad_classifier.ingest.models import IngestArtifacts, IngestEvent, WhisperTranscript
from ad_classifier.ingest.service import IngestService
from ad_classifier.marketing.extract import enrich_marketing_entities
from ad_classifier.models.classification import ClassificationRecord, OCRQuality
from ad_classifier.pipeline.aggregation.policy import aggregate
from ad_classifier.pipeline.evidence import build_evidence_bundle
from ad_classifier.pipeline.ocr.engine import OCREngine, PaddleOCREngine
from ad_classifier.pipeline.ocr.models import FrameRef, OCRItem
from ad_classifier.pipeline.paddlevl.gating import should_run_paddlevl
from ad_classifier.pipeline.paddlevl.models import PaddleVLGatingConfig, PaddleVLOutput
from ad_classifier.pipeline.paddlevl.parser import DocumentParser, PaddleVLParser
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from ad_classifier.pipeline.preprocess.service import preprocess_frames
from ad_classifier.pipeline.rules.engine import RulesEngine
from ad_classifier.pipeline.rules.loader import load_rules
from ad_classifier.pipeline.rules.models import RuleTrigger
from ad_classifier.search.fts import fts_update
from ad_classifier.vectors.sqlite_vec import SqliteVecStore
from ad_classifier.vlm.cleanup import OCRCleanupPass
from ad_classifier.vlm.correction import SelfCorrectionPass
from ad_classifier.vlm.validation import validate_vlm_output
from ad_classifier.vlm.verifier import HTTPVLMVerifier, VLMVerifier

ProgressCallback = Callable[[str, float, str], None]


class PipelineComponents:
    def __init__(
        self,
        *,
        ocr_engine: OCREngine | None = None,
        document_parser: DocumentParser | None = None,
        vlm_verifier: VLMVerifier | None = None,
        text_embedder: TextEmbedder | None = None,
        image_embedder: ImageEmbedder | None = None,
    ) -> None:
        self.ocr_engine = ocr_engine
        self.document_parser = document_parser
        self.vlm_verifier = vlm_verifier
        self.text_embedder = text_embedder
        self.image_embedder = image_embedder


def run_pipeline_for_job(
    *,
    conn: sqlite3.Connection,
    config: AppConfig,
    config_file: Path,
    ad_id: str,
    components: PipelineComponents | None = None,
    progress: ProgressCallback | None = None,
) -> None:
    load_sqlite_vec(conn)
    components = components or PipelineComponents()
    ad = AdRepository(conn).get(ad_id)
    if ad is None:
        raise ValueError(f"ad not found: {ad_id}")

    def emit(stage: str, progress_value: float, message: str) -> None:
        if progress is not None:
            progress(stage, progress_value, message)

    ingest = _run_ingest(config, config_file, ad.source_path, ad_id, emit)
    if ingest.dedup.skipped:
        AdRepository(conn).update_status(ad_id, "duplicate")
        conn.commit()
        emit("dedup", 1.0, ingest.dedup.skip_reason or "duplicate")
        return

    emit("preprocess", 0.22, "preprocessing frames")
    preprocess_result = preprocess_frames(ingest.frames)
    _persist_frame_analysis(conn, ad_id, preprocess_result.frames)
    conn.commit()

    emit("ocr", 0.34, "extracting OCR")
    ocr_items = _run_ocr(
        components.ocr_engine or PaddleOCREngine(config.ocr.device, config.ocr.lang),
        preprocess_result.kept_frames,
    )
    _replace_ocr_items(conn, ad_id, ocr_items)
    conn.commit()

    emit("paddlevl", 0.45, "checking hard frames")
    paddlevl_by_frame = _run_paddlevl(
        config=config,
        components=components,
        kept_frames=preprocess_result.kept_frames,
        ocr_by_frame=_ocr_by_frame(ocr_items),
    )

    emit("rules", 0.52, "running rules")
    rules = RulesEngine(load_rules(config.rules.rules_path)).run(ocr_items, ingest.transcript)
    _replace_rule_triggers(conn, ad_id, rules)
    conn.commit()

    if config.vlm.enable_ocr_cleanup_pass:
        emit("vlm:cleanup", 0.56, "cleaning OCR text")
        ocr_items = _run_ocr_cleanup(config, ocr_items, ingest.transcript)

    emit("vlm", 0.64, "verifying classification")
    bundle = build_evidence_bundle(
        ad_id=ad_id,
        kept_frames=preprocess_result.kept_frames,
        transcript=ingest.transcript,
        rules_triggered=rules,
        ocr_by_frame=_ocr_by_frame(ocr_items),
        paddlevl_by_frame=paddlevl_by_frame,
        alignment_window_ms=config.rules.alignment_window_ms,
        max_frames=config.vlm.max_frames_in_bundle,
        metadata=ingest.metadata.model_dump() if ingest.metadata else {},
    )
    vlm = components.vlm_verifier or HTTPVLMVerifier(
        endpoint=config.vlm.endpoint.endpoint,
        model=config.vlm.endpoint.model,
        api_key_env=config.vlm.endpoint.api_key_env,
        timeout_s=config.vlm.endpoint.timeout_s,
        max_retries=config.vlm.endpoint.max_retries,
        retry_delay_s=config.vlm.endpoint.retry_delay_s,
        temperature=config.vlm.endpoint.temperature,
        max_tokens=config.vlm.endpoint.max_tokens,
        enable_thinking=config.vlm.endpoint.enable_thinking,
    )
    vlm_result = vlm.verify(bundle)

    if config.vlm.enable_post_validation:
        evidence_texts = _collect_evidence_texts(ocr_items, ingest.transcript)
        vlm_result = validate_vlm_output(vlm_result, evidence_texts)

    if config.vlm.enable_self_correction:
        emit("vlm:correct", 0.72, "self-correction check")
        evidence_texts = _collect_evidence_texts(ocr_items, ingest.transcript)
        vlm_result = _run_self_correction(config, vlm_result, evidence_texts)

    emit("embeddings", 0.78, "embedding ad")
    text_embedder = components.text_embedder or SentenceTransformerEmbedder(
        config.text_embedder.model,
        config.text_embedder.device,
    )
    image_embedder = components.image_embedder or SigLIP2ImageEmbedder(
        config.image_embedder.model,
        config.image_embedder.device,
    )
    text_vector, visual_vector = _write_embeddings(
        conn,
        config,
        ad_id,
        ingest,
        ocr_items,
        preprocess_result.kept_frames,
        text_embedder,
        image_embedder,
    )

    emit("persist", 0.9, "persisting classification")
    store = SqliteVecStore(
        conn,
        text_dim=config.vector_store.text_dim,
        visual_dim=config.vector_store.visual_dim,
    )
    store.ensure_tables()
    related = enrich_related_ads(
        store,
        ad_id,
        text_vector=text_vector,
        visual_vector=visual_vector,
        k=5,
        min_score=0.7,
    )
    final = aggregate(
        ad_id,
        vlm_result,
        rules,
        related_ads=related,
        vlm_model=config.vlm.endpoint.model,
        vlm_prompt_version="verifier-2026.05.07",
        pipeline_version="0.1.0",
    )
    final.marketing_entities = enrich_marketing_entities(
        final.marketing_entities,
        ocr_items=ocr_items,
        transcript=ingest.transcript,
    )
    ClassificationRepository(conn).upsert(
        ClassificationRecord(
            ad_id=ad_id,
            primary_category=final.primary_category,
            risk_labels=final.risk_labels,
            confidence=final.confidence,
            decision=final.decision,
            needs_human_review=final.needs_human_review,
            ocr_quality=_ocr_quality(vlm_result),
            vlm_raw=vlm_result.model_dump(),
            evidence=final.evidence,
            vlm_model=final.vlm_model,
            vlm_prompt_version=final.vlm_prompt_version,
            embedder_text_model=text_embedder.model_name,
            embedder_visual_model=image_embedder.model_name,
            pipeline_version=final.pipeline_version,
        )
    )
    MarketingEntityRepository(conn).upsert(ad_id, final.marketing_entities)
    AdRepository(conn).update_projection(
        ad_id,
        brand_name=final.marketing_entities.brand.name,
        brand_confidence=final.marketing_entities.brand.confidence,
        advertiser_name=final.marketing_entities.advertiser.advertiser_name,
        website_domain=final.marketing_entities.primary_website_domain,
        phone_number=final.marketing_entities.primary_phone_number,
        landing_page_domain=final.marketing_entities.landing_page.domain,
        products_text=final.marketing_entities.products_text,
        primary_category=final.primary_category,
        subcategory=final.marketing_entities.subcategory,
        decision=final.decision,
    )
    AdRepository(conn).update_status(ad_id, "completed")
    fts_update(
        conn,
        ad_id,
        brand=final.marketing_entities.brand.name or "",
        products=final.marketing_entities.products_text or "",
        primary_category=final.primary_category,
        transcript_text=ingest.transcript.text,
        ocr_text=" ".join(item.text for item in ocr_items),
        marketing_entities_text=json.dumps(final.marketing_entities.model_dump()),
    )
    conn.commit()
    emit("completed", 1.0, "job completed")


def _run_ingest(
    config: AppConfig,
    config_file: Path,
    source_path: str,
    ad_id: str,
    emit: ProgressCallback,
) -> IngestArtifacts:
    def ingest_progress(event: IngestEvent) -> None:
        emit(f"ingest:{event.stage}", 0.05, event.message)

    service = IngestService(config=config, config_file=config_file, progress=ingest_progress)
    return service.run(video_path=Path(source_path), ad_id=ad_id, persist=True)


def _run_ocr(engine: OCREngine, kept_frames: list[FrameAnalysis]) -> list[OCRItem]:
    items: list[OCRItem] = []
    for frame in kept_frames:
        items.extend(
            engine.extract(
                FrameRef(frame_index=frame.frame_index, time_ms=frame.time_ms, path=frame.path)
            )
        )
    return items


def _run_paddlevl(
    *,
    config: AppConfig,
    components: PipelineComponents,
    kept_frames: list[FrameAnalysis],
    ocr_by_frame: dict[int, list[OCRItem]],
) -> dict[int, PaddleVLOutput]:
    if not config.paddlevl.enabled:
        return {}
    gating = PaddleVLGatingConfig.model_validate(config.paddlevl.gating.model_dump())
    parser = components.document_parser or PaddleVLParser(
        config.paddlevl.command,
        config.paddlevl.timeout_s,
    )
    outputs: dict[int, PaddleVLOutput] = {}
    for frame in kept_frames:
        run, _reason = should_run_paddlevl(ocr_by_frame.get(frame.frame_index, []), gating, frame)
        if run:
            outputs[frame.frame_index] = parser.parse(
                FrameRef(frame_index=frame.frame_index, time_ms=frame.time_ms, path=frame.path)
            )
    return outputs


def _write_embeddings(
    conn: sqlite3.Connection,
    config: AppConfig,
    ad_id: str,
    ingest: IngestArtifacts,
    ocr_items: list[OCRItem],
    kept_frames: list[FrameAnalysis],
    text_embedder: TextEmbedder,
    image_embedder: ImageEmbedder,
) -> tuple[list[float], list[float] | None]:
    load_sqlite_vec(conn)
    store = SqliteVecStore(
        conn,
        text_dim=config.vector_store.text_dim,
        visual_dim=config.vector_store.visual_dim,
    )
    store.ensure_tables()
    text_corpus = "\n".join([ingest.transcript.text, " ".join(item.text for item in ocr_items)])
    text_vector = text_embedder.embed(text_corpus)
    store.upsert_text(ad_id, text_vector)
    visual_vectors = image_embedder.embed_batch([frame.path for frame in kept_frames])
    visual_vector = _mean_pool(visual_vectors)
    if visual_vector is not None:
        store.upsert_visual(ad_id, visual_vector)
    return text_vector, visual_vector


def _persist_frame_analysis(
    conn: sqlite3.Connection,
    ad_id: str,
    frames: list[FrameAnalysis],
) -> None:
    for frame in frames:
        conn.execute(
            """
            UPDATE frames
            SET kept = ?,
                drop_reason = ?,
                phash = ?,
                blur_score = ?
            WHERE ad_id = ? AND frame_index = ?
            """,
            (
                int(frame.kept),
                frame.drop_reason,
                frame.phash,
                frame.blur_score,
                ad_id,
                frame.frame_index,
            ),
        )


def _replace_ocr_items(conn: sqlite3.Connection, ad_id: str, ocr_items: list[OCRItem]) -> None:
    frame_rows = conn.execute(
        "SELECT id, frame_index FROM frames WHERE ad_id = ?", (ad_id,)
    ).fetchall()
    frame_ids = {int(row["frame_index"]): int(row["id"]) for row in frame_rows}
    conn.execute(
        "DELETE FROM ocr_items WHERE frame_id IN (SELECT id FROM frames WHERE ad_id = ?)",
        (ad_id,),
    )
    for item in ocr_items:
        frame_id = frame_ids.get(item.frame_index)
        if frame_id is None:
            continue
        conn.execute(
            """
            INSERT INTO ocr_items (frame_id, engine, text, bbox_json, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                frame_id,
                item.engine,
                item.text,
                json.dumps(item.bbox) if item.bbox is not None else None,
                item.confidence,
            ),
        )


def _replace_rule_triggers(
    conn: sqlite3.Connection,
    ad_id: str,
    triggers: list[RuleTrigger],
) -> None:
    conn.execute("DELETE FROM rule_triggers WHERE ad_id = ?", (ad_id,))
    for trigger in triggers:
        conn.execute(
            """
            INSERT INTO rule_triggers (
              ad_id, rule_id, category, risk_label, severity,
              evidence_text, time_ms, frame_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ad_id,
                trigger.rule_id,
                trigger.category,
                trigger.risk_label,
                trigger.severity,
                trigger.evidence_text,
                trigger.time_ms,
                trigger.frame_index,
            ),
        )


def _ocr_by_frame(items: list[OCRItem]) -> dict[int, list[OCRItem]]:
    out: dict[int, list[OCRItem]] = {}
    for item in items:
        out.setdefault(item.frame_index, []).append(item)
    return out


def _mean_pool(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dim = len(vectors[0])
    return [sum(vector[i] for vector in vectors) / len(vectors) for i in range(dim)]


def _ocr_quality(vlm_result) -> OCRQuality:
    return OCRQuality(
        overall=vlm_result.ocr_quality.overall,
        possible_errors=[
            item.reason or item.raw_ocr for item in vlm_result.ocr_quality.possible_errors
        ],
        missed_text=[item.text for item in vlm_result.ocr_quality.missed_text],
    )


def _run_ocr_cleanup(
    config: AppConfig,
    ocr_items: list[OCRItem],
    transcript: WhisperTranscript,
) -> list[OCRItem]:
    api_key = os.environ.get(config.vlm.endpoint.api_key_env) if config.vlm.endpoint.api_key_env else None
    cleanup = OCRCleanupPass(
        endpoint=config.vlm.endpoint.endpoint,
        model=config.vlm.endpoint.model,
        api_key=api_key,
        timeout_s=60.0,
        max_tokens=2048,
        enable_thinking=config.vlm.endpoint.enable_thinking,
    )
    return cleanup.run(ocr_items, transcript)


def _run_self_correction(
    config: AppConfig,
    result: VLMVerificationResult,
    evidence_texts: list[str],
) -> VLMVerificationResult:
    api_key = os.environ.get(config.vlm.endpoint.api_key_env) if config.vlm.endpoint.api_key_env else None
    correction = SelfCorrectionPass(
        endpoint=config.vlm.endpoint.endpoint,
        model=config.vlm.endpoint.model,
        api_key=api_key,
        timeout_s=30.0,
        max_tokens=1024,
        enable_thinking=config.vlm.endpoint.enable_thinking,
    )
    return correction.run(result, evidence_texts)


def _collect_evidence_texts(
    ocr_items: list[OCRItem],
    transcript: WhisperTranscript,
) -> list[str]:
    texts: list[str] = []
    for item in ocr_items:
        if item.text:
            texts.append(item.text)
    for seg in transcript.segments:
        if seg.text:
            texts.append(seg.text)
    return texts
