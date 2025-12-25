"""Route request node - determines ask vs agent mode flow."""

from typing import Any

from common.logging import get_logger

logger = get_logger(__name__)


async def route_request(state: dict[str, Any]) -> dict[str, Any]:
    """
    Route the request based on type (ask vs agent).

    This node determines which flow the request should follow:
    - ASK: Conversational flow with RAG + tools
    - AGENT: Artifact creation/editing flow

    Emits THINKING events for streaming feedback.

    Args:
        state: Current graph state

    Returns:
        Updated state with request routing info
    """
    request_type = state.get("request_type", "ask")
    agent_case = state.get("agent_case")
    sse_callback = state.get("sse_callback")

    # Emit thinking event
    if sse_callback:
        if request_type == "agent":
            action = "edit" if agent_case == "edit" else "create"
            await sse_callback(
                "thinking",
                f"Processing {action} request...",
                "route_request",
            )
        else:
            await sse_callback(
                "thinking",
                "Understanding your question...",
                "route_request",
            )

    logger.info(
        "Routing request",
        request_type=request_type,
        agent_case=agent_case,
    )

    # The routing logic is handled by conditional edges in the graph
    # This node just validates and logs the request type
    return {
        "request_type": request_type,
        "agent_case": agent_case,
    }


def route_after_request_type(state: dict[str, Any]) -> str:
    """
    Routing function for conditional edges after route_request.

    Returns the next node name based on request_type.

    Args:
        state: Current graph state

    Returns:
        Next node name: "route_intent" for ask, "determine_action" for agent
    """
    request_type = state.get("request_type", "ask")

    if request_type == "agent":
        return "determine_action"
    return "route_intent"
