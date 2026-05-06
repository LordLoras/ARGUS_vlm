import typer

from ad_classifier.cli.operational import init_db

app = typer.Typer(
    name="ad-classifier",
    help="Local-first multimodal ad-classification pipeline.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print version and GPU status."""
    from ad_classifier import __version__
    from ad_classifier.diagnostics.env import check_torch

    typer.echo(f"ad-classifier {__version__}")
    check_torch(require_gpu=False)


app.command("init-db")(init_db)
