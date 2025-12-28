"""MCP Agent for structured data retrieval."""

from datetime import datetime
from typing import Any

from agent_core.tools.deals_mcp import call_deals_tool
from agent_core.graph.state import MultiAgentState
from common.callback_registry import get_callback_for_state
from common.logging import get_logger

logger = get_logger(__name__)


async def fetch_mcp_data(state: MultiAgentState) -> dict:
    """
    Fetch data from MCP tools based on the execution plan.

    This node:
    1. Reads data requirements from the execution plan
    2. Calls appropriate MCP tools (Deals, Clients, etc.)
    3. Stores results in mcp_data keyed by domain
    """
    logger.info("[MCP] Starting MCP data fetch")

    # Emit phase started event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "fetching_mcp_data",
            {"message": "Fetching structured data from MCP..."},
            "data_retrieval",
        )

    tool_results = list(state.get("tool_results", []))
    mcp_data: dict[str, Any] = dict(state.get("mcp_data", {}))
    tool_call_count = state.get("tool_call_count", 0)
    tool_policy = state.get("tool_policy", {})
    page_context = state.get("page_context") or {}
    tenant_id = state.get("tenant_id", "")
    execution_plan = state.get("execution_plan") or {}

    max_tool_calls = tool_policy.get("max_tool_calls", 10)
    enabled_mcps = tool_policy.get("enabled_mcps", ["deals"])

    # Get data requirements from plan
    data_requirements = execution_plan.get("data_requirements", [])
    mcp_requirements = [r for r in data_requirements if r.get("source") == "mcp"]

    # Sort by priority
    mcp_requirements.sort(key=lambda x: x.get("priority", 1))

    # Process Deals MCP calls
    if "deals" in enabled_mcps:
        opportunity_id = page_context.get("opportunity_id")

        if opportunity_id and tool_call_count < max_tool_calls:
            # Get opportunity details
            await _call_deals_tool(
                tool_name="get_opportunity_details",
                arguments={"opportunity_id": opportunity_id, "tenant_id": tenant_id},
                mcp_data=mcp_data,
                tool_results=tool_results,
                sse_callback=get_callback_for_state(state),
            )
            tool_call_count += 1

            # Get prescreening report if available
            if tool_call_count < max_tool_calls:
                await _call_deals_tool(
                    tool_name="get_prescreening_report",
                    arguments={"opportunity_id": opportunity_id, "tenant_id": tenant_id},
                    mcp_data=mcp_data,
                    tool_results=tool_results,
                    sse_callback=get_callback_for_state(state),
                )
                tool_call_count += 1

            # Get investment memo if available
            if tool_call_count < max_tool_calls:
                await _call_deals_tool(
                    tool_name="get_investment_memo",
                    arguments={"opportunity_id": opportunity_id, "tenant_id": tenant_id},
                    mcp_data=mcp_data,
                    tool_results=tool_results,
                    sse_callback=get_callback_for_state(state),
                )
                tool_call_count += 1

            # Get activity log
            if tool_call_count < max_tool_calls:
                await _call_deals_tool(
                    tool_name="get_opportunity_activity",
                    arguments={"opportunity_id": opportunity_id, "tenant_id": tenant_id, "limit": 10},
                    mcp_data=mcp_data,
                    tool_results=tool_results,
                    sse_callback=get_callback_for_state(state),
                )
                tool_call_count += 1

    # Emit MCP data received event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "mcp_data_received",
            {
                "domains_fetched": list(mcp_data.keys()),
                "tool_calls": tool_call_count,
            },
            "data_retrieval",
        )

    logger.info(f"[MCP] Data fetched: {list(mcp_data.keys())} ({tool_call_count} calls)")

    return {
        "mcp_data": mcp_data,
        "tool_results": tool_results,
        "tool_call_count": tool_call_count,
    }


async def _call_deals_tool(
    tool_name: str,
    arguments: dict,
    mcp_data: dict,
    tool_results: list,
    sse_callback: Any,
) -> None:
    """Helper to call a Deals MCP tool and store results."""
    opportunity_id = arguments.get("opportunity_id", "unknown")
    logger.info(f"[MCP] Calling deals:{tool_name} for {opportunity_id}")

    if sse_callback:
        await sse_callback(
            "thinking",
            f"Fetching {tool_name.replace('_', ' ')}...",
            "data_retrieval",
        )

    start = datetime.utcnow()

    try:
        result = await call_deals_tool(tool_name, arguments)
        latency = (datetime.utcnow() - start).total_seconds() * 1000

        tool_results.append({
            "tool_name": f"deals:{tool_name}",
            "input_summary": f"{tool_name} for {arguments.get('opportunity_id', 'unknown')}",
            "output_summary": (
                f"Retrieved: {result.data.get('name', 'data')}"
                if result.success and result.data
                else result.error or "No data"
            ),
            "latency_ms": latency,
            "success": result.success,
            "error": result.error,
            "timestamp": datetime.utcnow().isoformat(),
        })

        if result.success and result.data:
            # Map tool name to data key
            key_map = {
                "get_opportunity_details": "opportunity",
                "get_prescreening_report": "prescreening",
                "get_investment_memo": "investment_memo",
                "get_opportunity_activity": "activity",
            }
            data_key = key_map.get(tool_name, tool_name)
            mcp_data[data_key] = result.data
            logger.info(f"[MCP] deals:{tool_name} succeeded")
        else:
            logger.info(f"[MCP] deals:{tool_name} returned no data")

    except Exception as e:
        logger.error(f"[MCP] deals:{tool_name} failed: {e}")
        tool_results.append({
            "tool_name": f"deals:{tool_name}",
            "input_summary": f"{tool_name} for {arguments.get('opportunity_id', 'unknown')}",
            "output_summary": "",
            "latency_ms": 0,
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        })
