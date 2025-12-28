"""Confirmation gate nodes for HITL plan approval."""

from datetime import datetime

from common.callback_registry import get_callback_for_state
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState

logger = get_logger(__name__)


def build_human_readable_plan(plan: dict, state: MultiAgentState) -> str:
    """Build a human-readable description of the execution plan."""
    sections = plan.get("sections", [])
    agent_case = state.get("agent_case")
    template_def = state.get("template_definition")

    if agent_case == "fill":
        # For fill mode, describe the fields to fill
        section_names = [s.get("name", s.get("id", "Field")) for s in sections]
        return f"I will fill {len(sections)} field(s): {', '.join(section_names)}."
    elif agent_case == "edit":
        return "I will analyze and prepare edit instructions for the document."
    else:
        # Create mode
        section_names = [s.get("name", s.get("id", "Section")) for s in sections]
        if template_def:
            return f"I will create a document with {len(sections)} sections based on your template: {', '.join(section_names)}."
        else:
            return f"I will create a document with {len(sections)} sections: {', '.join(section_names)}."


async def present_plan(state: MultiAgentState) -> dict:
    """
    Present the execution plan to the user for review.

    This node:
    1. Extracts the plan details
    2. Formats them for user presentation (with human-readable message)
    3. Emits the awaiting_confirmation event with message_for_user structure
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

    section_list = [
        {"id": s["id"], "name": s["name"], "description": s.get("description", "")}
        for s in sections
    ]

    plan_summary = {
        "plan_id": plan.get("plan_id"),
        "sections": section_list,
        "data_sources": list(set(
            req["source"] + (":" + req["domain"] if req.get("domain") else "")
            for req in data_requirements
        )),
        "tools_to_call": [t["tool"] for t in tool_usage],
        "template_strategy": plan.get("template_strategy"),
        "complexity": plan.get("estimated_complexity"),
    }

    # Build human-readable plan description
    human_readable = build_human_readable_plan(plan, state)

    # Build message_for_user structure
    message_for_user = {
        "type": "plan",
        "content": human_readable,
        "plan_summary": {
            "sections": [s["name"] for s in section_list],
            "complexity": plan.get("estimated_complexity", "moderate"),
            "template_strategy": plan.get("template_strategy", "generate_new"),
            "from_template": state.get("template_definition") is not None,
        },
    }

    # Emit awaiting confirmation event with message_for_user
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "awaiting_confirmation",
            {
                "message_for_user": message_for_user,
                "plan": plan_summary,  # Keep for backward compat
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
    if sse_callback := get_callback_for_state(state):
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
    3. Handles modification requests (natural language via plan_modification_input)

    Possible responses:
    - "approved": Continue to data retrieval
    - "modify": Loop back to planning with modification input
    - "cancelled": End the flow
    """
    logger.info("Processing confirmation decision")

    response = state.get("plan_confirmation_response")
    modification_input = state.get("plan_modification_input", "")

    # Emit confirmation received event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "confirmation_received",
            {
                "response": response,
                "has_modification": bool(modification_input),
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
        logger.info(f"Plan modification requested: {modification_input[:100]}...")
        phase_history.append({
            "from_phase": "confirmation",
            "to_phase": "planning",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "User requested plan modifications",
        })

        # Store modification input in working memory for planning to use
        working_memory = dict(state.get("working_memory", {}))
        working_memory["plan_modification_request"] = modification_input

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
    Route based on confirmation response and agent case.

    Used as a conditional edge function in the orchestrator.

    Returns:
        "approved" -> continue to data_retrieval (or fill_handler for fill mode)
        "modify" -> loop back to planning
        "cancelled" -> end the flow
        "fill" -> go to fill_handler for fill mode
    """
    response = state.get("plan_confirmation_response", "cancelled")

    if response == "approved":
        # Check if this is fill mode
        agent_case = state.get("agent_case")
        if agent_case == "fill":
            return "fill"
        return "approved"
    elif response == "modify":
        return "modify"
    else:
        return "cancelled"
