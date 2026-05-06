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
