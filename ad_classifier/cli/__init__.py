import typer

from ad_classifier.cli.bench_vectors import bench_vectors
from ad_classifier.cli.campaigns import campaigns_app
from ad_classifier.cli.dedup import dedup_check
from ad_classifier.cli.ingest import ingest
from ad_classifier.cli.ocr import ocr_cmd
from ad_classifier.cli.operational import api, init_db, worker

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
app.command("api")(api)
app.command("worker")(worker)
app.command("ingest")(ingest)
app.command("dedup-check")(dedup_check)
app.command("ocr")(ocr_cmd)
app.command("bench-vectors")(bench_vectors)
app.add_typer(campaigns_app, name="campaigns")
