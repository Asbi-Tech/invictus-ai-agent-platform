"""Data Retrieval subgraph for MCP, RAG, and Web data gathering."""

from datetime import datetime

from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.data_retrieval.mcp_agent import fetch_mcp_data
from agent_core.graph.subgraphs.data_retrieval.rag_agent import fetch_rag_data
from agent_core.graph.subgraphs.data_retrieval.web_agent import fetch_web_data
from common.logging import get_logger

logger = get_logger(__name__)


async def plan_retrieval(state: MultiAgentState) -> dict:
    """
    Plan data retrieval based on execution plan requirements.

    This node initializes the retrieval phase and emits events.
    """
    logger.info("Planning data retrieval")

    # Emit phase started event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "phase_started",
            {"phase": "retrieval", "message": "Gathering data from sources..."},
            "data_retrieval",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "confirmation",
        "to_phase": "retrieval",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": "Starting data retrieval",
    })

    return {
        "current_phase": "retrieval",
        "phase_history": phase_history,
    }


async def collect_results(state: MultiAgentState) -> dict:
    """
    Collect and consolidate results from all data sources.

    This node aggregates data from MCP, RAG, and Web into working_memory
    for use by downstream nodes.
    """
    logger.info("Collecting retrieval results")

    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}

    # Build consolidated working memory
    working_memory = dict(state.get("working_memory", {}))

    # Add MCP data
    if mcp_data:
        working_memory["opportunity_data"] = mcp_data.get("opportunity")
        working_memory["prescreening_data"] = mcp_data.get("prescreening")
        working_memory["investment_memo_data"] = mcp_data.get("investment_memo")
        working_memory["activity_data"] = mcp_data.get("activity")

    # Add RAG data
    if rag_data:
        working_memory["rag_results"] = rag_data.get("fields", {})
        working_memory["rag_citations"] = rag_data.get("citations", [])

    # Add Web data
    if web_data:
        working_memory["web_search_results"] = web_data.get("results", [])
        working_memory["web_search_answer"] = web_data.get("answer")
        working_memory["web_citations"] = web_data.get("citations", [])

    # Calculate data summary
    data_summary = {
        "mcp_sources": len([k for k, v in mcp_data.items() if v]),
        "rag_fields": len(rag_data.get("fields", {})) if rag_data else 0,
        "web_results": len(web_data.get("results", [])) if web_data else 0,
    }

    # Emit phase completed event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "phase_completed",
            {"phase": "retrieval", **data_summary},
            "data_retrieval",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "retrieval",
        "to_phase": "synthesis",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Data collected: {data_summary}",
    })

    logger.info(f"Data collection complete: {data_summary}")

    return {
        "working_memory": working_memory,
        "phase_history": phase_history,
        "current_phase": "synthesis",
        "updated_at": datetime.utcnow(),
    }


def create_data_retrieval_subgraph() -> StateGraph:
    """
    Create the data retrieval subgraph.

    This subgraph gathers data from multiple sources:
    1. MCP - Structured data from internal systems
    2. RAG - Extracted fields from documents
    3. Web - Internet search results

    Flow:
        plan_retrieval -> fetch_mcp_data -> fetch_rag_data -> fetch_web_data -> collect_results -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # Add nodes
    graph.add_node("plan_retrieval", plan_retrieval)
    graph.add_node("fetch_mcp_data", fetch_mcp_data)
    graph.add_node("fetch_rag_data", fetch_rag_data)
    graph.add_node("fetch_web_data", fetch_web_data)
    graph.add_node("collect_results", collect_results)

    # Set entry point
    graph.set_entry_point("plan_retrieval")

    # Add edges - sequential flow
    # Note: These could be parallelized in the future, but sequential is simpler
    # and allows MCP data to inform RAG/Web queries
    graph.add_edge("plan_retrieval", "fetch_mcp_data")
    graph.add_edge("fetch_mcp_data", "fetch_rag_data")
    graph.add_edge("fetch_rag_data", "fetch_web_data")
    graph.add_edge("fetch_web_data", "collect_results")
    graph.add_edge("collect_results", END)

    logger.debug("Created data retrieval subgraph")

    return graph
