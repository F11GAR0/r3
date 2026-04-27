"""
Admin settings: Redmine URL, API key, sprint window, AI keys, TLS trust for Redmine.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from ldap3 import ALL, Connection, Server
from ldap3.core.exceptions import LDAPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_or_create_settings, require_min_role
from app.core.crypto_secrets import decrypt_secret, encrypt_secret
from app.core.roles import Role
from app.db.session import get_db
from app.models import AppSettings, User
from app.schemas.common import AIKeyEntryOut, AppSettingsIn, AppSettingsOut
from app.services import ai_client
from app.services.ai_client import AIProvider
from app.services.ldap_auth import LdapConnectionConfig, resolve_ldap_config, try_ldap_auth

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/ai-providers", response_model=list[dict[str, str]])
async def list_ai_provider_catalogue(
    _: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, str]]:
    """
    Fixed list of supported LLM providers for UI (id + human label).
    """
    return [
        {
            "id": "openai",
            "label": "OpenAI (несколько моделей по очереди при 4xx/5xx/429)",
        },
        {
            "id": "gemini",
            "label": "Google AI (Gemma + Gemini, fallback по списку; AI Studio key)",
        },
        {
            "id": "deepseek",
            "label": "DeepSeek (чат + coder + reasoner по очереди при сбоях)",
        },
    ]


class TestProviderBody(BaseModel):
    """Test connectivity for a provider using the first stored key for that id."""

    provider: str = Field(min_length=2, max_length=32, description="openai|gemini|deepseek")


@router.post("/ai-providers/test", response_model=dict[str, str | bool])
async def test_ai_provider(
    body: TestProviderBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_min_role(Role.ADMIN))],
) -> dict[str, str | bool]:
    """
    Run a minimal API request with the first key for the given provider (decrypt from DB).
    """
    try:
        prov = AIProvider(body.provider.lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Unknown provider id") from e
    s = await get_or_create_settings(session)
    raw = s.ai_keys_json
    if not raw or not isinstance(raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No API keys stored"
        )
    key_str: str | None = None
    for o in raw:
        if not isinstance(o, dict):
            continue
        if str(o.get("provider", "")).lower() != prov.value:
            continue
        enc = o.get("encrypted")
        if enc:
            key_str = decrypt_secret(str(enc))
            break
    if not key_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No saved key for provider {prov.value}",
        )
    ok, err = ai_client.test_provider_reachability(prov, key_str)
    if ok:
        return {"ok": True, "message": "Доступность подтверждена."}
    return {"ok": False, "message": err}


class LdapTestIn(BaseModel):
    """Probe LDAP: service bind, optional user bind (same as login)."""

    ldap_server_uri: str = Field(min_length=4, max_length=1024)
    ldap_bind_dn: str = Field(default="", max_length=1024)
    ldap_bind_password: str = Field(default="", max_length=512)
    ldap_user_base_dn: str = Field(min_length=1, max_length=1024)
    ldap_user_filter: str = Field(default="(uid={username})", max_length=512)
    test_username: str | None = Field(None, max_length=128)
    test_password: str | None = Field(None, max_length=256)


@router.post("/ldap/test", response_model=dict[str, str | bool])
async def test_ldap_settings(
    body: LdapTestIn,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_min_role(Role.ADMIN))],
) -> dict[str, str | bool]:
    """
    Try service-account bind; optionally verify a username/password like /api/auth/login.
    """
    try:
        server = Server(body.ldap_server_uri.strip(), get_info=ALL)
        conn = Connection(
            server,
            user=body.ldap_bind_dn.strip(),
            password=body.ldap_bind_password,
            auto_bind=True,
        )
        conn.unbind()
    except (LDAPException, OSError) as e:
        return {"ok": False, "message": f"Bind сервисной учётки: {e!s}"[:800]}
    if body.test_username and body.test_password:
        cfg = LdapConnectionConfig(
            server_uri=body.ldap_server_uri.strip(),
            bind_dn=body.ldap_bind_dn.strip(),
            bind_password=body.ldap_bind_password,
            user_base_dn=body.ldap_user_base_dn.strip(),
            user_filter=(body.ldap_user_filter or "(uid={username})").strip(),
        )
        info = try_ldap_auth(body.test_username.strip(), body.test_password, cfg)
        if info is None:
            return {
                "ok": False,
                "message": "Bind OK, но вход пользователя (поиск + bind) не удался.",
            }
        return {
            "ok": True,
            "message": f"Bind OK; пользователь {body.test_username!r} — ок.",
        }
    return {
        "ok": True,
        "message": (
            "Bind сервисной учётки успешен. "
            "Добавьте тестовый логин/пароль для проверки входа."
        ),
    }


@router.get("/roles", response_model=list[dict[str, str]])
async def list_app_roles(
    _: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, str]]:
    """Role ids and short descriptions (for admin UI)."""
    return [
        {
            "id": "superadmin",
            "label": "Супер-админ",
            "description": "Полный доступ, в т.ч. назначать superadmin",
        },
        {"id": "admin", "label": "Администратор", "description": "Настройки, пользователи, AI"},
        {
            "id": "product_manager",
            "label": "PM",
            "description": "Бэклог, статистика, история (без смены rолей superadmin)",
        },
        {"id": "user", "label": "Пользователь", "description": "Обычная работа в R3"},
    ]


@router.get("", response_model=AppSettingsOut)
async def get_settings_api(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> AppSettingsOut:
    """Return non-secret application settings for any authenticated user."""
    s = await get_or_create_settings(session)
    return await _build_out(session, s)


@router.put("", response_model=AppSettingsOut)
async def put_settings(
    body: AppSettingsIn,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_min_role(Role.ADMIN))],
) -> AppSettingsOut:
    """
    Update application settings. Admin or higher.

    AI keys are merged: existing entries are never removed; send updates with the same
    provider+name to replace the secret (non-empty key), or empty key to keep the old one.
    """
    s = await get_or_create_settings(session)
    d = body.model_dump(exclude_unset=True)
    if "redmine_base_url" in d and d["redmine_base_url"] is not None:
        s.redmine_base_url = str(d["redmine_base_url"]).rstrip("/")
    if "redmine_api_key" in d and d.get("redmine_api_key", "").strip():
        s.redmine_api_key_encrypted = encrypt_secret(str(d["redmine_api_key"]).strip())
    if "redmine_insecure_ssl" in d and d["redmine_insecure_ssl"] is not None:
        s.redmine_insecure_ssl = bool(d["redmine_insecure_ssl"])
    if "sprint_lifecycle_days" in d and d["sprint_lifecycle_days"] is not None:
        s.sprint_lifecycle_days = int(d["sprint_lifecycle_days"])
    if "redmine_complexity_field_id" in d:
        s.redmine_complexity_field_id = d["redmine_complexity_field_id"]
    if "project_id" in d:
        s.redmine_project_id = d["project_id"]
    if "ai_keys" in d and d["ai_keys"] is not None:
        old = s.ai_keys_json if isinstance(s.ai_keys_json, list) else []
        s.ai_keys_json = _merge_ai_keys(old, d["ai_keys"])
    if "ldap_enabled" in d and d["ldap_enabled"] is not None:
        s.ldap_enabled = bool(d["ldap_enabled"])
    if "ldap_server_uri" in d:
        v = d.get("ldap_server_uri")
        s.ldap_server_uri = (str(v).strip() if v else None) or None
    if "ldap_bind_dn" in d:
        v = d.get("ldap_bind_dn")
        s.ldap_bind_dn = (str(v).strip() if v else None) or None
    if "ldap_user_base_dn" in d:
        v = d.get("ldap_user_base_dn")
        s.ldap_user_base_dn = (str(v).strip() if v else None) or None
    if "ldap_user_filter" in d:
        v = d.get("ldap_user_filter")
        s.ldap_user_filter = (str(v).strip() if v else None) or None
    if "ldap_bind_password" in d and (d.get("ldap_bind_password") or "").strip():
        s.ldap_bind_password_encrypted = encrypt_secret(str(d["ldap_bind_password"]).strip())
    return await _build_out(session, s)


def _merge_ai_keys(
    old_list: list[Any],
    from_body: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    Merge key rows: start from all existing, apply updates, never remove a row.

    Args:
        old_list: Current DB list.
        from_body: New entries from the client; empty key string keeps the old ciphertext.

    Returns:
        New list to persist.
    """
    by: dict[tuple[str, str], dict[str, Any]] = {}
    for o in old_list or []:
        if not isinstance(o, dict) or not o.get("name") or not o.get("provider"):
            continue
        p = str(o.get("provider", "")).lower()
        n = str(o.get("name", ""))
        enc = o.get("encrypted")
        if p and n and enc:
            by[(p, n)] = {"provider": p, "name": n, "encrypted": str(enc)}
    for item in from_body:
        prov = str(item.get("provider", "")).lower()
        name = str(item.get("name", ""))
        key_plain = (item.get("key") or "").strip()
        if not prov or not name:
            continue
        if key_plain:
            by[(prov, name)] = {
                "provider": prov,
                "name": name,
                "encrypted": encrypt_secret(key_plain),
            }
        # empty key: keep by[(prov,name)] if already in by; do nothing if new row without key
    return list(by.values())


