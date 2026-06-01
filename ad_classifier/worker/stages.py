from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import structlog

from ad_classifier._env import resolve_api_key
from ad_classifier.config import AppConfig, resolve_config_path
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.db.repositories import AdRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.dedup.post_ocr import find_post_ocr_duplicate
from ad_classifier.dedup.similarity import enrich_related_ads
from ad_classifier.embeddings.image.base import ImageEmbedder
from ad_classifier.embeddings.image.siglip2 import SigLIP2ImageEmbedder
from ad_classifier.embeddings.text.base import TextEmbedder
from ad_classifier.embeddings.text.sentence_transformer import SentenceTransformerEmbedder
from ad_classifier.ingest.models import IngestArtifacts, IngestEvent, WhisperTranscript
from ad_classifier.ingest.service import IngestService
from ad_classifier.knowledge.manager import KnowledgeManager
from ad_classifier.marketing.extract import enrich_marketing_entities
from ad_classifier.models.classification import ClassificationRecord, OCRQuality
from ad_classifier.pipeline.aggregation.policy import aggregate
from ad_classifier.pipeline.evidence import build_evidence_bundle
from ad_classifier.pipeline.ocr.broadcast_overlay import split_broadcast_overlay
from ad_classifier.pipeline.ocr.engine import OCREngine, PaddleOCREngine
from ad_classifier.pipeline.ocr.fine_print import split_fine_print
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
from ad_classifier.vlm.complexity import VLMComplexity, assess_vlm_complexity, token_budget_for
from ad_classifier.vlm.correction import SelfCorrectionPass
from ad_classifier.vlm.models import VLMVerificationResult
from ad_classifier.vlm.prompt import get_prompt_version
from ad_classifier.vlm.validation import validate_vlm_output
from ad_classifier.vlm.verifier import HTTPVLMVerifier, VLMVerifier
from ad_classifier.vlm.visual_verify import VisualVerificationPass
from ad_classifier.worker.document_ocr import (
    bundle_document_outputs,
    document_outputs_to_ocr_items,
    run_glm_ocr,
    search_ocr_items,
)

ProgressCallback = Callable[[str, float, str], None]
_logger = structlog.get_logger(__name__)


