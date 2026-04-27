"""
Shared Pydantic response models.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    """JSON Web Token and metadata after login."""

    access_token: str
    token_type: str = "bearer"
    role: str


class UserOut(BaseModel):
    """Public user information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    role: str
    redmine_user_id: int | None = None
    is_ldap: bool = False
    # Effective AI system prompts (defaults merged with users.ai_prompts_json)
    ai_prompts: dict[str, str] = Field(
        default_factory=dict,
        description="split_system, complexity_system, wizard_system",
    )


def build_user_out(user: object) -> UserOut:
    """
    Map User ORM object to API model (injects effective AI prompt merge).

    Args:
        user: SQLAlchemy User.
    """
    from app.services import ai_client

    u: Any = user
    return UserOut(
        id=int(u.id),
        username=str(u.username),
        email=getattr(u, "email", None),
        full_name=getattr(u, "full_name", None),
        role=str(getattr(u, "role", "user")),
        redmine_user_id=getattr(u, "redmine_user_id", None),
        is_ldap=bool(getattr(u, "is_ldap", False)),
        ai_prompts=ai_client.effective_ai_prompts(getattr(u, "ai_prompts_json", None)),
    )


class AppSettingsIn(BaseModel):
    """Update payload for application settings (admin)."""

    redmine_base_url: str | None = None
    redmine_api_key: str | None = Field(None, description="Set only when changing; omit to keep")
    redmine_insecure_ssl: bool | None = None
    sprint_lifecycle_days: int | None = Field(None, ge=1, le=365)
    redmine_complexity_field_id: int | None = Field(
        None,
        ge=1,
        description="List custom field id in Redmine for label values s, m, l, xl, 2xl",
    )
    # Merge into existing keys; never deletes keys (omit key to keep ciphertext)
    ai_keys: list[dict[str, str]] | None = None
    project_id: int | None = None
    # LDAP: when ldap_enabled, DB config is used; empty password keeps stored hash.
    ldap_enabled: bool | None = None
    ldap_server_uri: str | None = None
    ldap_bind_dn: str | None = None
    ldap_bind_password: str | None = Field(
        None, description="Set when changing; omit or empty to keep stored bind password"
    )
    ldap_user_base_dn: str | None = None
    ldap_user_filter: str | None = None


class AIKeyEntryOut(BaseModel):
    """One stored key slot (no secret)."""

    provider: str
    name: str


class AppSettingsOut(BaseModel):
    """Non-secret settings for clients."""

    redmine_base_url: str | None = None
    redmine_insecure_ssl: bool = False
    sprint_lifecycle_days: int = 14
    redmine_complexity_field_id: int | None = None
    has_redmine: bool = False
    has_ai: bool = False
    project_id: int | None = None
    ai_key_entries: list[AIKeyEntryOut] = Field(default_factory=list)
    # LDAP: stored config (no passwords). ldap_effective = login will try LDAP.
    ldap_enabled: bool = False
    ldap_server_uri: str | None = None
    ldap_bind_dn: str | None = None
    ldap_user_base_dn: str | None = None
    ldap_user_filter: str | None = None
    has_ldap_bind_password: bool = False
    ldap_effective: bool = False
