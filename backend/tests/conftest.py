"""
Pytest fixtures: in-memory SQLite and async test client.
"""

import os
from collections.abc import AsyncGenerator

os.environ["SECRET_KEY"] = "test-secret-key-32-chars-abcdefghijk"
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.roles import Role
from app.core.security import hash_password
from app.db import session as session_mod
from app.db.session import init_engine, session_scope
from app.main import build_app
from app.models import User

get_settings.cache_clear()


@pytest.fixture
async def app_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTPX client: app lifespan bootstraps DB; then add a regular user for role tests.
    """
    get_settings.cache_clear()
    if session_mod._engine:  # noqa: SLF001
        await session_mod._engine.dispose()  # type: ignore
    session_mod._engine = None
    session_mod._session_factory = None
    init_engine()
    app = build_app()
    async with LifespanManager(app) as _:
        async with session_scope() as sess:
            sess.add(
                User(
                    username="dev",
                    email="d@d.com",
                    role=Role.USER,
                    hashed_password=hash_password("dev"),
                )
            )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True
        ) as ac:
            yield ac
    if session_mod._engine:  # noqa: SLF001
        await session_mod._engine.dispose()  # type: ignore
    get_settings.cache_clear()
