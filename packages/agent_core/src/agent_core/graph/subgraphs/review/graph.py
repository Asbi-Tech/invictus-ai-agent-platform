"""Review subgraph for coherence checking and validation."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.review.nodes import (
    check_coherence,
    check_citations,
    generate_suggestions,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_review_subgraph() -> StateGraph:
    """
    Create the review subgraph.

    This subgraph reviews the generated document:
    1. Checks coherence and consistency
    2. Validates citations and sources
    3. Generates improvement suggestions

    Flow:
        check_coherence -> check_citations -> generate_suggestions -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("check_coherence", check_coherence)
    graph.add_node("check_citations", check_citations)
    graph.add_node("generate_suggestions", generate_suggestions)

    # Set entry point
    graph.set_entry_point("check_coherence")

    # Add edges
    graph.add_edge("check_coherence", "check_citations")
    graph.add_edge("check_citations", "generate_suggestions")
    graph.add_edge("generate_suggestions", END)

    logger.debug("Created review subgraph")

    return graph
