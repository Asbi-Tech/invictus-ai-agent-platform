"""Authentication utilities for MCP servers."""

from common.errors import AuthorizationError
from common.logging import get_logger

logger = get_logger(__name__)


def validate_tenant_access(tenant_id: str) -> None:
    """
    Validate that the tenant has access.

    For MVP, this is a simple validation that checks tenant_id is present.
    In production, verify against tenant registry.

    Args:
        tenant_id: The tenant ID to validate

    Raises:
        AuthorizationError: If the tenant_id is missing or invalid
    """
    if not tenant_id:
        raise AuthorizationError("tenant_id is required")

    if not isinstance(tenant_id, str) or len(tenant_id) < 1:
        raise AuthorizationError("Invalid tenant_id format")

    logger.debug("Tenant access validated", tenant_id=tenant_id)


def validate_user_access(
    user_id: str,
    tenant_id: str,
    resource_type: str,
    action: str = "read",
) -> None:
    """
    Validate that the user has access to a resource type.

    For MVP, this is a placeholder that validates user_id is present.
    In production, check user permissions against the resource.

    Args:
        user_id: The user ID to validate
        tenant_id: The tenant ID
        resource_type: The type of resource being accessed
        action: The action being performed (read, write, delete)

    Raises:
        AuthorizationError: If access is denied
    """
    if not user_id:
        raise AuthorizationError("user_id is required")

    if not isinstance(user_id, str) or len(user_id) < 1:
        raise AuthorizationError("Invalid user_id format")

    logger.debug(
        "User access validated",
        user_id=user_id,
        tenant_id=tenant_id,
        resource_type=resource_type,
        action=action,
    )


def validate_entity_access(
    user_id: str,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    action: str = "read",
) -> None:
    """
    Validate that the user has access to a specific entity.

    For MVP, this validates the entity belongs to the tenant.
    In production, check fine-grained permissions.

    Args:
        user_id: The user ID
        tenant_id: The tenant ID
        entity_type: The type of entity
        entity_id: The entity ID
        action: The action being performed

    Raises:
        AuthorizationError: If access is denied
    """
    validate_user_access(user_id, tenant_id, entity_type, action)

    logger.debug(
        "Entity access validated",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
    )
