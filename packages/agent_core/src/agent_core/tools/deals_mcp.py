"""Deals MCP client - calls Deals MCP server via HTTP.

This module provides the client-side interface for calling Deals MCP tools.
The actual implementation lives in the Deals MCP server (apps/mcp_servers/deals/).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from common.config import get_settings
from common.logging import get_logger
from agent_core.tools.mcp_client import call_mcp_tool, MCPToolResult

logger = get_logger(__name__)
settings = get_settings()


class DealsMCPToolResult(BaseModel):
    """Result from a Deals MCP tool call."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0


# Available Deals MCP tools
DEALS_TOOLS = [
    "get_opportunity_details",
    "get_prescreening_report",
    "get_investment_memo",
    "get_opportunity_activity",
]


async def call_deals_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> DealsMCPToolResult:
    """
    Call a Deals MCP tool via HTTP.

    Args:
        tool_name: Name of the tool to call
        arguments: Arguments to pass to the tool

    Returns:
        DealsMCPToolResult with the tool output
    """
    if tool_name not in DEALS_TOOLS:
        return DealsMCPToolResult(
            success=False,
            error=f"Unknown Deals tool: {tool_name}",
        )

    start_time = datetime.utcnow()

    try:
        logger.info(f"[MCP] Calling deals:{tool_name}")

        result: MCPToolResult = await call_mcp_tool(
            server_url=settings.mcp_deals_url,
            tool_name=tool_name,
            arguments=arguments,
        )

        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        if result.success:
            # Extract success/data/error from the MCP response
            data = result.data or {}
            return DealsMCPToolResult(
                success=data.get("success", True),
                data=data.get("data"),
                error=data.get("error"),
                latency_ms=latency_ms,
            )
        else:
            return DealsMCPToolResult(
                success=False,
                error=result.error,
                latency_ms=latency_ms,
            )

    except Exception as e:
        logger.error(f"[MCP] deals:{tool_name} failed", error=str(e))
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        return DealsMCPToolResult(
            success=False,
            error=f"Tool execution failed: {str(e)}",
            latency_ms=latency_ms,
        )


# Convenience functions for backward compatibility


async def get_opportunity_details(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
) -> DealsMCPToolResult:
    """Get detailed information about an opportunity."""
    return await call_deals_tool(
        "get_opportunity_details",
        {
            "opportunity_id": opportunity_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
    )


def list_available_tools() -> list[str]:
    """List all available Deals MCP tools."""
    return DEALS_TOOLS.copy()
