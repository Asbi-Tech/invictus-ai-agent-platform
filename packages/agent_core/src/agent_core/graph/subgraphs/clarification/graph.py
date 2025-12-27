"""Clarification subgraph for HITL interactions."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.clarification.nodes import (
    generate_questions,
    wait_for_response,
    process_response,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_clarification_subgraph() -> StateGraph:
    """
    Create the clarification subgraph for HITL interactions.

    This subgraph handles the human-in-the-loop clarification flow:
    1. Generates clarification questions based on missing inputs
    2. Pauses execution (INTERRUPT) to wait for user response
    3. Processes the user's responses and updates state

    Flow:
        generate_questions -> wait_for_response (INTERRUPT) -> process_response -> END

    The graph will be compiled with interrupt_before=["wait_for_response"]
    to pause execution at that point.

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("generate_questions", generate_questions)
    graph.add_node("wait_for_response", wait_for_response)
    graph.add_node("process_response", process_response)

    # Set entry point
    graph.set_entry_point("generate_questions")

    # Add edges
    graph.add_edge("generate_questions", "wait_for_response")
    graph.add_edge("wait_for_response", "process_response")
    graph.add_edge("process_response", END)

    logger.debug("Created clarification subgraph")

    return graph


def should_skip_clarification(state: MultiAgentState) -> bool:
    """
    Check if clarification should be skipped.

    Used by the orchestrator to conditionally bypass clarification
    when no questions are needed.

    Args:
        state: Current graph state

    Returns:
        True if clarification should be skipped
    """
    intent_analysis = state.get("intent_analysis") or {}
    return not intent_analysis.get("clarification_needed", False)
