from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def ingest(
    video: Annotated[
        Path,
        typer.Option("--video", "-v", help="Path to the prepared ad video file."),
    ],
    ad_id: Annotated[
        str | None,
        typer.Option("--ad-id", help="Optional ad id. Defaults to ad_<first 8 chars of SHA256>."),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    whisper_model: Annotated[
        str | None,
        typer.Option("--whisper-model", help="Override whisper.model for this run."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Rebuild frames, audio, transcript, and manifest."),
    ] = False,
    no_db: Annotated[
        bool,
        typer.Option("--no-db", help="Write disk artifacts only; do not persist SQLite rows."),
    ] = False,
) -> None:
    """Extract frames, audio, transcript, and manifest for one prepared ad video."""
    from ad_classifier.config import load_config
    from ad_classifier.ingest.service import IngestService

    app_config, config_file = load_config(config)
    if whisper_model is not None:
        app_config = app_config.model_copy(
            update={"whisper": app_config.whisper.model_copy(update={"model": whisper_model})}
        )

    service = IngestService(config=app_config, config_file=config_file)
    try:
        result = service.run(video_path=video, ad_id=ad_id, force=force, persist=not no_db)
    except Exception as exc:
        typer.echo(f"ingest failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"ad_id={result.ad_id}")
    typer.echo(f"source={result.source_path}")
    typer.echo(f"frames={result.frames_dir} count={len(result.frames)}")
    typer.echo(f"audio={result.audio_path or 'none'}")
    typer.echo(f"whisper={result.whisper_path}")
    typer.echo(f"manifest={result.manifest_path}")
    typer.echo(f"persisted={not no_db}")
