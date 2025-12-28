"""Fill handler subgraph for form filling mode."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.fill_handler.nodes import (
    prepare_fields,
    fill_fields,
    validate_fill,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_fill_handler_subgraph() -> StateGraph:
    """
    Create the fill handler subgraph for form filling mode.

    This subgraph handles template-based field filling:
    1. Prepares fields from template definition
    2. Fills each field using LLM with available data context
    3. Validates all required fields are filled

    Flow:
        prepare_fields -> fill_fields -> validate_fill -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("prepare_fields", prepare_fields)
    graph.add_node("fill_fields", fill_fields)
    graph.add_node("validate_fill", validate_fill)

    # Set entry point
    graph.set_entry_point("prepare_fields")

    # Add edges
    graph.add_edge("prepare_fields", "fill_fields")
    graph.add_edge("fill_fields", "validate_fill")
    graph.add_edge("validate_fill", END)

    logger.debug("Created fill handler subgraph")

    return graph
