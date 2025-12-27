"""Synthesis subgraph for data normalization and insight generation."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.synthesis.nodes import (
    normalize_data,
    generate_insights,
    score_confidence,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_synthesis_subgraph() -> StateGraph:
    """
    Create the synthesis subgraph.

    This subgraph synthesizes data from multiple sources:
    1. Normalizes data from MCP, RAG, and Web
    2. Generates key insights and observations
    3. Identifies data gaps and contradictions
    4. Assigns confidence scores to data points

    Flow:
        normalize_data -> generate_insights -> score_confidence -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("normalize_data", normalize_data)
    graph.add_node("generate_insights", generate_insights)
    graph.add_node("score_confidence", score_confidence)

    # Set entry point
    graph.set_entry_point("normalize_data")

    # Add edges
    graph.add_edge("normalize_data", "generate_insights")
    graph.add_edge("generate_insights", "score_confidence")
    graph.add_edge("score_confidence", END)

    logger.debug("Created synthesis subgraph")

    return graph
