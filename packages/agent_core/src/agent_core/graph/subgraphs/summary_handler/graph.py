"""Summary handler subgraph definition."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.summary_handler.nodes import generate_summary
from common.logging import get_logger

logger = get_logger(__name__)


def create_summary_handler_subgraph() -> StateGraph:
    """
    Create the summary handler subgraph.

    This subgraph generates an LLM-powered summary for the user at the end
    of agent flows (create, edit, fill).

    Flow:
        generate_summary -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add the summary generation node
    graph.add_node("generate_summary", generate_summary)

    # Set entry point
    graph.set_entry_point("generate_summary")

    # Connect to END
    graph.add_edge("generate_summary", END)

    logger.debug("Created summary handler subgraph")

    return graph
