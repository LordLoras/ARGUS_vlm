from typing import Annotated

import typer

from ad_classifier.cli.agent import agent_app
from ad_classifier.cli.bench_vectors import bench_vectors
from ad_classifier.cli.campaigns import campaigns_app
from ad_classifier.cli.dedup import dedup_check
from ad_classifier.cli.entity_graph import entity_graph_app
from ad_classifier.cli.ingest import ingest
from ad_classifier.intelligence_crawler.cli import intel_app
from ad_classifier.cli.ocr import ocr_cmd
from ad_classifier.cli.operational import api, init_db, recover_jobs, reindex_visual_frames, worker

app = typer.Typer(
    name="ad-classifier",
    help="Multimodal ad-classification pipeline.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print version and GPU status."""
    from ad_classifier import __version__
    from ad_classifier.diagnostics.env import check_torch

    typer.echo(f"ad-classifier {__version__}")
    check_torch(require_gpu=False)


@app.command("paddle-rocm-check")
def paddle_rocm_check(
    image: Annotated[
        str | None,
        typer.Option(
            "--image",
            "-i",
            help="Optional image path for a PaddleOCR GPU inference smoke test.",
        ),
    ] = None,
) -> None:
    """Check best-effort PaddlePaddle ROCm/GPU support."""
    from pathlib import Path

    from ad_classifier.diagnostics.paddle_rocm import (
        diagnostic_explanation,
        format_diagnostic_table,
        run_paddle_rocm_check,
    )

    rows = run_paddle_rocm_check(Path(image) if image else None)
    typer.echo(format_diagnostic_table(rows))
    typer.echo()
    typer.echo(diagnostic_explanation(rows))


app.command("init-db")(init_db)
app.command("api")(api)
app.command("worker")(worker)
app.command("recover-jobs")(recover_jobs)
app.command("reindex-visual-frames")(reindex_visual_frames)
app.command("ingest")(ingest)
app.command("dedup-check")(dedup_check)
app.command("ocr")(ocr_cmd)
app.command("bench-vectors")(bench_vectors)
app.add_typer(campaigns_app, name="campaigns")
app.add_typer(agent_app, name="agent")
app.add_typer(entity_graph_app, name="entity-graph")
app.add_typer(intel_app, name="intel")
