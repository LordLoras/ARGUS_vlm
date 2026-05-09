from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def init_db(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Override the configured SQLite database path."),
    ] = None,
    skip_vector_check: Annotated[
        bool,
        typer.Option(
            "--skip-vector-check",
            help="Create schema without loading sqlite-vec. Useful only for limited local debugging.",
        ),
    ] = False,
) -> None:
    """Create or migrate the SQLite database and verify sqlite-vec."""
    from ad_classifier.config import resolve_sqlite_path
    from ad_classifier.db.connection import SqliteVecUnavailableError, initialize_database

    target = resolve_sqlite_path(config, db_path)
    try:
        result = initialize_database(target, require_sqlite_vec=not skip_vector_check)
    except SqliteVecUnavailableError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"database={result.db_path}")
    typer.echo(f"journal_mode={result.journal_mode}")
    typer.echo(f"sqlite_vec={result.sqlite_vec_version or 'skipped'}")
    if result.migrations_applied:
        typer.echo(f"migrations_applied={','.join(result.migrations_applied)}")
    else:
        typer.echo("migrations_applied=none")


def api(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    host: Annotated[str | None, typer.Option("--host", help="Override API host.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Override API port.")] = None,
) -> None:
    """Run the FastAPI server."""
    import uvicorn

    from ad_classifier.api.app import create_app
    from ad_classifier.api.factories import text_embedder_factory, vector_store_factory
    from ad_classifier.config import load_config

    app_config, _ = load_config(config)
    app = create_app(
        config_path=config,
        agent_text_embedder_factory=lambda cfg: text_embedder_factory(cfg),
        agent_vector_store_factory=lambda cfg, conn: vector_store_factory(cfg, conn),
    )
    uvicorn.run(
        app,
        host=host or app_config.api.host,
        port=port or app_config.api.port,
    )


def worker(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    once: Annotated[bool, typer.Option("--once", help="Process at most one queued job.")] = False,
) -> None:
    """Run the SQLite-backed worker."""
    from ad_classifier.worker.runner import build_worker

    runner = build_worker(config)
    if once:
        did_work = runner.run_once()
        typer.echo(f"did_work={str(did_work).lower()}")
        return
    runner.run_forever()
