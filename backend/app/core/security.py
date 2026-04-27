"""
Password hashing, JWT creation, and Fernet key derivation for secrets.
"""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# pbkdf2_sha256 avoids bcrypt backend issues in some Python/container environments
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    """
    Check a plain password against a stored bcrypt hash.

    Args:
        plain: Submitted password.
        hashed: Stored hash from the database.

    Returns:
        True if the password matches.
    """
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    """
    Hash a password for storage.

    Args:
        plain: Raw password.

    Returns:
        Bcrypt hash string.
    """
    return pwd_context.hash(plain)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Encode a JWT with optional expiry override.

    Args:
        data: Payload claims (sub, role, etc.).
        expires_delta: If set, overrides default from settings.

    Returns:
        Signed JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Validate and decode a JWT.

    Args:
        token: Bearer token string.

    Returns:
        Decoded claims.

    Raises:
        JWTError: If signature or claims are invalid.
    """
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def fernet_key_from_settings() -> bytes:
    """
    Derive a 32-byte URL-safe key for Fernet from application secret.

    Returns:
        Fernet-compatible key bytes.
    """
    settings = get_settings()
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)
