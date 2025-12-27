"""Agent tools for data retrieval and operations."""

from agent_core.tools.mcp_client import (
    MCPClientRegistry,
    MCPToolResult,
    call_domain_tool,
    call_mcp_tool,
    mcp_registry,
)
from agent_core.tools.rag_gateway import (
    ExtractFieldsRequest,
    ExtractFieldsResponse,
    FieldDefinition,
    RetrievalConfig,
    StorageConfig,
    extract_fields,
    generate_fields_for_question,
)
from agent_core.tools.deals_mcp import (
    DealsMCPToolResult,
    call_deals_tool,
    get_opportunity_details,
    list_available_tools as list_deals_tools,
    DEALS_TOOLS,
)
from agent_core.tools.web_search import (
    WebSearchResult,
    web_search,
    search_for_context,
)

__all__ = [
    # RAG Gateway
    "extract_fields",
    "generate_fields_for_question",
    "FieldDefinition",
    "StorageConfig",
    "RetrievalConfig",
    "ExtractFieldsRequest",
    "ExtractFieldsResponse",
    # MCP Client
    "call_mcp_tool",
    "call_domain_tool",
    "mcp_registry",
    "MCPClientRegistry",
    "MCPToolResult",
    # Deals MCP Tools
    "call_deals_tool",
    "get_opportunity_details",
    "list_deals_tools",
    "DealsMCPToolResult",
    "DEALS_TOOLS",
    # Web Search
    "web_search",
    "search_for_context",
    "WebSearchResult",
]
