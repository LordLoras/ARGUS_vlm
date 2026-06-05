from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ad_classifier.entity_graph.manager import EntityGraphManager
from ad_classifier.entity_graph.targets import from_ad_url_mapping

entity_graph_app = typer.Typer(
    help="Manage the experimental product entity graph.",
    no_args_is_help=True,
)


@entity_graph_app.command("reset")
def reset_graph(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Confirm clearing only the experimental graph DB."),
    ] = False,
) -> None:
    """Clear the experimental graph DB without mutating the submitted ad DB."""
    if not yes:
        typer.echo("Refusing to reset without --yes. Only entity_graph.db is cleared.", err=True)
        raise typer.Exit(1)
    manager = _manager_from_config(config)
    typer.echo(_format_json(manager.reset_graph()))


@entity_graph_app.command("resolve")
def resolve_entities(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum submitted ad rows to read.")] = 1000,
    preview: Annotated[bool, typer.Option("--preview", help="Preview without writing graph rows.")] = False,
    fully_automatic: Annotated[
        bool,
        typer.Option(
            "--fully-automatic",
            help="Auto-confirm internally grounded entities as unreviewed.",
        ),
    ] = False,
) -> None:
    """Resolve product/brand/company/category graph nodes from submitted ad evidence."""
    manager = _manager_from_config(config)
    if preview:
        result = manager.preview_resolver(limit=limit, fully_automatic=fully_automatic)
    else:
        result = manager.run_resolver(limit=limit, fully_automatic=fully_automatic)
    typer.echo(result.model_dump_json(indent=2))


@entity_graph_app.command("crawl")
def crawl_web_targets(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum submitted web targets to visit.")] = 100,
    ad_id: Annotated[
        list[str] | None,
        typer.Option("--ad-id", help="Restrict crawl to one submitted ad id. Repeatable."),
    ] = None,
    target: Annotated[
        list[str] | None,
        typer.Option(
            "--target",
            help="Explicit crawl target in ad_id=url form. Repeatable.",
        ),
    ] = None,
) -> None:
    """Visit submitted ad website targets and write discovery-only graph evidence."""
    manager = _manager_from_config(config)
    result = manager.run_crawler(
        limit=limit,
        ad_ids=ad_id or None,
        target_urls=_parse_target_options(target or []),
    )
    typer.echo(result.model_dump_json(indent=2))


@entity_graph_app.command("rebuild")
def rebuild_graph(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum submitted ads/targets to read.")] = 1000,
    crawl: Annotated[
        bool,
        typer.Option("--crawl/--no-crawl", help="Run discovery-only website crawling after resolve."),
    ] = True,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Confirm clearing only the experimental graph DB first."),
    ] = False,
) -> None:
    """Reset, resolve, and optionally crawl in one local experimental graph run."""
    if not yes:
        typer.echo("Refusing to rebuild without --yes. Only entity_graph.db is cleared.", err=True)
        raise typer.Exit(1)
    manager = _manager_from_config(config)
    reset_result = manager.reset_graph()
    resolver_result = manager.run_resolver(limit=limit)
    crawler_result = manager.run_crawler(limit=limit) if crawl else None
    typer.echo(
        _format_json(
            {
                "reset": reset_result,
                "resolver": resolver_result.model_dump(mode="json"),
                "crawler": crawler_result.model_dump(mode="json") if crawler_result else None,
            }
        )
    )


@entity_graph_app.command("status")
def graph_status(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Product rows to inspect.")] = 200,
) -> None:
    """Print a compact status summary for the experimental graph."""
    manager = _manager_from_config(config)
    products = manager.list_products(limit=limit)
    typer.echo(
        _format_json(
            {
                "submitted_db_query_only": manager.submitted_db_is_readonly(),
                "products": len(products),
                "candidates": sum(1 for item in products if item.node.status == "candidate"),
                "confirmed_unreviewed": sum(
                    1 for item in products if item.node.status == "confirmed_unreviewed"
                ),
                "sample_products": [item.node.canonical_name for item in products[:20]],
            }
        )
    )


def _manager_from_config(config_path: Path | None) -> EntityGraphManager:
    from ad_classifier.config import load_config, resolve_config_path

    config, config_file = load_config(config_path)
    return EntityGraphManager(
        resolve_config_path(config.paths.entity_graph_path, config_file),
        resolve_config_path(config.paths.sqlite_path, config_file),
        crawler_config_path=resolve_config_path(config.paths.entity_crawler_config_path, config_file),
    )


def _format_json(payload: object) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


def _parse_target_options(values: list[str]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for value in values:
        if "=" not in value:
            raise typer.BadParameter("--target must be in ad_id=url form")
        ad_id, url = value.split("=", 1)
        targets = from_ad_url_mapping({ad_id: [url]})
        if not targets:
            raise typer.BadParameter(f"Invalid --target value: {value}")
        mapping.setdefault(ad_id.strip(), []).append(url.strip())
    return mapping
