from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def dedup_check(
    video: Annotated[
        Path | None,
        typer.Option("--video", "-v", help="Check a prepared ad video by source SHA256."),
    ] = None,
    ad_id: Annotated[
        str | None,
        typer.Option("--ad-id", help="Check an existing ad row by id."),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Defaults to ./config.yaml or ./config.example.yaml.",
        ),
    ] = None,
) -> None:
    """Run exact and available perceptual duplicate checks."""
    from ad_classifier.config import load_config, resolve_config_path
    from ad_classifier.db.connection import initialize_database, open_database
    from ad_classifier.db.repositories import AdRepository
    from ad_classifier.dedup.file_hash import source_sha256
    from ad_classifier.dedup.service import DedupService, check_frame_phashes
    from ad_classifier.ingest.ffmpeg import existing_frames
    from ad_classifier.ingest.service import ad_id_from_source_hash

    if (video is None and ad_id is None) or (video is not None and ad_id is not None):
        typer.echo("provide exactly one of --video or --ad-id", err=True)
        raise typer.Exit(1)

    app_config, config_file = load_config(config)
    db_path = resolve_config_path(app_config.paths.sqlite_path, config_file)
    initialize_database(db_path)
    conn = open_database(db_path)
    try:
        ads = AdRepository(conn)
        dedup = DedupService(conn=conn, config=app_config.dedup)

        if video is not None:
            source_path = video.expanduser().resolve()
            if not source_path.exists():
                typer.echo(f"video not found: {source_path}", err=True)
                raise typer.Exit(1)
            file_hash = source_sha256(source_path)
            derived_ad_id = ad_id_from_source_hash(file_hash)
            exact = dedup.check_exact(source_hash=file_hash)
            typer.echo(f"source_hash={file_hash}")
            typer.echo(f"derived_ad_id={derived_ad_id}")
            typer.echo(f"exact_duplicate_of={exact.ad_id if exact else 'none'}")

            frames_dir = resolve_config_path(app_config.paths.frames, config_file) / derived_ad_id
            frames = existing_frames(frames_dir, app_config.ingest.frame_interval_ms)
            if frames:
                frame_result = check_frame_phashes(
                    conn=conn,
                    config=app_config.dedup,
                    frame_paths=[frame.path for frame in frames],
                    exclude_ad_id=derived_ad_id,
                    source_hash=file_hash,
                )
                typer.echo(f"cached_frames={len(frames)}")
                typer.echo(f"phash_mean={frame_result.phash_mean or 'none'}")
                typer.echo(f"near_duplicate_of={frame_result.near_duplicate_of or 'none'}")
                distance = (
                    str(frame_result.phash_distance)
                    if frame_result.phash_distance is not None
                    else "none"
                )
                typer.echo(f"phash_distance={distance}")
            else:
                typer.echo("cached_frames=0")
            return

        assert ad_id is not None
        ad = ads.get(ad_id)
        if ad is None:
            typer.echo(f"ad not found: {ad_id}", err=True)
            raise typer.Exit(1)
        typer.echo(f"ad_id={ad.id}")
        typer.echo(f"source_hash={ad.source_hash or 'none'}")
        if ad.source_hash:
            exact = dedup.check_exact(source_hash=ad.source_hash, exclude_ad_id=ad.id)
            typer.echo(f"exact_duplicate_of={exact.ad_id if exact else 'none'}")
        if ad.phash_mean:
            near = dedup.check_near(phash_mean=ad.phash_mean, exclude_ad_id=ad.id)
            typer.echo(f"phash_mean={ad.phash_mean}")
            typer.echo(f"near_duplicate_of={near.ad_id if near else 'none'}")
            typer.echo(f"phash_distance={near.distance if near is not None else 'none'}")
        else:
            typer.echo("phash_mean=none")
    finally:
        conn.close()
