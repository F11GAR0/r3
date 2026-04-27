"""
Singleton-style application settings row.
"""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, json_col


class AppSettings(TimestampMixin, Base):
    """
    Global app configuration; typically a single row with id=1.

    Redmine and AI are configured by admin here.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    redmine_base_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    redmine_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    redmine_insecure_ssl: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        doc="If True, TLS certificate is not verified (self-signed Redmine).",
    )
    sprint_lifecycle_days: Mapped[int] = mapped_column(Integer, default=14)
    redmine_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # List custom field id in Redmine for t-shirt values s, m, l, xl, 2xl (displayed as label)
    redmine_complexity_field_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSON list of { "provider": "openai|gemini|deepseek", "name": "key1", "encrypted": "..." }
    ai_keys_json: Mapped[dict | None] = mapped_column(json_col(), nullable=True)
    # JSON list of SOCKS5 proxy URLs for outbound AI API calls (round-robin), e.g. ["socks5://127.0.0.1:1080"]
    ai_socks5_proxies_json: Mapped[list | None] = mapped_column(json_col(), nullable=True)
    # LDAP: when ldap_enabled, login uses these; else fall back to env (see ldap_auth).
    ldap_enabled: Mapped[bool] = mapped_column(
        default=False,
        doc="Use stored LDAP config for login.",
    )
    ldap_server_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ldap_bind_dn: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ldap_bind_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    ldap_user_base_dn: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ldap_user_filter: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Search filter, e.g. (uid={username}) or (sAMAccountName={username})",
    )
