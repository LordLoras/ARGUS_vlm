from __future__ import annotations

import time
from pathlib import Path

import typer

from ad_classifier.config import load_config, resolve_sqlite_path


def bench_vectors(
    db: Path = typer.Option(None, "--db", help="Path to SQLite database"),
    n: int = typer.Option(100, "--n", help="Number of random vectors to insert + query"),
    config_path: Path = typer.Option(None, "--config", help="Path to config.yaml"),
) -> None:
    """Benchmark SqliteVecStore insert and KNN query speed."""
    import random

    from ad_classifier.db.connection import load_sqlite_vec, open_database
    from ad_classifier.vectors.sqlite_vec import SqliteVecStore

    cfg, _ = load_config(config_path)
    db_path = resolve_sqlite_path(config_path, db)

    conn = open_database(db_path)
    try:
        load_sqlite_vec(conn)
    except Exception as exc:
        typer.echo(f"sqlite-vec not available: {exc}", err=True)
        raise typer.Exit(1)

    store = SqliteVecStore(
        conn,
        text_dim=cfg.vector_store.text_dim,
        visual_dim=cfg.vector_store.visual_dim,
    )
    store.ensure_tables()

    text_dim = cfg.vector_store.text_dim
    typer.echo(f"Inserting {n} random text vectors (dim={text_dim})...")

    ids = [f"bench_{i}" for i in range(n)]
    vectors = [[random.gauss(0, 1) for _ in range(text_dim)] for _ in range(n)]

    t0 = time.perf_counter()
    for ad_id, vec in zip(ids, vectors, strict=False):
        store.upsert_text(ad_id, vec)
    conn.commit()
    insert_ms = (time.perf_counter() - t0) * 1000
    typer.echo(f"  Insert: {insert_ms:.1f}ms total ({insert_ms/n:.2f}ms/vec)")

    query_vec = [random.gauss(0, 1) for _ in range(text_dim)]
    t0 = time.perf_counter()
    results = store.search_text(query_vec, k=10)
    query_ms = (time.perf_counter() - t0) * 1000
    typer.echo(f"  KNN query (k=10): {query_ms:.2f}ms  top={results[0] if results else 'none'}")

    # Cleanup bench rows
    for ad_id in ids:
        conn.execute("DELETE FROM vec_ads_text WHERE ad_id = ?", (ad_id,))
    conn.commit()
    typer.echo("Bench rows cleaned up.")
