"""Intent Analyzer subgraph for request classification."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.intent_analyzer.nodes import (
    analyze_request,
    detect_entities,
    check_completeness,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_intent_analyzer_subgraph() -> StateGraph:
    """
    Create the intent analyzer subgraph.

    This subgraph analyzes the user's request to:
    1. Classify the request type (ask, create, edit, extend)
    2. Identify the document type if applicable
    3. Detect entities mentioned in the request
    4. Check if all required information is present
    5. Determine if clarification is needed

    Flow:
        analyze_request -> detect_entities -> check_completeness -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("analyze_request", analyze_request)
    graph.add_node("detect_entities", detect_entities)
    graph.add_node("check_completeness", check_completeness)

    # Set entry point
    graph.set_entry_point("analyze_request")

    # Add edges - linear flow
    graph.add_edge("analyze_request", "detect_entities")
    graph.add_edge("detect_entities", "check_completeness")
    graph.add_edge("check_completeness", END)

    logger.debug("Created intent analyzer subgraph")

    return graph
