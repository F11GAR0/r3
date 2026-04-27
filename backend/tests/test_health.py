"""
Tests for health and auth endpoints.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_health(app_client: AsyncClient) -> None:
    """GET /api/health returns status ok."""
    r = await app_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_login_admin(app_client: AsyncClient) -> None:
    """Default admin can obtain JWT."""
    r = await app_client.post(
        "/api/auth/login", json={"username": "admin", "password": "changeme"}
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["role"] == "superadmin"


async def test_me_unauthorized(app_client: AsyncClient) -> None:
    """GET /api/auth/me without token returns 401."""
    r = await app_client.get("/api/auth/me")
    assert r.status_code == 401
