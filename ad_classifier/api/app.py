from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ad_classifier.api.routes.ads import router as ads_router
from ad_classifier.api.routes.campaigns import router as campaigns_router
from ad_classifier.api.routes.jobs import router as jobs_router
from ad_classifier.api.routes.search import router as search_router
from ad_classifier.config import load_config, resolve_config_path
from ad_classifier.db.connection import initialize_database


def create_app(
    *,
    config_path: Path | None = None,
    db_path: Path | None = None,
    upload_probe: Callable[[Path], object] | None = None,
) -> FastAPI:
    config, config_file = load_config(config_path)
    resolved_db = db_path or resolve_config_path(config.paths.sqlite_path, config_file)
    initialize_database(resolved_db)

    app = FastAPI(
        title="Ad Classifier API",
        version="0.1.0",
    )
    app.state.config = config
    app.state.config_file = config_file
    app.state.db_path = resolved_db
    app.state.upload_probe = upload_probe

    @app.get("/", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ad-classifier"}

    # Local-first: allow any localhost / 127.0.0.1 port in addition to the
    # explicit allowlist. Browsers treat localhost and 127.0.0.1 as different
    # origins, and Vite may fall back to 5174 if 5173 is held; the regex
    # covers both without forcing the analyst to edit config.yaml.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ads_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(campaigns_router, prefix="/api")

    data_root = resolve_config_path(config.paths.data_root, config_file)
    data_root.mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=str(data_root)), name="data")

    return app
