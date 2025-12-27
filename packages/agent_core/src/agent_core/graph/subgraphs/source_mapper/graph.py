"""Source Mapper subgraph for source attribution."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.source_mapper.nodes import (
    build_ledger,
    map_to_sections,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_source_mapper_subgraph() -> StateGraph:
    """
    Create the source mapper subgraph.

    This subgraph handles source attribution:
    1. Builds a comprehensive source ledger
    2. Maps sources to document sections

    Flow:
        build_ledger -> map_to_sections -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("build_ledger", build_ledger)
    graph.add_node("map_to_sections", map_to_sections)

    # Set entry point
    graph.set_entry_point("build_ledger")

    # Add edges
    graph.add_edge("build_ledger", "map_to_sections")
    graph.add_edge("map_to_sections", END)

    logger.debug("Created source mapper subgraph")

    return graph
