"""
LDAP bind and user lookup for optional LDAP login (env and/or DB settings).
"""

from dataclasses import dataclass

from ldap3 import ALL, Connection, Server
from ldap3.core.exceptions import LDAPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto_secrets import decrypt_secret
from app.models import AppSettings


@dataclass
class LdapConnectionConfig:
    """Parameters for LDAP search + user bind."""

    server_uri: str
    bind_dn: str
    bind_password: str
    user_base_dn: str
    user_filter: str


@dataclass
class LdapUserInfo:
    """User attributes returned from a successful LDAP bind."""

    username: str
    email: str | None = None
    full_name: str | None = None


def _env_ldap_config() -> LdapConnectionConfig | None:
    """Build config from environment if all required fields are set."""
    s = get_settings()
    if not (
        s.ldap_server_uri.strip()
        and s.ldap_user_base_dn.strip()
        and (s.ldap_user_filter or "").strip()
    ):
        return None
    return LdapConnectionConfig(
        server_uri=s.ldap_server_uri.strip(),
        bind_dn=(s.ldap_bind_dn or "").strip(),
        bind_password=s.ldap_bind_password or "",
        user_base_dn=s.ldap_user_base_dn.strip(),
        user_filter=(s.ldap_user_filter or "(uid={username})").strip(),
    )


async def resolve_ldap_config(session: AsyncSession) -> LdapConnectionConfig | None:
    """
    Effective LDAP config: DB when ldap_enabled and server set, else environment.
    """
    r = await session.execute(select(AppSettings).where(AppSettings.id == 1))
    row = r.scalar_one_or_none()
    if row and row.ldap_enabled and (row.ldap_server_uri or "").strip():
        user_base = (row.ldap_user_base_dn or "").strip()
        if not user_base:
            return _env_ldap_config()
        filt = (row.ldap_user_filter or "").strip() or "(uid={username})"
        pwd = ""
        if row.ldap_bind_password_encrypted:
            pwd = decrypt_secret(str(row.ldap_bind_password_encrypted))
        return LdapConnectionConfig(
            server_uri=row.ldap_server_uri.strip(),
            bind_dn=(row.ldap_bind_dn or "").strip(),
            bind_password=pwd,
            user_base_dn=user_base,
            user_filter=filt,
        )
    return _env_ldap_config()


def try_ldap_auth(username: str, password: str, cfg: LdapConnectionConfig) -> LdapUserInfo | None:
    """
    Search for the user DN and try to bind with the supplied password.

    Args:
        username: User login.
        password: User password (never logged).
        cfg: Connection parameters.

    Returns:
        LdapUserInfo on success, None on failure.
    """
    flt = cfg.user_filter.format(username=username)
    conn: Connection | None = None
    try:
        server = Server(cfg.server_uri, get_info=ALL)
        conn = Connection(
            server,
            user=cfg.bind_dn,
            password=cfg.bind_password,
            auto_bind=True,
        )
        conn.search(
            cfg.user_base_dn,
            flt,
            attributes=["mail", "cn", "displayName", "uid"],
        )
        if not conn.entries:
            return None
        entry = conn.entries[0]
        user_dn = entry.entry_dn
        uconn = Connection(server, user=user_dn, password=password, auto_bind=True)
        uconn.unbind()
        email = str(entry.mail) if hasattr(entry, "mail") else None
        full_name: str | None = None
        if hasattr(entry, "displayName") and entry.displayName:
            full_name = str(entry.displayName)
        elif hasattr(entry, "cn") and entry.cn:
            full_name = str(entry.cn)
        return LdapUserInfo(username=username, email=email, full_name=full_name)
    except LDAPException:
        return None
    finally:
        if conn is not None:
            try:
                conn.unbind()
            except Exception:  # noqa: S110
                pass
