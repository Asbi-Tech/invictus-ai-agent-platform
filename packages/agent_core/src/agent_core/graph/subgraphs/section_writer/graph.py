"""Section Writer subgraph for parallel section generation."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.section_writer.nodes import (
    prepare_sections,
    write_sections,
    collect_sections,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_section_writer_subgraph() -> StateGraph:
    """
    Create the section writer subgraph.

    This subgraph handles parallel section generation:
    1. Prepares sections for writing
    2. Writes all sections in parallel using asyncio.gather
    3. Collects and assembles the final document

    Flow:
        prepare_sections -> write_sections (PARALLEL) -> collect_sections -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("prepare_sections", prepare_sections)
    graph.add_node("write_sections", write_sections)
    graph.add_node("collect_sections", collect_sections)

    # Set entry point
    graph.set_entry_point("prepare_sections")

    # Add edges
    graph.add_edge("prepare_sections", "write_sections")
    graph.add_edge("write_sections", "collect_sections")
    graph.add_edge("collect_sections", END)

    logger.debug("Created section writer subgraph")

    return graph
