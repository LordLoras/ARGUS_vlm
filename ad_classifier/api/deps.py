from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from fastapi import Request

from ad_classifier.config import AppConfig
from ad_classifier.db.connection import open_database
from ad_classifier.ingest.ffmpeg import FFmpegMediaExtractor

UploadProbe = Callable[[Path], object]


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def get_config_file(request: Request) -> Path:
    return request.app.state.config_file


def get_db_path(request: Request) -> Path:
    return request.app.state.db_path


def open_request_db(request: Request) -> sqlite3.Connection:
    return open_database(get_db_path(request))


def get_upload_probe(request: Request) -> UploadProbe:
    probe = getattr(request.app.state, "upload_probe", None)
    if probe is not None:
        return probe
    config = get_config(request)
    extractor = FFmpegMediaExtractor(
        ffmpeg_path=config.ingest.ffmpeg_path,
        ffprobe_path=config.ingest.ffprobe_path,
    )
    return extractor.probe
