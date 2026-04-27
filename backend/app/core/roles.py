"""
User role definitions and authorization helpers.
"""

from enum import StrEnum


class Role(StrEnum):
    """Application roles, ordered from highest to lowest privilege."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    PRODUCT_MANAGER = "product_manager"
    USER = "user"


ROLE_HIERARCHY: dict[Role, int] = {
    Role.SUPERADMIN: 4,
    Role.ADMIN: 3,
    Role.PRODUCT_MANAGER: 2,
    Role.USER: 1,
}


def at_least(role: Role, required: Role) -> bool:
    """
    Return True if `role` has at least the privilege level of `required`.

    Args:
        role: The user's role.
        required: The minimum required role.

    Returns:
        Whether the user satisfies the role requirement.
    """
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY.get(required, 0)