async def _build_out(session: AsyncSession, s: AppSettings) -> AppSettingsOut:
    """Map AppSettings to response DTO."""
    entries: list[AIKeyEntryOut] = []
    if s.ai_keys_json and isinstance(s.ai_keys_json, list):
        for k in s.ai_keys_json:
            if isinstance(k, dict) and k.get("name") and k.get("provider"):
                entries.append(
                    AIKeyEntryOut(
                        provider=str(k["provider"]),
                        name=str(k["name"]),
                    )
                )
    ldap_effective = await resolve_ldap_config(session) is not None
    return AppSettingsOut(
        redmine_base_url=s.redmine_base_url,
        redmine_insecure_ssl=bool(s.redmine_insecure_ssl),
        sprint_lifecycle_days=s.sprint_lifecycle_days,
        redmine_complexity_field_id=s.redmine_complexity_field_id,
        has_redmine=bool(s.redmine_base_url and s.redmine_api_key_encrypted),
        has_ai=bool(entries),
        project_id=s.redmine_project_id,
        ai_key_entries=entries,
        ldap_enabled=bool(s.ldap_enabled),
        ldap_server_uri=s.ldap_server_uri,
        ldap_bind_dn=s.ldap_bind_dn,
        ldap_user_base_dn=s.ldap_user_base_dn,
        ldap_user_filter=s.ldap_user_filter,
        has_ldap_bind_password=bool(s.ldap_bind_password_encrypted),
        ldap_effective=ldap_effective,
    )
