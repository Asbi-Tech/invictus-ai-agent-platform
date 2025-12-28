"""Web Agent for internet search via Tavily."""

from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage

from agent_core.tools.web_search import search_for_context
from agent_core.graph.state import MultiAgentState
from common.callback_registry import get_callback_for_state
from common.logging import get_logger

logger = get_logger(__name__)


async def fetch_web_data(state: MultiAgentState) -> dict:
    """
    Fetch data from web search via Tavily.

    This node:
    1. Checks if web search is enabled
    2. Builds search query with context
    3. Calls Tavily web search
    4. Stores results in web_data
    """
    logger.info("Fetching web data")

    tool_results = list(state.get("tool_results", []))
    web_data: dict[str, Any] = dict(state.get("web_data", {}))
    tool_call_count = state.get("tool_call_count", 0)
    tool_policy = state.get("tool_policy", {})

    max_tool_calls = tool_policy.get("max_tool_calls", 10)
    web_search_enabled = tool_policy.get("web_search_enabled", False)

    # Check if web search is enabled
    if not web_search_enabled:
        logger.info("Web search disabled, skipping")
        return {"web_data": web_data, "tool_results": tool_results}

    if tool_call_count >= max_tool_calls:
        logger.info("Max tool calls reached, skipping web search")
        return {"web_data": web_data, "tool_results": tool_results}

    # Get user question
    messages = state.get("messages", [])
    user_question = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_question = str(msg.content)
            break

    if not user_question:
        logger.warning("No user question, skipping web search")
        return {"web_data": web_data, "tool_results": tool_results}

    # Emit fetching event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "fetching_web_data",
            {"message": "Searching the web for relevant information..."},
            "data_retrieval",
        )

    start = datetime.utcnow()

    try:
        # Get opportunity context for better search
        mcp_data = state.get("mcp_data") or {}
        opp_data = mcp_data.get("opportunity", {})
        opportunity_name = opp_data.get("name")
        sector = opp_data.get("sector")

        result = await search_for_context(
            user_question=user_question,
            opportunity_name=opportunity_name,
            sector=sector,
        )

        latency = (datetime.utcnow() - start).total_seconds() * 1000

        tool_results.append({
            "tool_name": "tavily:web_search",
            "input_summary": f"Search: {user_question[:50]}...",
            "output_summary": (
                f"Found {len(result.results)} results"
                if result.success
                else result.error
            ),
            "latency_ms": latency,
            "success": result.success,
            "error": result.error,
            "timestamp": datetime.utcnow().isoformat(),
        })

        if result.success:
            # Store web search results
            web_data["results"] = result.results
            web_data["query"] = user_question
            if result.answer:
                web_data["answer"] = result.answer

            # Create citations from web results
            web_data["citations"] = [
                {
                    "source": "web",
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:200],
                }
                for r in result.results
            ]

            logger.info(
                "Web search completed",
                result_count=len(result.results),
                has_answer=bool(result.answer),
                latency_ms=latency,
            )

            # Emit web data received event
            if sse_callback := get_callback_for_state(state):
                await sse_callback(
                    "web_data_received",
                    {
                        "result_count": len(result.results),
                        "has_answer": bool(result.answer),
                        "latency_ms": latency,
                    },
                    "data_retrieval",
                )

    except Exception as e:
        logger.error("Web search failed", error=str(e))
        tool_results.append({
            "tool_name": "tavily:web_search",
            "input_summary": f"Search: {user_question[:50]}...",
            "output_summary": "",
            "latency_ms": 0,
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        })

    return {
        "web_data": web_data,
        "tool_results": tool_results,
        "tool_call_count": tool_call_count + 1,
    }
