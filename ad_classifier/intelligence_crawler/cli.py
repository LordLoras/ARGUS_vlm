"""``ad-classifier intel ...`` command group."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import typer

from ad_classifier.intelligence_crawler.config import IntelConfig, load_intel_config
from ad_classifier.intelligence_crawler.digest import build_digest
from ad_classifier.intelligence_crawler.meta_ad_library_probe import (
    TOYOTA_META_AD_LIBRARY_URL,
    run_meta_ad_library_probe,
)
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.runner import IntelRunner
from ad_classifier.intelligence_crawler.schema import initialize_intelligence_crawler_db
from ad_classifier.intelligence_crawler.sources.base import available_source_types
from ad_classifier.intelligence_crawler.timeutils import parse_iso, utcnow
from ad_classifier.intelligence_crawler.watchlist import build_watchlist

intel_app = typer.Typer(
    help="Brand-anchored awareness crawler: detect new US ad/campaign releases.",
    no_args_is_help=True,
)

_ConfigOpt = Annotated[
    Path | None,
    typer.Option("--config", "-c", help="Path to intelligence_crawler.yaml (defaults to ./)."),
]


def _load(config_path: Path | None) -> IntelConfig:
    if config_path is None:
        default = Path("./intelligence_crawler.yaml")
        config_path = default if default.exists() else None
    return load_intel_config(config_path)


def _parse_since(value: str | None):
    if not value:
        return None
    text = value.strip().lower()
    if text.endswith("d") and text[:-1].isdigit():
        return utcnow() - timedelta(days=int(text[:-1]))
    return parse_iso(value)


@intel_app.command("init-db")
def init_db(config: _ConfigOpt = None) -> None:
    """Create intelligence_crawler.db (schema + migrations)."""
    cfg = _load(config)
    applied = initialize_intelligence_crawler_db(cfg.db_path)
    typer.echo(json.dumps({"db_path": str(cfg.db_path), "migrations_applied": applied}, indent=2))


@intel_app.command("source-types")
def source_types() -> None:
    """List registered source adapter types (the extension points)."""
    typer.echo(json.dumps({"source_types": available_source_types()}, indent=2))


@intel_app.command("watchlist")
def watchlist(config: _ConfigOpt = None) -> None:
    """Show the US brand watchlist (graph brands + YAML seed)."""
    cfg = _load(config)
    brands = build_watchlist(cfg)
    typer.echo(json.dumps([b.model_dump() for b in brands], indent=2))


@intel_app.command("crawl")
def crawl(
    config: _ConfigOpt = None,
    due: Annotated[bool, typer.Option("--due", help="Crawl all enabled (due) sources.")] = False,
    source: Annotated[
        str | None, typer.Option("--source", help="Crawl one source id (even if disabled).")
    ] = None,
    brand: Annotated[str | None, typer.Option("--brand", help="Restrict to one brand.")] = None,
) -> None:
    """Poll sources and persist new resources/signals."""
    cfg = _load(config)
    summary = IntelRunner(cfg).run(due=due, source_id=source, brand=brand)
    typer.echo(summary.model_dump_json(indent=2))


@intel_app.command("signals")
def signals(
    config: _ConfigOpt = None,
    brand: Annotated[str | None, typer.Option("--brand", help="Filter by brand.")] = None,
    since: Annotated[str | None, typer.Option("--since", help="e.g. 7d, 30d, or ISO date.")] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="candidate|corroborated|...")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max rows.")] = 50,
) -> None:
    """List detected ad/campaign signals."""
    cfg = _load(config)
    repo = IntelRepository(cfg.db_path)
    with repo.connect(readonly=True) as conn:
        rows = repo.list_signals(
            conn, brand=brand, since=_parse_since(since), status=status, limit=limit
        )
    typer.echo(json.dumps([r.model_dump(mode="json") for r in rows], indent=2))


@intel_app.command("digest")
def digest(
    config: _ConfigOpt = None,
    since: Annotated[str | None, typer.Option("--since", help="e.g. 7d, 30d, or ISO date.")] = "7d",
) -> None:
    """Grouped 'what's new' digest (the notification surface)."""
    cfg = _load(config)
    repo = IntelRepository(cfg.db_path)
    entries = build_digest(repo, since=_parse_since(since))
    typer.echo(json.dumps([e.model_dump() for e in entries], indent=2))


@intel_app.command("meta-probe")
def meta_probe(
    url: Annotated[
        str,
        typer.Option(
            "--url",
            help="Public Meta Ad Library URL to observe.",
        ),
    ] = TOYOTA_META_AD_LIBRARY_URL,
    out_dir: Annotated[
        Path,
        typer.Option("--out-dir", help="Directory for screenshots and JSON output."),
    ] = Path("./output/meta_ad_library_probe/toyota"),
    scrolls: Annotated[int, typer.Option("--scrolls", help="Number of page scrolls.")] = 6,
    max_cards: Annotated[
        int, typer.Option("--max-cards", help="Maximum candidate cards to capture.")
    ] = 30,
    wait_ms: Annotated[int, typer.Option("--wait-ms", help="Wait after load/scroll in ms.")] = 1800,
    stop_after_no_new: Annotated[
        int,
        typer.Option(
            "--stop-after-no-new",
            help="Stop after this many scrolls without new Library IDs; 0 disables.",
        ),
    ] = 3,
    headed: Annotated[bool, typer.Option("--headed", help="Show Chromium while probing.")] = False,
) -> None:
    """Experimental Playwright probe for the public Meta Ad Library UI."""
    result = run_meta_ad_library_probe(
        url=url,
        out_dir=out_dir,
        scrolls=scrolls,
        max_cards=max_cards,
        headed=headed,
        wait_ms=wait_ms,
        stop_after_no_new=stop_after_no_new,
    )
    typer.echo(
        json.dumps(
            {
                "source_url": result.source_url,
                "final_url": result.final_url,
                "cards_count": result.cards_count,
                "scrolls_completed": result.scrolls_completed,
                "unique_library_ids_seen": result.unique_library_ids_seen,
                "stopped_after_no_new": result.stopped_after_no_new,
                "json_path": str(out_dir / "meta_ad_library_probe.json"),
                "full_page_screenshot": result.full_page_screenshot,
            },
            indent=2,
        )
    )
