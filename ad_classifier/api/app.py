from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ad_classifier.api.routes.ads import router as ads_router
from ad_classifier.api.routes.agent import router as agent_router
from ad_classifier.api.routes.brand_profiles import router as brand_profiles_router
from ad_classifier.api.routes.campaigns import router as campaigns_router
from ad_classifier.api.routes.creative_panel import router as creative_panel_router
from ad_classifier.api.routes.embeddings import router as embeddings_router
from ad_classifier.api.routes.entity_graph import router as entity_graph_router
from ad_classifier.api.routes.evidence import router as evidence_router
from ad_classifier.api.routes.jobs import router as jobs_router
from ad_classifier.api.routes.knowledge import router as knowledge_router
from ad_classifier.api.routes.public import router as public_router
from ad_classifier.api.routes.search import router as search_router
from ad_classifier.api.routes.settings import router as settings_router
from ad_classifier.api.routes.stats import router as stats_router
from ad_classifier.config import load_config, resolve_config_path
from ad_classifier.db.connection import initialize_database, load_sqlite_vec, open_database
from ad_classifier.entity_graph.manager import EntityGraphManager
from ad_classifier.knowledge.manager import KnowledgeManager
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


def create_app(
    *,
    config_path: Path | None = None,
    db_path: Path | None = None,
    upload_probe: Callable[[Path], object] | None = None,
    agent_client_factory: Callable | None = None,
    agent_text_embedder_factory: Callable | None = None,
    agent_visual_text_embedder_factory: Callable | None = None,
    agent_vector_store_factory: Callable | None = None,
    creative_panel_client_factory: Callable | None = None,
    brand_profile_client_factory: Callable | None = None,
) -> FastAPI:
    config, config_file = load_config(config_path)
    resolved_db = db_path or resolve_config_path(config.paths.sqlite_path, config_file)
    initialize_database(resolved_db)
    vector_conn = open_database(resolved_db)
    try:
        load_sqlite_vec(vector_conn)
        SqliteVecStore(
            vector_conn,
            text_dim=config.vector_store.text_dim,
            visual_dim=config.vector_store.visual_dim,
        ).ensure_tables()
        vector_conn.commit()
    finally:
        vector_conn.close()

    # Surface agent loop diagnostics in the uvicorn console so SSE failures are
    # visible without needing structlog wiring. Idempotent across re-creation.
    agent_logger = logging.getLogger("ad_classifier.agent")
    if agent_logger.level == logging.NOTSET or agent_logger.level > logging.INFO:
        agent_logger.setLevel(logging.INFO)
    if not agent_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        agent_logger.addHandler(handler)
        agent_logger.propagate = False

    app = FastAPI(
        title="Ad Classifier API",
        version="0.1.0",
    )
    app.state.config = config
    app.state.config_file = config_file
    app.state.db_path = resolved_db
    app.state.upload_probe = upload_probe
    app.state.agent_client_factory = agent_client_factory
    app.state.agent_text_embedder_factory = agent_text_embedder_factory
    app.state.agent_visual_text_embedder_factory = agent_visual_text_embedder_factory
    app.state.agent_vector_store_factory = agent_vector_store_factory
    app.state.creative_panel_client_factory = creative_panel_client_factory
    app.state.brand_profile_client_factory = brand_profile_client_factory

    kb_path = resolved_db.parent / "knowledge.db"
    kb = KnowledgeManager(kb_path)
    app.state.knowledge_manager = kb
    entity_graph_path = resolve_config_path(config.paths.entity_graph_path, config_file)
    entity_crawler_config_path = resolve_config_path(
        config.paths.entity_crawler_config_path, config_file
    )
    app.state.entity_graph_manager = EntityGraphManager(
        entity_graph_path,
        resolved_db,
        crawler_config_path=entity_crawler_config_path,
        knowledge_db_path=kb_path,
    )

    @app.get("/", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ad-classifier"}

    @app.get("/api/health", tags=["health"])
    def api_health() -> dict[str, str]:
        return health()

    # Allow any localhost / 127.0.0.1 port in addition to the explicit
    # allowlist. Browsers treat localhost and 127.0.0.1 as different origins,
    # and Vite may fall back to 5174 if 5173 is held; the regex covers both
    # without forcing the analyst to edit config.yaml.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if config.api.public.enabled:
        from ad_classifier.api.middleware import ApiKeyMiddleware

        app.add_middleware(
            ApiKeyMiddleware,
            public_api_key=config.api.public.api_key,
        )

    app.include_router(ads_router, prefix="/api")
    app.include_router(evidence_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")
    app.include_router(brand_profiles_router, prefix="/api")
    app.include_router(creative_panel_router, prefix="/api")
    app.include_router(campaigns_router, prefix="/api")
    app.include_router(agent_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")
    app.include_router(embeddings_router, prefix="/api")
    app.include_router(entity_graph_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    if config.api.public.enabled:
        app.include_router(public_router, prefix="/api")

    data_root = resolve_config_path(config.paths.data_root, config_file)
    data_root.mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=str(data_root)), name="data")

    return app
