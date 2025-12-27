"""Ask Handler subgraph for simple Q&A requests."""

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.ask_handler.nodes import (
    gather_context,
    fetch_data,
    generate_answer,
    finalize_ask,
)
from common.logging import get_logger

logger = get_logger(__name__)


def create_ask_handler_subgraph() -> StateGraph:
    """
    Create the ask handler subgraph for Q&A requests.

    This subgraph handles simple question-answering:
    1. Gathers available context (page context, data)
    2. Fetches data from enabled MCP tools
    3. Generates an answer using LLM
    4. Finalizes the response

    Flow:
        gather_context -> fetch_data -> generate_answer -> finalize_ask -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("gather_context", gather_context)
    graph.add_node("fetch_data", fetch_data)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("finalize_ask", finalize_ask)

    # Set entry point
    graph.set_entry_point("gather_context")

    # Add edges - linear flow
    graph.add_edge("gather_context", "fetch_data")
    graph.add_edge("fetch_data", "generate_answer")
    graph.add_edge("generate_answer", "finalize_ask")
    graph.add_edge("finalize_ask", END)

    logger.debug("Created ask handler subgraph")

    return graph
