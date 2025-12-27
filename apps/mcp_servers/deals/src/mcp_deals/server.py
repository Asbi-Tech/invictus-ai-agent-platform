"""FastAPI server configuration for Deals MCP domain.

This server exposes MCP tools via HTTP JSON-RPC at the /mcp endpoint.
"""

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any

from mcp_deals.tools import (
    get_opportunity_details,
    get_prescreening_report,
    get_investment_memo,
    get_opportunity_activity,
)

logger = structlog.get_logger(__name__)

# Tool registry mapping tool names to async functions
TOOLS = {
    "get_opportunity_details": get_opportunity_details,
    "get_prescreening_report": get_prescreening_report,
    "get_investment_memo": get_investment_memo,
    "get_opportunity_activity": get_opportunity_activity,
}


class MCPToolCallParams(BaseModel):
    """Parameters for a tool call."""
    name: str
    arguments: dict[str, Any]


class MCPRequest(BaseModel):
    """JSON-RPC request for MCP."""
    jsonrpc: str = "2.0"
    method: str
    params: MCPToolCallParams
    id: int | str = 1


class MCPSuccessResponse(BaseModel):
    """JSON-RPC success response."""
    jsonrpc: str = "2.0"
    result: dict[str, Any]
    id: int | str = 1


class MCPErrorResponse(BaseModel):
    """JSON-RPC error response."""
    jsonrpc: str = "2.0"
    error: dict[str, Any]
    id: int | str = 1


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Deals MCP Server",
        description="MCP server for Deals/Opportunities domain",
        version="1.0.0",
    )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "deals-mcp"}

    @app.get("/tools")
    async def list_tools():
        """List available MCP tools."""
        return {
            "tools": list(TOOLS.keys()),
            "count": len(TOOLS),
        }

    @app.post("/mcp")
    async def handle_mcp_request(request: MCPRequest) -> dict[str, Any]:
        """
        Handle MCP JSON-RPC requests.

        Expects:
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "tool_name",
                    "arguments": {...}
                },
                "id": 1
            }

        Returns:
            {
                "jsonrpc": "2.0",
                "result": {...},
                "id": 1
            }
        """
        logger.info(
            "[MCP] Received request",
            method=request.method,
            tool=request.params.name,
        )

        # Validate method
        if request.method != "tools/call":
            logger.warning("[MCP] Invalid method", method=request.method)
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {request.method}",
                },
                "id": request.id,
            }

        tool_name = request.params.name
        arguments = request.params.arguments

        # Check if tool exists
        if tool_name not in TOOLS:
            logger.warning("[MCP] Unknown tool", tool=tool_name)
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": f"Unknown tool: {tool_name}",
                },
                "id": request.id,
            }

        # Call the tool
        try:
            tool_fn = TOOLS[tool_name]
            result = await tool_fn(**arguments)

            logger.info(
                "[MCP] Tool call succeeded",
                tool=tool_name,
                success=result.get("success", True),
            )

            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": request.id,
            }

        except TypeError as e:
            # Handle missing or invalid arguments
            logger.error("[MCP] Invalid arguments", tool=tool_name, error=str(e))
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": f"Invalid arguments: {str(e)}",
                },
                "id": request.id,
            }
        except Exception as e:
            logger.error("[MCP] Tool execution failed", tool=tool_name, error=str(e))
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"Tool execution failed: {str(e)}",
                },
                "id": request.id,
            }

    return app
