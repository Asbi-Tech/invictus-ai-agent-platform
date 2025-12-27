"""Confirmation gate nodes for HITL plan approval."""

from datetime import datetime

from common.logging import get_logger
from agent_core.graph.state import MultiAgentState

logger = get_logger(__name__)


async def present_plan(state: MultiAgentState) -> dict:
    """
    Present the execution plan to the user for review.

    This node:
    1. Extracts the plan details
    2. Formats them for user presentation
    3. Emits the awaiting_confirmation event
    """
    logger.info("Presenting execution plan for confirmation")

    plan = state.get("execution_plan")
    if not plan:
        logger.warning("No execution plan to present")
        return {
            "plan_confirmed": True,  # Skip confirmation if no plan
            "current_phase": "retrieval",
        }

    # Extract plan summary for presentation
    sections = plan.get("sections", [])
    data_requirements = plan.get("data_requirements", [])
    tool_usage = plan.get("tool_usage_plan", [])

    plan_summary = {
        "plan_id": plan.get("plan_id"),
        "sections": [
            {"id": s["id"], "name": s["name"], "description": s["description"]}
            for s in sections
        ],
        "data_sources": list(set(
            req["source"] + (":" + req["domain"] if req.get("domain") else "")
            for req in data_requirements
        )),
        "tools_to_call": [t["tool"] for t in tool_usage],
        "template_strategy": plan.get("template_strategy"),
        "complexity": plan.get("estimated_complexity"),
    }

    # Emit awaiting confirmation event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "awaiting_confirmation",
            {
                "plan": plan_summary,
                "message": "Please review and confirm the execution plan.",
                "options": ["approved", "modify", "cancelled"],
            },
            "confirmation",
        )

    logger.info(f"Plan presented: {len(sections)} sections, awaiting confirmation")

    return {
        "hitl_wait_reason": "confirmation",
        "current_phase": "awaiting_confirmation",
    }


async def await_confirmation(state: MultiAgentState) -> dict:
    """
    Wait point for user confirmation response.

    This node serves as an INTERRUPT POINT in the graph.
    The graph will pause here until the user provides a response
    via the /resume endpoint with confirmation_response.

    The actual waiting is handled by LangGraph's interrupt mechanism.
    """
    logger.info("Waiting for user confirmation")

    # Emit thinking event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "thinking",
            {"message": "Waiting for plan confirmation..."},
            "confirmation",
        )

    # This node returns minimal changes - the graph will be interrupted
    # before this node, and when resumed, the state will contain
    # plan_confirmation_response from the user
    return {
        "hitl_wait_reason": "confirmation",
        "updated_at": datetime.utcnow(),
    }


async def process_decision(state: MultiAgentState) -> dict:
    """
    Process the user's confirmation decision.

    This node:
    1. Reads the confirmation response
    2. Routes to appropriate next phase
    3. Handles modification requests

    Possible responses:
    - "approved": Continue to data retrieval
    - "modify": Loop back to planning with modifications
    - "cancelled": End the flow
    """
    logger.info("Processing confirmation decision")

    response = state.get("plan_confirmation_response")
    modifications = state.get("plan_modifications_requested", [])

    # Emit confirmation received event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "confirmation_received",
            {
                "response": response,
                "modifications_count": len(modifications),
            },
            "confirmation",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))

    if response == "approved":
        logger.info("Plan approved, proceeding to data retrieval")
        phase_history.append({
            "from_phase": "confirmation",
            "to_phase": "retrieval",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "User approved plan",
        })

        return {
            "plan_confirmed": True,
            "hitl_wait_reason": None,
            "phase_history": phase_history,
            "current_phase": "retrieval",
            "updated_at": datetime.utcnow(),
        }

    elif response == "modify":
        logger.info(f"Plan modification requested: {modifications}")
        phase_history.append({
            "from_phase": "confirmation",
            "to_phase": "planning",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"User requested modifications: {modifications}",
        })

        # Store modifications in working memory for planning to use
        working_memory = dict(state.get("working_memory", {}))
        working_memory["plan_modification_request"] = modifications

        return {
            "plan_confirmed": False,
            "hitl_wait_reason": None,
            "working_memory": working_memory,
            "phase_history": phase_history,
            "current_phase": "planning",
            "updated_at": datetime.utcnow(),
        }

    else:  # cancelled or unknown
        logger.info("Plan cancelled by user")
        phase_history.append({
            "from_phase": "confirmation",
            "to_phase": "complete",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "User cancelled execution",
        })

        return {
            "plan_confirmed": False,
            "hitl_wait_reason": None,
            "phase_history": phase_history,
            "current_phase": "complete",
            "updated_at": datetime.utcnow(),
        }


def route_after_confirmation(state: MultiAgentState) -> str:
    """
    Route based on confirmation response.

    Used as a conditional edge function in the orchestrator.

    Returns:
        "approved" -> continue to data_retrieval
        "modify" -> loop back to planning
        "cancelled" -> end the flow
    """
    response = state.get("plan_confirmation_response", "cancelled")

    if response == "approved":
        return "approved"
    elif response == "modify":
        return "modify"
    else:
        return "cancelled"
