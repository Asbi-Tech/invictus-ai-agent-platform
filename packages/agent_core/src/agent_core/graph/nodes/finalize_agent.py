"""Finalize agent mode response."""

from datetime import datetime
from typing import Any

from common.logging import get_logger

logger = get_logger(__name__)


async def finalize_agent(state: dict[str, Any]) -> dict[str, Any]:
    """
    Finalize the agent mode response.

    This node performs cleanup and logging for agent mode operations.

    Args:
        state: Current graph state

    Returns:
        Updated state with finalized metadata
    """
    agent_case = state.get("agent_case", "create")
    edit_instructions = state.get("edit_instructions", [])
    artifacts = state.get("artifacts", [])
    tool_results = state.get("tool_results", [])
    tool_call_count = state.get("tool_call_count", 0)
    error_count = state.get("error_count", 0)
    sse_callback = state.get("sse_callback")

    # Emit completion status
    if sse_callback:
        if agent_case == "edit":
            await sse_callback(
                "thinking",
                f"Completed with {len(edit_instructions)} edit instructions",
                "finalize_agent",
            )
        else:
            artifact_count = len(artifacts)
            await sse_callback(
                "thinking",
                f"Generated {artifact_count} artifact(s)",
                "finalize_agent",
            )

    # Log completion metrics
    logger.info(
        "Agent mode completed",
        agent_case=agent_case,
        edit_instruction_count=len(edit_instructions),
        artifact_count=len(artifacts),
        tool_call_count=tool_call_count,
        error_count=error_count,
        tool_results_count=len(tool_results),
    )

    # Update metadata
    return {
        "updated_at": datetime.utcnow(),
    }
