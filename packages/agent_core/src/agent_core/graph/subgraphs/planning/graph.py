"""Planning subgraph for execution plan generation."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.planning.nodes import (
    generate_plan,
    validate_plan,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_planning_subgraph() -> StateGraph:
    """
    Create the planning subgraph for execution plan generation.

    This subgraph generates a detailed execution plan:
    1. Analyzes the request and available resources
    2. Generates section outline and data requirements
    3. Plans tool usage and template strategy
    4. Validates the plan for feasibility

    Flow:
        generate_plan -> validate_plan -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("generate_plan", generate_plan)
    graph.add_node("validate_plan", validate_plan)

    # Set entry point
    graph.set_entry_point("generate_plan")

    # Add edges
    graph.add_edge("generate_plan", "validate_plan")
    graph.add_edge("validate_plan", END)

    logger.debug("Created planning subgraph")

    return graph
