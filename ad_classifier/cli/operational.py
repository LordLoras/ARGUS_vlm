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
    from ad_classifier.api.factories import (
        text_embedder_factory,
        vector_store_factory,
        visual_text_embedder_factory,
    )
    from ad_classifier.config import load_config

    app_config, _ = load_config(config)
    app = create_app(
        config_path=config,
        agent_text_embedder_factory=lambda cfg: text_embedder_factory(cfg),
        agent_visual_text_embedder_factory=lambda cfg: visual_text_embedder_factory(cfg),
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


def recover_jobs(
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
) -> None:
    """Requeue interrupted running jobs after a local service restart."""
    from ad_classifier.config import resolve_sqlite_path
    from ad_classifier.db.connection import initialize_database, open_database
    from ad_classifier.db.repositories import JobRepository

    target = resolve_sqlite_path(config, db_path)
    initialize_database(target, require_sqlite_vec=False)
    conn = open_database(target)
    try:
        conn.execute(
            """
            UPDATE ads
            SET status = 'new'
            WHERE status = 'processing'
              AND id IN (SELECT ad_id FROM jobs WHERE state = 'running')
            """
        )
        jobs_requeued = JobRepository(conn).requeue_running()
        conn.commit()
    finally:
        conn.close()
    typer.echo(f"jobs_requeued={jobs_requeued}")


def reindex_visual_frames(
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
    ad_id: Annotated[
        str | None,
        typer.Option("--ad-id", help="Only reindex frames for one ad."),
    ] = None,
) -> None:
    """Backfill per-frame SigLIP visual vectors for existing kept frames."""
    from collections import defaultdict

    from ad_classifier.config import load_config, resolve_sqlite_path
    from ad_classifier.db.connection import load_sqlite_vec, open_database
    from ad_classifier.embeddings.image.siglip2 import SigLIP2ImageEmbedder
    from ad_classifier.vectors.sqlite_vec import SqliteVecStore

    app_config, _ = load_config(config)
    target = db_path.expanduser().resolve() if db_path else resolve_sqlite_path(config, db_path)
    conn = open_database(target)
    try:
        load_sqlite_vec(conn)
        store = SqliteVecStore(
            conn,
            text_dim=app_config.vector_store.text_dim,
            visual_dim=app_config.vector_store.visual_dim,
        )
        store.ensure_tables()
        query = "SELECT ad_id, frame_index, time_ms, path FROM frames WHERE kept = 1"
        params: tuple[str, ...] = ()
        if ad_id:
            query += " AND ad_id = ?"
            params = (ad_id,)
        query += " ORDER BY ad_id, frame_index"
        rows = conn.execute(query, params).fetchall()
        if not rows:
            typer.echo("frames_indexed=0")
            return

        embedder = SigLIP2ImageEmbedder(
            app_config.image_embedder.model,
            app_config.image_embedder.device,
        )
        by_ad = defaultdict(list)
        for row in rows:
            by_ad[row["ad_id"]].append(row)

        total = 0
        for found_ad_id, frame_rows in by_ad.items():
            store.delete_frame_visuals(found_ad_id)
            vectors: list[list[float]] = []
            batch_size = app_config.image_embedder.batch_size
            for start in range(0, len(frame_rows), batch_size):
                batch = frame_rows[start : start + batch_size]
                batch_vectors = embedder.embed_batch([Path(row["path"]) for row in batch])
                vectors.extend(batch_vectors)
                for row, vector in zip(batch, batch_vectors, strict=False):
                    store.upsert_frame_visual(
                        found_ad_id,
                        int(row["frame_index"]),
                        int(row["time_ms"]),
                        vector,
                    )
                    total += 1
            ad_vector = _mean_pool_vectors(vectors)
            if ad_vector is not None:
                store.upsert_visual(found_ad_id, ad_vector)
            conn.commit()
            typer.echo(f"ad_id={found_ad_id} frames_indexed={len(frame_rows)}")
        typer.echo(f"frames_indexed={total}")
    finally:
        conn.close()


def _mean_pool_vectors(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dim = len(vectors[0])
    return [sum(vector[i] for vector in vectors) / len(vectors) for i in range(dim)]