class PipelineComponents:
    def __init__(
        self,
        *,
        ocr_engine: OCREngine | None = None,
        document_parser: DocumentParser | None = None,
        glm_ocr_parser: DocumentParser | None = None,
        vlm_verifier: VLMVerifier | None = None,
        text_embedder: TextEmbedder | None = None,
        image_embedder: ImageEmbedder | None = None,
    ) -> None:
        self.ocr_engine = ocr_engine
        self.document_parser = document_parser
        self.glm_ocr_parser = glm_ocr_parser
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

    if config.ocr.enabled:
        emit("ocr", 0.34, "extracting OCR")
        ocr_items = _run_ocr(
            components.ocr_engine or PaddleOCREngine(config.ocr.device, config.ocr.lang),
            preprocess_result.kept_frames,
        )
    else:
        emit("ocr", 0.34, "OCR disabled")
        ocr_items = []
    _replace_ocr_items(conn, ad_id, ocr_items)
    conn.commit()

    emit("paddlevl", 0.45, "checking hard frames")
    paddlevl_by_frame = _run_paddlevl(
        config=config,
        components=components,
        kept_frames=preprocess_result.kept_frames,
        ocr_by_frame=_ocr_by_frame(ocr_items),
    )

    emit("glm_ocr", 0.47, "checking GLM-OCR frames")
    glm_ocr_by_frame = run_glm_ocr(
        config=config,
        kept_frames=preprocess_result.kept_frames,
        ocr_by_frame=_ocr_by_frame(ocr_items),
        parser=components.glm_ocr_parser,
    )
    glm_ocr_items = document_outputs_to_ocr_items(glm_ocr_by_frame)
    if glm_ocr_items:
        _replace_ocr_items(conn, ad_id, ocr_items + glm_ocr_items)
        conn.commit()

    post_ocr_match = find_post_ocr_duplicate(conn, ad_id, config.dedup.post_ocr)
    if post_ocr_match is not None:
        if post_ocr_match.verdict == "exact_duplicate" and config.dedup.post_ocr.skip_on_exact:
            ads = AdRepository(conn)
            ads.update_duplicate(
                ad_id,
                duplicate_of=post_ocr_match.ad_id,
                duplicate_verdict=post_ocr_match.verdict,
                duplicate_score=post_ocr_match.overall_score,
            )
            ads.update_status(ad_id, "duplicate")
            conn.commit()
            emit(
                "dedup:post_ocr",
                1.0,
                f"post-OCR exact duplicate of {post_ocr_match.ad_id}",
            )
            return
        emit(
            "dedup:post_ocr",
            0.49,
            f"{post_ocr_match.verdict} candidate {post_ocr_match.ad_id}; continuing",
        )

    raw_ocr_items = list(ocr_items)
    corrected_ocr_items: list[OCRItem] = []
    rule_ocr_items = [*raw_ocr_items, *glm_ocr_items]
    reasoning_ocr_items = _main_ocr_items(
        rule_ocr_items,
        preprocess_result.kept_frames,
    )
    vlm_complexity = assess_vlm_complexity(
        ocr_items=reasoning_ocr_items,
        transcript=ingest.transcript,
        kept_frames=preprocess_result.kept_frames,
        config=config.vlm.complexity,
    )
    _logger.info(
        "vlm_complexity_assessed",
        ad_id=ad_id,
        stage="vlm",
        level=vlm_complexity.level,
        score=vlm_complexity.score,
        reasons=list(vlm_complexity.reasons),
        metrics=vlm_complexity.metrics,
    )

    if config.vlm.enable_ocr_cleanup_pass and raw_ocr_items:
        raw_ocr_path = config.paths.out / ad_id / "raw_ocr_items.json"
        raw_ocr_path.parent.mkdir(parents=True, exist_ok=True)
        raw_ocr_path.write_text(
            json.dumps(
                [item.model_dump() for item in raw_ocr_items],
                default=str,
            ),
            encoding="utf-8",
        )

    if config.vlm.enable_ocr_cleanup_pass:
        emit("vlm:cleanup", 0.50, "cleaning OCR text")
        cleaned = _run_ocr_cleanup(config, raw_ocr_items, ingest.transcript, vlm_complexity)
        corrected_ocr_items = _corrected_ocr_items(cleaned)
        if corrected_ocr_items:
            _replace_ocr_items(conn, ad_id, [*raw_ocr_items, *glm_ocr_items, *corrected_ocr_items])
            conn.commit()

    emit("rules", 0.55, "running rules")
    rules = RulesEngine(load_rules(config.rules.rules_path)).run(
        reasoning_ocr_items,
        ingest.transcript,
    )
    _replace_rule_triggers(conn, ad_id, rules)
    conn.commit()

    emit("vlm", 0.64, "verifying classification")
    vlm_max_tokens = token_budget_for(
        vlm_complexity,
        normal_tokens=config.vlm.endpoint.max_tokens,
        complex_tokens=config.vlm.complexity.verifier_max_tokens,
    )
    bundle = build_evidence_bundle(
        ad_id=ad_id,
        kept_frames=preprocess_result.kept_frames,
        transcript=ingest.transcript,
        rules_triggered=rules,
        ocr_by_frame=_ocr_by_frame([*rule_ocr_items, *corrected_ocr_items]),
        paddlevl_by_frame=bundle_document_outputs(
            paddlevl_by_frame,
            glm_ocr_by_frame,
            include_glm=config.glm_ocr.include_in_vlm_bundle,
        ),
        alignment_window_ms=config.rules.alignment_window_ms,
        max_frames=config.vlm.max_frames_in_bundle,
        metadata=ingest.metadata.model_dump() if ingest.metadata else {},
    )
    knowledge_manager = _knowledge_manager_for_pipeline(config, config_file)
    prompt_profile = config.vlm.resolved_prompt_profile()
    prompt_override = config.vlm.prompt_override_for(prompt_profile)
    vlm = components.vlm_verifier or HTTPVLMVerifier(
        endpoint=config.vlm.endpoint.endpoint,
        model=config.vlm.endpoint.model,
        api_key_env=config.vlm.endpoint.api_key_env,
        timeout_s=config.vlm.endpoint.timeout_s,
        max_retries=config.vlm.endpoint.max_retries,
        retry_delay_s=config.vlm.endpoint.retry_delay_s,
        temperature=config.vlm.endpoint.temperature,
        max_tokens=vlm_max_tokens,
        prompt_profile=prompt_profile,
        prompt_override=prompt_override,
        enable_thinking=config.vlm.endpoint.enable_thinking,
        response_format=config.vlm.endpoint.response_format,
        image_max_dim=config.vlm.image_max_dim,
        stream=config.vlm.endpoint.stream,
        knowledge_manager=knowledge_manager,
    )
    vlm_result = vlm.verify(bundle)

    if config.vlm.enable_post_validation:
        evidence_texts = _collect_evidence_texts(reasoning_ocr_items, ingest.transcript)
        vlm_result = validate_vlm_output(
            vlm_result, evidence_texts, primary_category=vlm_result.primary_category
        )

    if config.vlm.enable_self_correction:
        emit("vlm:correct", 0.72, "self-correction check")
        evidence_texts = _collect_evidence_texts(reasoning_ocr_items, ingest.transcript)
        vlm_result = _run_self_correction(config, vlm_result, evidence_texts, vlm_complexity)

    if getattr(config.vlm, "enable_visual_verify", False):
        emit("vlm:visual_verify", 0.75, "visual verification")
        vlm_result = _run_visual_verify(config, vlm_result, preprocess_result.kept_frames)

    emit("embed", 0.78, "embedding ad")
    search_ocr_for_index = search_ocr_items(
        [*raw_ocr_items, *corrected_ocr_items],
        glm_ocr_items,
        config,
    )
    search_main_ocr_for_index = _main_ocr_items(
        search_ocr_for_index,
        preprocess_result.kept_frames,
    )
    text_embedder = components.text_embedder or SentenceTransformerEmbedder(
        config.text_embedder.model,
        config.text_embedder.device,
    )
    image_embedder = components.image_embedder
    if image_embedder is None and config.image_embedder.enabled:
        image_embedder = SigLIP2ImageEmbedder(
            config.image_embedder.model,
            config.image_embedder.device,
        )
    text_vector, visual_vector = _write_embeddings(
        conn,
        config,
        ad_id,
        ingest,
        search_main_ocr_for_index,
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
    selected_debug = [
        {
            "frame_index": f.frame_index,
            "time_ms": f.time_ms,
            "path": str(f.path) if f.path else None,
            "kept": f.kept,
        }
        for f in preprocess_result.frames
        if f.kept
    ]
    dropped_debug = [
        {
            "frame_index": f.frame_index,
            "time_ms": f.time_ms,
            "drop_reason": f.drop_reason,
        }
        for f in preprocess_result.frames
        if not f.kept and f.drop_reason
    ]
    final = aggregate(
        ad_id,
        vlm_result,
        rules,
        related_ads=related,
        vlm_model=config.vlm.endpoint.model,
        vlm_prompt_version=get_prompt_version(prompt_profile, prompt_text=prompt_override),
        pipeline_version="0.1.0",
        selected_frames=selected_debug,
        dropped_frames=dropped_debug,
        knowledge_manager=knowledge_manager,
    )
    marketing_ocr_items = _main_ocr_items(
        [*rule_ocr_items, *corrected_ocr_items],
        preprocess_result.kept_frames,
    )
    final.marketing_entities = enrich_marketing_entities(
        final.marketing_entities,
        ocr_items=marketing_ocr_items,
        transcript=ingest.transcript,
    )
    ClassificationRepository(conn).upsert(
        ClassificationRecord(
            ad_id=ad_id,
            primary_category=final.primary_category,
            risk_labels=final.risk_labels,
            confidence=final.confidence,
            sensitive_category=final.sensitive_category,
            ocr_quality=final.ocr_quality or _ocr_quality(vlm_result),
            vlm_raw=vlm_result.model_dump(),
            evidence=final.evidence,
            vlm_model=final.vlm_model,
            vlm_prompt_version=final.vlm_prompt_version,
            embedder_text_model=text_embedder.model_name,
            embedder_visual_model=image_embedder.model_name,
            pipeline_version=final.pipeline_version,
            iab_category=final.iab_category,
            iab_content_categories=final.iab_content_categories,
        )
    )
    MarketingEntityRepository(conn).upsert(ad_id, final.marketing_entities)
    iab = final.iab_category
    iab_content_json = json.dumps([item.model_dump() for item in final.iab_content_categories])
    AdRepository(conn).update_projection(
        ad_id,
        brand_name=final.marketing_entities.brand.name,
        brand_confidence=final.marketing_entities.brand.confidence,
        advertiser_name=final.marketing_entities.advertiser.advertiser_name,
        promotion_name=final.marketing_entities.promotion_name,
        website_domain=final.marketing_entities.primary_website_domain,
        phone_number=final.marketing_entities.primary_phone_number,
        landing_page_domain=final.marketing_entities.landing_page.domain,
        products_text=final.marketing_entities.products_text,
        primary_category=final.primary_category,
        subcategory=final.marketing_entities.subcategory,
        iab_unique_id=iab.iab_unique_id if iab else None,
        iab_parent_id=iab.iab_parent_id if iab else None,
        iab_tier_1=iab.tier_1 if iab else None,
        iab_tier_2=iab.tier_2 if iab else None,
        iab_tier_3=iab.tier_3 if iab else None,
        iab_selected_depth=iab.selected_depth if iab else None,
        iab_selected_category=iab.selected_category if iab else None,
        iab_full_path=iab.full_path if iab else None,
        iab_confidence=iab.confidence if iab else None,
        iab_content_ids=",".join(item.iab_unique_id for item in final.iab_content_categories)
        or None,
        iab_content_paths=" | ".join(item.full_path for item in final.iab_content_categories)
        or None,
        iab_content_categories_json=iab_content_json if final.iab_content_categories else None,
    )
    AdRepository(conn).update_status(ad_id, "completed")
    fts_update(
        conn,
        ad_id,
        brand=final.marketing_entities.brand.name or "",
        promotion_name=final.marketing_entities.promotion_name or "",
        products=final.marketing_entities.products_text or "",
        primary_category=final.primary_category,
        transcript_text=ingest.transcript.text,
        ocr_text=" ".join(item.text for item in search_main_ocr_for_index),
        marketing_entities_text=json.dumps(
            {
                "marketing_entities": final.marketing_entities.model_dump(),
                "iab_category": final.iab_category.model_dump() if final.iab_category else None,
                "iab_content_categories": [
                    item.model_dump() for item in final.iab_content_categories
                ],
            }
        ),
    )
    conn.commit()
    emit("completed", 1.0, "job completed")


def _knowledge_manager_for_pipeline(
    config: AppConfig,
    config_file: Path,
) -> KnowledgeManager | None:
    try:
        db_path = resolve_config_path(config.paths.sqlite_path, config_file)
        return KnowledgeManager(db_path.parent / "knowledge.db")
    except Exception as exc:
        _logger.warning(
            "knowledge_manager_unavailable",
            stage="vlm",
            error=str(exc),
        )
        return None


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
    image_embedder: ImageEmbedder | None,
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
    visual_vector: list[float] | None = None
    if image_embedder is not None:
        visual_vectors = image_embedder.embed_batch([frame.path for frame in kept_frames])
        store.delete_frame_visuals(ad_id)
        for frame, vector in zip(kept_frames, visual_vectors, strict=False):
            store.upsert_frame_visual(ad_id, frame.frame_index, frame.time_ms, vector)
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


def _main_ocr_items(
    items: list[OCRItem],
    kept_frames: list[FrameAnalysis],
) -> list[OCRItem]:
    frame_paths = {frame.frame_index: frame.path for frame in kept_frames}
    main: list[OCRItem] = []
    for frame_index, frame_items in _ocr_by_frame(items).items():
        non_overlay_items, _broadcast_overlay = split_broadcast_overlay(
            frame_items,
            frame_path=frame_paths.get(frame_index),
        )
        frame_main, _fine_print = split_fine_print(
            non_overlay_items,
            frame_path=frame_paths.get(frame_index),
        )
        main.extend(frame_main)
    return main


def _corrected_ocr_items(items: list[OCRItem]) -> list[OCRItem]:
    return [item for item in items if item.engine == "ocr_cleanup"]


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
    complexity: VLMComplexity,
) -> list[OCRItem]:
    api_key = resolve_api_key(config.vlm.endpoint.api_key_env)
    max_tokens = token_budget_for(
        complexity,
        normal_tokens=2048,
        complex_tokens=config.vlm.complexity.cleanup_max_tokens,
    )
    cleanup = OCRCleanupPass(
        endpoint=config.vlm.endpoint.endpoint,
        model=config.vlm.endpoint.model,
        api_key=api_key,
        timeout_s=60.0,
        max_tokens=max_tokens,
        enable_thinking=config.vlm.endpoint.enable_thinking,
        stream=config.vlm.endpoint.stream,
    )
    return cleanup.run(ocr_items, transcript)


