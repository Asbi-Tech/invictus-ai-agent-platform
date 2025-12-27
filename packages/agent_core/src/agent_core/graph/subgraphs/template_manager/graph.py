"""Template Manager subgraph for template selection and adaptation."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.template_manager.nodes import (
    select_template,
    map_sections,
    adapt_template,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_template_manager_subgraph() -> StateGraph:
    """
    Create the template manager subgraph.

    This subgraph handles document templates:
    1. Selects the appropriate template based on document type
    2. Maps data sources to template sections
    3. Adapts the template for specific requirements

    Flow:
        select_template -> map_sections -> adapt_template -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("select_template", select_template)
    graph.add_node("map_sections", map_sections)
    graph.add_node("adapt_template", adapt_template)

    # Set entry point
    graph.set_entry_point("select_template")

    # Add edges
    graph.add_edge("select_template", "map_sections")
    graph.add_edge("map_sections", "adapt_template")
    graph.add_edge("adapt_template", END)

    logger.debug("Created template manager subgraph")

    return graph
