"""
Encrypt and decrypt API keys at rest using Fernet.
"""

from cryptography.fernet import Fernet

from app.core.security import fernet_key_from_settings


def get_fernet() -> Fernet:
    """
    Build a Fernet instance from application settings.

    Returns:
        Configured Fernet encrypter.
    """
    return Fernet(fernet_key_from_settings())


def encrypt_secret(plain: str) -> str:
    """
    Encrypt a secret string for database storage.

    Args:
        plain: Raw secret.

    Returns:
        Base64 token safe for text column.
    """
    f = get_fernet()
    return f.encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    """
    Decrypt a stored secret.

    Args:
        token: Ciphertext from encrypt_secret.

    Returns:
        Original plaintext.
    """
    f = get_fernet()
    return f.decrypt(token.encode()).decode()
