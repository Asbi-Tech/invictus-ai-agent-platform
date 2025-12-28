"""Determine action node - routes agent mode to edit or create."""

from typing import Any

from common.callback_registry import get_callback_for_state
from common.logging import get_logger

logger = get_logger(__name__)


async def determine_action(state: dict[str, Any]) -> dict[str, Any]:
    """
    Determine the agent action type (edit vs create).

    This node validates the agent mode request and prepares
    the state for the appropriate action handler.

    Args:
        state: Current graph state

    Returns:
        Updated state with action determination
    """
    agent_case = state.get("agent_case", "create")
    current_artifact = state.get("current_artifact")
    sse_callback = get_callback_for_state(state)

    # Emit thinking event
    if sse_callback:
        if agent_case == "edit":
            artifact_title = current_artifact.get("title", "document") if current_artifact else "document"
            await sse_callback(
                "thinking",
                f"Analyzing '{artifact_title}' for modifications...",
                "determine_action",
            )
        else:
            await sse_callback(
                "thinking",
                "Preparing to generate new content...",
                "determine_action",
            )

    # Validate edit mode has artifact
    if agent_case == "edit" and not current_artifact:
        logger.warning("Edit mode requested but no artifact provided, defaulting to create")
        agent_case = "create"

    # Set the appropriate intent
    if agent_case == "edit":
        current_intent = "edit_artifact"
    else:
        current_intent = "create_artifact"

    logger.info(
        "Determined agent action",
        agent_case=agent_case,
        current_intent=current_intent,
        has_artifact=current_artifact is not None,
    )

    return {
        "agent_case": agent_case,
        "current_intent": current_intent,
    }


def route_agent_action(state: dict[str, Any]) -> str:
    """
    Routing function for conditional edges after determine_action.

    Returns the next node name based on agent_case.

    Args:
        state: Current graph state

    Returns:
        Next node name: "gather_for_edit" or "gather_for_create"
    """
    agent_case = state.get("agent_case", "create")

    if agent_case == "edit":
        return "gather_for_edit"
    return "gather_for_create"
