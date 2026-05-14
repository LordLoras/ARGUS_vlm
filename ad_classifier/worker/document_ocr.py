from __future__ import annotations

from ad_classifier.config import AppConfig
from ad_classifier.pipeline.ocr.models import FrameRef, OCRItem
from ad_classifier.pipeline.paddlevl.gating import should_run_paddlevl
from ad_classifier.pipeline.paddlevl.models import PaddleVLGatingConfig, PaddleVLOutput
from ad_classifier.pipeline.paddlevl.parser import DocumentParser, GLMOCRParser
from ad_classifier.pipeline.preprocess.models import FrameAnalysis


def run_glm_ocr(
    *,
    config: AppConfig,
    kept_frames: list[FrameAnalysis],
    ocr_by_frame: dict[int, list[OCRItem]],
    parser: DocumentParser | None = None,
) -> dict[int, PaddleVLOutput]:
    if not config.glm_ocr.enabled:
        return {}

    parser = parser or GLMOCRParser(
        endpoint=config.glm_ocr.endpoint.endpoint,
        model=config.glm_ocr.endpoint.model,
        api_key_env=config.glm_ocr.endpoint.api_key_env,
        prompt=config.glm_ocr.prompt,
        timeout_s=config.glm_ocr.endpoint.timeout_s,
        max_retries=config.glm_ocr.endpoint.max_retries,
        retry_delay_s=config.glm_ocr.endpoint.retry_delay_s,
        temperature=config.glm_ocr.endpoint.temperature,
        max_tokens=config.glm_ocr.endpoint.max_tokens,
        image_max_dim=config.glm_ocr.image_max_dim,
        stream=config.glm_ocr.endpoint.stream,
    )
    outputs: dict[int, PaddleVLOutput] = {}
    for frame in select_glm_ocr_frames(
        config=config,
        kept_frames=kept_frames,
        ocr_by_frame=ocr_by_frame,
    ):
        outputs[frame.frame_index] = parser.parse(
            FrameRef(frame_index=frame.frame_index, time_ms=frame.time_ms, path=frame.path)
        )
    return outputs


def select_glm_ocr_frames(
    *,
    config: AppConfig,
    kept_frames: list[FrameAnalysis],
    ocr_by_frame: dict[int, list[OCRItem]],
) -> list[FrameAnalysis]:
    gating = PaddleVLGatingConfig.model_validate(config.glm_ocr.gating.model_dump())
    candidates: list[tuple[int, int, int, FrameAnalysis]] = []
    for frame in kept_frames:
        items = ocr_by_frame.get(frame.frame_index, [])
        char_count = sum(len(item.text) for item in items)
        run, _reason = should_run_paddlevl(items, gating, frame)
        priority: int | None = None
        if run:
            priority = 0
        elif not config.ocr.enabled and config.glm_ocr.run_when_ocr_disabled:
            priority = 1
        elif config.glm_ocr.run_on_text_frames and char_count >= config.glm_ocr.min_ocr_chars:
            priority = 2

        if priority is not None:
            candidates.append((priority, -char_count, frame.frame_index, frame))

    candidates.sort(key=lambda item: item[:3])
    return [frame for *_keys, frame in candidates[: config.glm_ocr.max_frames_per_ad]]


def document_outputs_to_ocr_items(
    outputs_by_frame: dict[int, PaddleVLOutput],
) -> list[OCRItem]:
    items: list[OCRItem] = []
    for _frame_index, output in sorted(outputs_by_frame.items()):
        text = document_output_text(output)
        if not output.parse_ok or not text:
            continue
        items.append(
            OCRItem(
                frame_index=output.frame_index,
                time_ms=output.time_ms,
                text=text,
                confidence=None,
                bbox=None,
                engine=output.engine,
            )
        )
    return items


def document_output_text(output: PaddleVLOutput) -> str:
    parsed_text = ""
    if isinstance(output.parsed, dict) and isinstance(output.parsed.get("text"), str):
        parsed_text = output.parsed["text"]
    return (parsed_text or output.raw_text or "").strip()


def search_ocr_items(
    raw_ocr_items: list[OCRItem],
    glm_ocr_items: list[OCRItem],
    config: AppConfig,
) -> list[OCRItem]:
    if config.glm_ocr.enabled and config.glm_ocr.include_in_search:
        return [*raw_ocr_items, *glm_ocr_items]
    return raw_ocr_items


def bundle_document_outputs(
    paddlevl_by_frame: dict[int, PaddleVLOutput],
    glm_ocr_by_frame: dict[int, PaddleVLOutput],
    *,
    include_glm: bool,
) -> dict[int, PaddleVLOutput]:
    if not include_glm:
        return paddlevl_by_frame

    merged = dict(paddlevl_by_frame)
    for frame_index, glm_output in glm_ocr_by_frame.items():
        existing = merged.get(frame_index)
        if existing is None:
            merged[frame_index] = glm_output
        else:
            merged[frame_index] = _merge_document_outputs(existing, glm_output)
    return merged


def _merge_document_outputs(left: PaddleVLOutput, right: PaddleVLOutput) -> PaddleVLOutput:
    left_text = document_output_text(left)
    right_text = document_output_text(right)
    joined = "\n".join(
        part for part in (f"{left.engine}: {left_text}", f"{right.engine}: {right_text}") if part
    )
    return PaddleVLOutput(
        frame_index=left.frame_index,
        time_ms=left.time_ms,
        raw_text=joined,
        parsed={"text": joined} if joined else None,
        parse_ok=left.parse_ok or right.parse_ok,
        stderr=left.stderr or right.stderr,
        engine=f"{left.engine}+{right.engine}",
    )
