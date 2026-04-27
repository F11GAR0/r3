"""
Lightweight schema patches for app_settings (no Alembic in dev).
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_app_settings_patches(conn: AsyncConnection) -> None:
    """
    Add columns introduced after first deploy. Safe to run every startup.

    Args:
        conn: Open async connection.
    """
    d = conn.dialect.name
    if d == "postgresql":
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS redmine_insecure_ssl "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS redmine_complexity_field_id "
                "INTEGER NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS ldap_enabled "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS "
                "ldap_server_uri VARCHAR(1024) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS "
                "ldap_bind_dn VARCHAR(1024) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS "
                "ldap_bind_password_encrypted TEXT NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS "
                "ldap_user_base_dn VARCHAR(1024) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS "
                "ldap_user_filter VARCHAR(512) NULL"
            )
        )
        return
    if d == "sqlite":
        r = (await conn.execute(text("PRAGMA table_info(app_settings)"))).fetchall()
        cols = {str(row[1]) for row in r}
        if "redmine_insecure_ssl" not in cols:
            sql = (
                "ALTER TABLE app_settings ADD COLUMN redmine_insecure_ssl "
                "BOOLEAN NOT NULL DEFAULT 0"
            )
            await conn.execute(text(sql))
        r2 = (await conn.execute(text("PRAGMA table_info(app_settings)"))).fetchall()
        cols2 = {str(row[1]) for row in r2}
        if "redmine_complexity_field_id" not in cols2:
            await conn.execute(
                text("ALTER TABLE app_settings ADD COLUMN redmine_complexity_field_id INTEGER NULL")
            )
        r3 = (await conn.execute(text("PRAGMA table_info(app_settings)"))).fetchall()
        cols3 = {str(row[1]) for row in r3}
        if "ldap_enabled" not in cols3:
            await conn.execute(
                text("ALTER TABLE app_settings ADD COLUMN ldap_enabled BOOLEAN NOT NULL DEFAULT 0")
            )
        r4 = (await conn.execute(text("PRAGMA table_info(app_settings)"))).fetchall()
        cols4 = {str(row[1]) for row in r4}
        for name, sql in (
            (
                "ldap_server_uri",
                "ALTER TABLE app_settings ADD COLUMN ldap_server_uri VARCHAR(1024) NULL",
            ),
            (
                "ldap_bind_dn",
                "ALTER TABLE app_settings ADD COLUMN ldap_bind_dn VARCHAR(1024) NULL",
            ),
            (
                "ldap_bind_password_encrypted",
                "ALTER TABLE app_settings ADD COLUMN ldap_bind_password_encrypted TEXT NULL",
            ),
            (
                "ldap_user_base_dn",
                "ALTER TABLE app_settings ADD COLUMN ldap_user_base_dn VARCHAR(1024) NULL",
            ),
            (
                "ldap_user_filter",
                "ALTER TABLE app_settings ADD COLUMN ldap_user_filter VARCHAR(512) NULL",
            ),
        ):
            if name not in cols4:
                await conn.execute(text(sql))
            r4 = (await conn.execute(text("PRAGMA table_info(app_settings)"))).fetchall()
            cols4 = {str(row[1]) for row in r4}
        return


async def apply_user_patches(conn: AsyncConnection) -> None:
    """Add columns to users (per-user JSON overrides)."""
    d = conn.dialect.name
    if d == "postgresql":
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_prompts_json JSONB NULL")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS redmine_api_key_encrypted TEXT NULL")
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS redmine_skip_tls "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )
        return
    if d == "sqlite":
        r = (await conn.execute(text("PRAGMA table_info(users)"))).fetchall()
        cols = {str(row[1]) for row in r}
        if "ai_prompts_json" not in cols:
            await conn.execute(text("ALTER TABLE users ADD COLUMN ai_prompts_json JSON NULL"))
        r2 = (await conn.execute(text("PRAGMA table_info(users)"))).fetchall()
        cols2 = {str(row[1]) for row in r2}
        if "redmine_api_key_encrypted" not in cols2:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN redmine_api_key_encrypted TEXT NULL")
            )
        r3 = (await conn.execute(text("PRAGMA table_info(users)"))).fetchall()
        cols3 = {str(row[1]) for row in r3}
        if "redmine_skip_tls" not in cols3:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN redmine_skip_tls BOOLEAN NOT NULL DEFAULT 0")
            )
        return
