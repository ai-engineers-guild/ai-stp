"""Application factory and lifespan (SPEC-017 REQ-1701, REQ-1702).

A deterministic factory builds an app from validated settings with no module
global state. The lifespan acquires the engine and session factory and disposes
them on shutdown. A missing required secret raises in load_settings, which
surfaces as a typed startup failure.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal, cast

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from ai_stp_api.correlation import CorrelationMiddleware
from ai_stp_api.errors import register_exception_handlers
from ai_stp_api.observability import configure_observability
from ai_stp_api.rate_limit import RateLimitMiddleware, SlidingWindowLimiter
from ai_stp_api.settings import Settings, load_settings
from ai_stp_api.slices.auth.oauth import build_oauth
from ai_stp_api.slices.auth.router import router as auth_router
from ai_stp_api.slices.catalog.router import router as catalog_router
from ai_stp_api.slices.complaints.router import router as complaints_router
from ai_stp_api.slices.devices.router import router as devices_router
from ai_stp_api.slices.documents.router import router as documents_router
from ai_stp_api.slices.grants.router import router as grants_router
from ai_stp_api.slices.health.router import router as health_router
from ai_stp_api.slices.owner.router import router as owner_router
from ai_stp_api.slices.profile.router import router as profile_router
from ai_stp_api.slices.publish.router import router as publish_router
from ai_stp_api.slices.reports.router import router as reports_router
from ai_stp_api.slices.selection.router import router as selection_router
from ai_stp_api.slices.sync.router import router as sync_router
from ai_stp_api.slices.system.router import router as system_router
from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.logging import configure_logging, get_logger

_API_PREFIX = "/v1"
_SERVICE_NAME = "ai-stp-api"
_SameSite = Literal["lax", "strict", "none"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI application from validated settings."""
    resolved = settings or load_settings()
    configure_logging(resolved.service.log_dir)
    log = get_logger("app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        from ai_stp_platform.storage import AvatarObjectStore, MemoryObjectClient, S3ObjectClient

        engine = make_engine(resolved.database)
        app.state.settings = resolved
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        app.state.oauth = build_oauth(resolved.auth)
        # Tests and offline environments use in-memory object store; production uses S3/RustFS.
        memory_client: MemoryObjectClient | None = None
        s3_client: S3ObjectClient | None = None
        if resolved.service.environment == "test" or resolved.storage.endpoint.startswith(
            "memory://"
        ):
            memory_client = MemoryObjectClient()
            app.state.object_client = memory_client
            app.state.avatar_store = AvatarObjectStore(
                settings=resolved.storage, client=memory_client
            )
        else:
            s3_client = S3ObjectClient(resolved.storage)
            await s3_client.__aenter__()
            await s3_client.ensure_bucket()
            app.state.object_client = s3_client
            app.state.avatar_store = AvatarObjectStore(settings=resolved.storage, client=s3_client)
        log.info("startup", environment=resolved.service.environment)
        try:
            yield
        finally:
            if s3_client is not None:
                await s3_client.__aexit__(None, None, None)
            await engine.dispose()
            log.info("shutdown")

    app = FastAPI(
        title="ai_stp platform API",
        version=resolved.service.version,
        lifespan=lifespan,
    )
    # SessionMiddleware holds ONLY OAuth handshake state (state, code_verifier).
    # Application sessions use the opaque account_session table (ADR-0041).
    app.add_middleware(
        SessionMiddleware,
        secret_key=resolved.auth.secret_key,
        same_site=cast("_SameSite", resolved.auth.cookie_samesite),
        https_only=resolved.auth.cookie_secure,
    )
    app.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowLimiter(
            maximum=resolved.service.rate_limit_requests,
            window_seconds=resolved.service.rate_limit_window_seconds,
            max_keys=resolved.service.rate_limit_max_keys,
        ),
    )
    app.add_middleware(CorrelationMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router, prefix=_API_PREFIX)
    app.include_router(system_router, prefix=_API_PREFIX)
    app.include_router(auth_router, prefix=_API_PREFIX)
    app.include_router(devices_router, prefix=_API_PREFIX)
    app.include_router(catalog_router, prefix=_API_PREFIX)
    app.include_router(complaints_router, prefix=_API_PREFIX)
    app.include_router(sync_router, prefix=_API_PREFIX)
    app.include_router(publish_router, prefix=_API_PREFIX)
    app.include_router(grants_router, prefix=_API_PREFIX)
    app.include_router(reports_router, prefix=_API_PREFIX)
    app.include_router(selection_router, prefix=_API_PREFIX)
    app.include_router(owner_router, prefix=_API_PREFIX)
    app.include_router(profile_router, prefix=_API_PREFIX)
    app.include_router(documents_router, prefix=_API_PREFIX)
    configure_observability(
        app,
        service_name=_SERVICE_NAME,
        exporter_endpoint=resolved.service.otel_exporter_endpoint,
        exporter_headers=resolved.service.otel_headers(),
    )
    return app
