"""Finalize node - prepares final output and updates metadata."""

from datetime import datetime
from typing import Any

from common.logging import get_logger

logger = get_logger(__name__)


async def finalize(state: dict[str, Any]) -> dict[str, Any]:
    """
    Finalize the response and prepare for checkpointing.

    This node:
    - Updates timestamps
    - Logs completion metrics
    - Cleans up temporary working memory

    Args:
        state: The current agent state

    Returns:
        State updates with finalized metadata
    """
    session_id = state.get("session_id", "")
    tool_call_count = state.get("tool_call_count", 0)
    artifacts = state.get("artifacts", [])
    tool_results = state.get("tool_results", [])

    # Calculate success metrics
    successful_tools = sum(1 for tr in tool_results if tr.get("success", False))
    failed_tools = len(tool_results) - successful_tools

    logger.info(
        "Finalizing response",
        session_id=session_id,
        tool_calls=tool_call_count,
        successful_tools=successful_tools,
        failed_tools=failed_tools,
        artifacts=len(artifacts),
    )

    # Return updated timestamp
    return {
        "updated_at": datetime.utcnow(),
    }
