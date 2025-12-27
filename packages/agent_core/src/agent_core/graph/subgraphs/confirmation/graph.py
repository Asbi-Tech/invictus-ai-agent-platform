"""Confirmation gate subgraph for HITL plan approval."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.confirmation.nodes import (
    present_plan,
    await_confirmation,
    process_decision,
    route_after_confirmation,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_confirmation_subgraph() -> StateGraph:
    """
    Create the confirmation gate subgraph for HITL plan approval.

    This subgraph handles the mandatory plan confirmation:
    1. Presents the execution plan to the user
    2. Pauses execution (INTERRUPT) to wait for user decision
    3. Processes the decision and routes accordingly

    Flow:
        present_plan -> await_confirmation (INTERRUPT) -> process_decision -> END

    The graph will be compiled with interrupt_before=["await_confirmation"]
    to pause execution at that point.

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("present_plan", present_plan)
    graph.add_node("await_confirmation", await_confirmation)
    graph.add_node("process_decision", process_decision)

    # Set entry point
    graph.set_entry_point("present_plan")

    # Add edges
    graph.add_edge("present_plan", "await_confirmation")
    graph.add_edge("await_confirmation", "process_decision")
    graph.add_edge("process_decision", END)

    logger.debug("Created confirmation subgraph")

    return graph
