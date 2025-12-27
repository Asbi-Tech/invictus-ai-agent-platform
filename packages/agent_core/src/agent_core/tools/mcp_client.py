"""MCP client for calling domain MCP servers."""

from typing import Any

import httpx
from pydantic import BaseModel

from common.config import get_settings
from common.errors import MCPError
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class MCPToolResult(BaseModel):
    """Result from an MCP tool call."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


class MCPClientRegistry:
    """
    Registry of MCP server endpoints.

    Maintains a mapping of domain names to MCP server URLs.
    """

    def __init__(self):
        self._servers: dict[str, str] = {}
        self._load_from_settings()

    def _load_from_settings(self) -> None:
        """Load MCP server URLs from settings."""
        self._servers = {
            "deals": settings.mcp_deals_url,
            "clients": settings.mcp_clients_url,
            "risk_planning": settings.mcp_risk_planning_url,
            "reporting": settings.mcp_reporting_url,
            "admin_policy": settings.mcp_admin_policy_url,
        }

    def register(self, domain: str, url: str) -> None:
        """
        Register an MCP server.

        Args:
            domain: The domain name (e.g., "opportunities")
            url: The server URL
        """
        self._servers[domain] = url
        logger.info("Registered MCP server", domain=domain, url=url)

    def get_url(self, domain: str) -> str | None:
        """
        Get the URL for a domain's MCP server.

        Args:
            domain: The domain name

        Returns:
            The server URL if registered, None otherwise
        """
        return self._servers.get(domain)

    def list_domains(self) -> list[str]:
        """
        List all registered domains.

        Returns:
            List of domain names
        """
        return list(self._servers.keys())

    def is_available(self, domain: str) -> bool:
        """
        Check if a domain's MCP server is registered.

        Args:
            domain: The domain name

        Returns:
            True if the server is registered
        """
        return domain in self._servers and bool(self._servers[domain])


# Global registry instance
mcp_registry = MCPClientRegistry()


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 30.0,
) -> MCPToolResult:
    """
    Call a tool on an MCP server.

    Args:
        server_url: The MCP server URL
        tool_name: The name of the tool to call
        arguments: Arguments to pass to the tool
        timeout: Request timeout in seconds

    Returns:
        MCPToolResult with the response data or error
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            # MCP uses JSON-RPC style calls
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
                "id": 1,
            }

            logger.debug(
                "Calling MCP tool",
                server=server_url,
                tool=tool_name,
            )

            response = await client.post(
                f"{server_url}/mcp",
                json=payload,
            )
            response.raise_for_status()

            result = response.json()

            if "error" in result:
                error_msg = result["error"].get("message", "Unknown MCP error")
                logger.warning(
                    "MCP tool returned error",
                    tool=tool_name,
                    error=error_msg,
                )
                return MCPToolResult(success=False, error=error_msg)

            return MCPToolResult(
                success=True,
                data=result.get("result", {}),
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "MCP HTTP error",
                status=e.response.status_code,
                server=server_url,
            )
            return MCPToolResult(
                success=False,
                error=f"HTTP {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.error(
                "MCP connection error",
                error=str(e),
                server=server_url,
            )
            return MCPToolResult(
                success=False,
                error=f"Connection error: {e}",
            )
        except Exception as e:
            logger.error(
                "MCP call error",
                error=str(e),
                server=server_url,
            )
            return MCPToolResult(success=False, error=str(e))


async def call_domain_tool(
    domain: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 30.0,
) -> MCPToolResult:
    """
    Call a tool on a domain's MCP server.

    Args:
        domain: The domain name (e.g., "opportunities")
        tool_name: The name of the tool to call
        arguments: Arguments to pass to the tool
        timeout: Request timeout in seconds

    Returns:
        MCPToolResult with the response data or error

    Raises:
        MCPError: If the domain is not registered
    """
    server_url = mcp_registry.get_url(domain)
    if not server_url:
        raise MCPError(
            f"MCP server not registered for domain: {domain}",
            server_name=domain,
        )

    return await call_mcp_tool(server_url, tool_name, arguments, timeout)


async def get_entity_data(
    domain: str,
    entity_type: str,
    entity_id: str,
    tenant_id: str,
) -> MCPToolResult:
    """
    Get entity data from an MCP server.

    This is a convenience wrapper for common entity retrieval patterns.

    Args:
        domain: The domain name
        entity_type: The type of entity (e.g., "opportunity", "client")
        entity_id: The entity ID
        tenant_id: The tenant ID for access control

    Returns:
        MCPToolResult with the entity data or error
    """
    tool_name = f"get_{entity_type}"
    arguments = {
        f"{entity_type}_id": entity_id,
        "tenant_id": tenant_id,
    }

    return await call_domain_tool(domain, tool_name, arguments)


async def list_entity_documents(
    domain: str,
    entity_type: str,
    entity_id: str,
    tenant_id: str,
) -> MCPToolResult:
    """
    List documents associated with an entity.

    Args:
        domain: The domain name
        entity_type: The type of entity
        entity_id: The entity ID
        tenant_id: The tenant ID for access control

    Returns:
        MCPToolResult with the document list or error
    """
    tool_name = f"list_{entity_type}_documents"
    arguments = {
        f"{entity_type}_id": entity_id,
        "tenant_id": tenant_id,
    }

    return await call_domain_tool(domain, tool_name, arguments)
