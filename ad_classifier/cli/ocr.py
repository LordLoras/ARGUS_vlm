from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def ocr_cmd(
    input: Annotated[
        Path,
        typer.Option("--input", "-i", help="Image file or directory of frames."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output JSON file path."),
    ],
    device: Annotated[
        str,
        typer.Option("--device", help="OCR device: cpu or gpu:0. Default: cpu."),
    ] = "cpu",
    lang: Annotated[
        str,
        typer.Option("--lang", help="OCR language code (e.g. en, ch)."),
    ] = "en",
) -> None:
    """Run PaddleOCR on a single image or a directory of frame images."""
    from ad_classifier.pipeline.ocr.engine import PaddleOCREngine
    from ad_classifier.pipeline.ocr.models import FrameRef

    try:
        engine = PaddleOCREngine(device=device, lang=lang)
    except ImportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    paths: list[Path] = []
    if input.is_dir():
        paths = sorted(
            p for p in input.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
        )
        if not paths:
            typer.echo(f"No image files found in {input}", err=True)
            raise typer.Exit(1)
    elif input.is_file():
        paths = [input]
    else:
        typer.echo(f"Input not found: {input}", err=True)
        raise typer.Exit(1)

    results: list[dict] = []
    for idx, path in enumerate(paths):
        frame = FrameRef(frame_index=idx, time_ms=idx * 500, path=path)
        try:
            items = engine.extract(frame)
        except Exception as exc:
            typer.echo(f"OCR failed for {path}: {exc}", err=True)
            continue
        results.extend(item.model_dump(mode="json") for item in items)
        typer.echo(f"[{idx + 1}/{len(paths)}] {path.name}: {len(items)} items", err=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    typer.echo(f"Wrote {len(results)} OCR items to {output}")