def _run_self_correction(
    config: AppConfig,
    result: VLMVerificationResult,
    evidence_texts: list[str],
    complexity: VLMComplexity,
) -> VLMVerificationResult:
    api_key = resolve_api_key(config.vlm.endpoint.api_key_env)
    max_tokens = token_budget_for(
        complexity,
        normal_tokens=4096,
        complex_tokens=config.vlm.complexity.self_correction_max_tokens,
    )
    correction = SelfCorrectionPass(
        endpoint=config.vlm.endpoint.endpoint,
        model=config.vlm.endpoint.model,
        api_key=api_key,
        timeout_s=300.0,
        max_tokens=max_tokens,
        enable_thinking=config.vlm.endpoint.enable_thinking,
        stream=config.vlm.endpoint.stream,
    )
    return correction.run(result, evidence_texts)


def _run_visual_verify(
    config: AppConfig,
    result: VLMVerificationResult,
    kept_frames: list,
) -> VLMVerificationResult:
    api_key = resolve_api_key(config.vlm.endpoint.api_key_env)
    verify = VisualVerificationPass(
        endpoint=config.vlm.endpoint.endpoint,
        model=config.vlm.endpoint.model,
        api_key=api_key,
        timeout_s=60.0,
        max_tokens=512,
        enable_thinking=config.vlm.endpoint.enable_thinking,
        stream=config.vlm.endpoint.stream,
    )
    frame_paths = [Path(f.path) for f in kept_frames if f.path]
    return verify.run(result, frame_paths)


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
