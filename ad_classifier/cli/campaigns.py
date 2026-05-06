from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

campaigns_app = typer.Typer(help="Discover and manage ad campaigns.", no_args_is_help=True)


@campaigns_app.command("discover")
def discover_cmd(
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
    clusterer: Annotated[
        str | None,
        typer.Option("--clusterer", help="Override clusterer: hdbscan or agglomerative."),
    ] = None,
) -> None:
    """Run on-demand auto-discovery and persist proposed campaigns."""
    from ad_classifier.campaigns.discover import discover_campaigns
    from ad_classifier.config import load_config, resolve_config_path
    from ad_classifier.db.connection import initialize_database, load_sqlite_vec, open_database
    from ad_classifier.vectors.sqlite_vec import SqliteVecStore

    app_config, config_file = load_config(config)
    if clusterer is not None:
        app_config.campaigns.discover.clusterer = _validate_clusterer(clusterer)

    target = (
        db_path.expanduser().resolve()
        if db_path
        else resolve_config_path(app_config.paths.sqlite_path, config_file)
    )
    initialize_database(target)
    conn = open_database(target)
    try:
        load_sqlite_vec(conn)
        store = SqliteVecStore(
            conn,
            text_dim=app_config.vector_store.text_dim,
            visual_dim=app_config.vector_store.visual_dim,
        )
        store.ensure_tables()
        result = discover_campaigns(conn, store, config=app_config.campaigns.discover)
        conn.commit()
    finally:
        conn.close()

    typer.echo(f"discovered={len(result.discovered)}")
    typer.echo(f"skipped_missing_vectors={result.skipped_missing_vectors}")
    typer.echo(f"skipped_user_assigned_ads={result.skipped_user_assigned_ads}")
    for item in result.discovered:
        typer.echo(
            "campaign="
            f"{item.campaign.id} name={item.campaign.name!r} brand={item.campaign.brand!r} "
            f"ads={len(item.ad_ids)} mean_similarity={item.mean_similarity:.4f}"
        )


@campaigns_app.command("list")
def list_cmd(
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
    brand: Annotated[str | None, typer.Option("--brand", help="Filter by brand.")] = None,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Filter by created_by: auto or user."),
    ] = None,
    q: Annotated[str | None, typer.Option("--q", help="Search name/theme/description.")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    """List campaigns from SQLite."""
    from ad_classifier.config import load_config, resolve_config_path
    from ad_classifier.db.connection import initialize_database, open_database
    from ad_classifier.db.repositories import AdCampaignRepository, CampaignRepository

    if created_by is not None and created_by not in {"auto", "user"}:
        typer.echo("--created-by must be 'auto' or 'user'", err=True)
        raise typer.Exit(1)

    app_config, config_file = load_config(config)
    target = (
        db_path.expanduser().resolve()
        if db_path
        else resolve_config_path(app_config.paths.sqlite_path, config_file)
    )
    initialize_database(target, require_sqlite_vec=False)
    conn = open_database(target)
    try:
        campaigns = CampaignRepository(conn).list(
            brand=brand,
            created_by=created_by,
            q=q,
            limit=limit,
        )
        assignments = AdCampaignRepository(conn)
        for campaign in campaigns:
            count = len(assignments.list_for_campaign(campaign.id))
            typer.echo(
                f"{campaign.id}\t{campaign.name}\tbrand={campaign.brand or ''}\t"
                f"created_by={campaign.created_by}\tads={count}"
            )
    finally:
        conn.close()


def _validate_clusterer(value: str) -> str:
    if value not in {"hdbscan", "agglomerative"}:
        typer.echo("--clusterer must be 'hdbscan' or 'agglomerative'", err=True)
        raise typer.Exit(1)
    return value
