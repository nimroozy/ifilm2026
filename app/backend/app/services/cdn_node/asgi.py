"""ASGI factory for the production CDN node service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.core.logging_filters import install_token_redaction_logging
from app.services.branch_cache.data_plane.cache_store import CacheStore
from app.services.branch_cache.data_plane.engine import BranchDataPlaneEngine
from app.services.branch_cache.service.app import create_branch_cache_app
from app.services.branch_cache.service.config import BranchServiceConfig
from app.services.cdn_node.config import (
    NodeRuntimeConfig,
    load_node_runtime_config,
    node_settings,
)
from app.services.cdn_node.heartbeat import HeartbeatClient
from app.services.cdn_node.origin import CentralHttpOriginFetcher


def build_service_config(cfg: NodeRuntimeConfig, *, origin: Any | None = None) -> BranchServiceConfig:
    settings = node_settings(cfg)
    fetcher = origin or CentralHttpOriginFetcher(
        central_url=cfg.central_url,
        node_id=cfg.node_id,
        node_token=cfg.node_token,
        max_object_bytes=cfg.max_object_bytes,
        connect_timeout_seconds=cfg.connect_timeout_seconds,
        read_timeout_seconds=cfg.read_timeout_seconds,
    )
    return BranchServiceConfig(
        node_id=cfg.node_id,
        site_id=cfg.site_id,
        public_key_pem=cfg.public_key_pem,
        cache_root=cfg.cache_root,
        origin=fetcher,
        settings=settings,
        enable_health=True,
        enable_ready=True,
        enable_metrics=True,
        max_concurrent_fills=cfg.max_concurrent_fills,
        high_watermark_bytes=cfg.high_watermark_bytes,
        low_watermark_bytes=cfg.low_watermark_bytes,
        # Headroom kept under the high watermark before eviction (bounded for small caches).
        min_free_bytes=max(1_000_000, min(64 * 1024 * 1024, (cfg.cache_limit_bytes - cfg.high_watermark_bytes) // 2)),
        runtime_mode="node",
    )


def create_node_app(
    cfg: NodeRuntimeConfig | None = None,
    *,
    origin: Any | None = None,
    heartbeat_client: Any | None = None,
    start_heartbeat: bool = True,
) -> FastAPI:
    runtime = cfg or load_node_runtime_config()
    service_cfg = build_service_config(runtime, origin=origin)
    app = create_branch_cache_app(service_cfg)
    engine: BranchDataPlaneEngine = app.state.branch_engine
    cache: CacheStore = engine.cache
    heartbeat = HeartbeatClient(runtime, cache=cache, state=app.state.branch_state, client=heartbeat_client)
    app.state.node_runtime = runtime
    app.state.heartbeat = heartbeat

    inner_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        install_token_redaction_logging()
        if start_heartbeat:
            heartbeat.start()
        async with inner_lifespan(application):
            yield
        heartbeat.stop()

    app.router.lifespan_context = lifespan
    app.title = "iFilm CDN node"
    return app


def create_app() -> FastAPI:
    """Uvicorn factory: ``uvicorn app.services.cdn_node.asgi:create_app --factory``."""
    return create_node_app()
