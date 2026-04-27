"""
R3 FastAPI application: Redmine-integrated agile helper with optional AI and LDAP.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from app.api import (
    routes_admin,
    routes_auth,
    routes_backlog,
    routes_history,
    routes_issues,
    routes_profile,
    routes_settings,
    routes_stats,
    routes_wizard,
)
from app.bootstrap import ensure_bootstrap
from app.core.config import get_settings
from app.db import session as session_mod
from app.db.session import create_all_tables, init_engine, session_scope


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    On startup, create database schema and default admin; on shutdown, dispose engine.

    Args:
        _app: FastAPI instance (unused).
    """
    init_engine()
    await create_all_tables()
    async with session_scope() as session:
        await ensure_bootstrap(session)
    yield
    s = get_settings()
    if not s.use_sqlite and session_mod._engine:  # noqa: SLF001
        await session_mod._engine.dispose()  # type: ignore


def build_app() -> FastAPI:
    """
    Create configured FastAPI app with routes and CORS.

    Returns:
        Application instance.
    """
    s = get_settings()
    app = FastAPI(title=s.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_auth.router)
    app.include_router(routes_admin.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_issues.router)
    app.include_router(routes_wizard.router)
    app.include_router(routes_profile.router)
    app.include_router(routes_stats.router)
    app.include_router(routes_history.router)
    app.include_router(routes_backlog.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """
        Liveness and readiness for orchestrators and docker-compose.
        """
        return {"status": "ok", "app": s.app_name}

    @app.get(
        "/api/tls/root-ca",
        response_model=None,
    )
    def download_root_ca():
        """
        If TLS_CERT_DIR/rootCA.pem exists (docker entrypoint), serve it; else return guidance text.
        """
        base = os.environ.get("TLS_CERT_DIR", "/certs")
        p = Path(base) / "rootCA.pem"
        if p.is_file():
            return FileResponse(
                p, filename="r3-rootCA.pem", media_type="application/x-x509-ca-cert"
            )
        return PlainTextResponse(
            "CA file not yet generated. Use HTTP or run TLS init.", status_code=404
        )

    return app


app = build_app()
