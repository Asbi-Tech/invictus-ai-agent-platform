"""Multi-Agent Orchestrator Graph.

This module defines the main orchestrator graph that composes all subgraphs
into a unified multi-agent system with HITL capabilities.
"""

from datetime import datetime
from typing import Any, Callable, Awaitable

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from agent_core.graph.state import MultiAgentState
from agent_core.graph.subgraphs.intent_analyzer import create_intent_analyzer_subgraph
from agent_core.graph.subgraphs.clarification import create_clarification_subgraph
from agent_core.graph.subgraphs.planning import create_planning_subgraph
from agent_core.graph.subgraphs.confirmation import create_confirmation_subgraph
from agent_core.graph.subgraphs.data_retrieval import create_data_retrieval_subgraph
from agent_core.graph.subgraphs.synthesis import create_synthesis_subgraph
from agent_core.graph.subgraphs.template_manager import create_template_manager_subgraph
from agent_core.graph.subgraphs.section_writer import create_section_writer_subgraph
from agent_core.graph.subgraphs.review import create_review_subgraph
from agent_core.graph.subgraphs.source_mapper import create_source_mapper_subgraph
from agent_core.graph.subgraphs.ask_handler import create_ask_handler_subgraph
from common.logging import get_logger

logger = get_logger(__name__)


# Type alias for SSE callback
SSECallbackType = Callable[[str, str | dict, str | None], Awaitable[None]]


# ============================================================
# Entry and Exit Nodes
# ============================================================


async def ingest_context(state: MultiAgentState) -> dict:
    """
    Entry point node - validates and initializes state.

    This node:
    1. Validates required fields
    2. Initializes state defaults
    3. Emits initial processing event
    """
    logger.info("Ingesting context for multi-agent flow")

    # Validate required fields
    tenant_id = state.get("tenant_id")
    user_id = state.get("user_id")

    if not tenant_id or not user_id:
        raise ValueError("tenant_id and user_id are required")

    # Emit initial event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "status",
            {"status": "processing", "message": "Starting multi-agent processing..."},
            "orchestrator",
        )

    # Initialize phase tracking
    now = datetime.utcnow()

    return {
        "current_phase": "intent",
        "phase_history": [{
            "from_phase": "start",
            "to_phase": "intent",
            "timestamp": now.isoformat(),
            "reason": "Processing started",
        }],
        "created_at": now,
        "updated_at": now,
        "tool_call_count": 0,
        "error_count": 0,
        "clarification_pending": False,
        "plan_confirmed": False,
        "mcp_data": {},
        "rag_data": {},
        "web_data": {},
    }


async def finalize(state: MultiAgentState) -> dict:
    """
    Final node - completes processing and prepares response.

    This node:
    1. Summarizes execution
    2. Emits final event
    3. Prepares response message
    """
    logger.info("Finalizing multi-agent processing")

    artifacts = state.get("artifacts", [])
    review_result = state.get("review_result") or {}
    source_ledger = state.get("source_ledger") or {}
    tool_results = state.get("tool_results", [])

    # Build summary message
    if artifacts:
        artifact = artifacts[-1]
        message = f"Generated {artifact.get('artifact_type', 'document')}: {artifact.get('title', 'Untitled')}"

        # Add review summary
        if review_result:
            score = review_result.get("coherence_score", 0)
            issues = len(review_result.get("issues", []))
            message += f"\n\nQuality score: {score:.0%}"
            if issues > 0:
                message += f" ({issues} issues noted)"
    else:
        message = "Processing complete."

    # Create AI message
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=message))

    # Emit final event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "final",
            {
                "session_id": state.get("session_id"),
                "type": state.get("request_type", "agent"),
                "artifact_count": len(artifacts),
                "tool_call_count": len(tool_results),
                "sources_count": len(source_ledger.get("sources", [])),
            },
            "orchestrator",
        )

    logger.info(
        f"Processing complete: {len(artifacts)} artifacts, "
        f"{len(tool_results)} tool calls"
    )

    return {
        "messages": messages,
        "current_phase": "complete",
        "updated_at": datetime.utcnow(),
    }


# ============================================================
# Routing Functions
# ============================================================


def route_after_intent(state: MultiAgentState) -> str:
    """Route after intent analysis based on request type and clarification needs."""
    intent = state.get("intent_analysis") or {}
    request_type = intent.get("request_type", "ask")

    # Ask mode goes directly to ask_handler (no planning/confirmation needed)
    if request_type == "ask":
        return "ask_handler"

    # Agent mode (create/edit/extend) needs planning flow
    if intent.get("clarification_needed", False):
        return "clarification"

    return "planning"


def route_after_confirmation(state: MultiAgentState) -> str:
    """Route based on confirmation response."""
    response = state.get("plan_confirmation_response", "cancelled")

    if response == "approved":
        return "data_retrieval"
    elif response == "modify":
        return "planning"
    else:
        return "finalize"


# ============================================================
# Graph Construction
# ============================================================


def create_multi_agent_graph() -> StateGraph:
    """
    Create the main multi-agent orchestrator graph.

    This graph composes all subgraphs into a unified flow:

    Flow (Ask Mode - Q&A):
        ingest_context
            -> intent_analyzer
            -> ask_handler -> END

    Flow (Agent Mode - Create/Edit):
        ingest_context
            -> intent_analyzer
            -> [conditional] clarification (if needed)
            -> planning
            -> confirmation_gate (INTERRUPT)
            -> [conditional]
                -> approved: data_retrieval -> synthesis -> template_manager
                            -> section_writers -> review -> source_mapper -> finalize
                -> modify: -> planning (loop)
                -> cancelled: -> finalize

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(MultiAgentState)

    # === Add Entry/Exit Nodes ===
    graph.add_node("ingest_context", ingest_context)
    graph.add_node("finalize", finalize)

    # === Add Subgraphs as Nodes ===
    # Each subgraph is compiled and added as a node
    graph.add_node("intent_analyzer", create_intent_analyzer_subgraph().compile())
    graph.add_node("ask_handler", create_ask_handler_subgraph().compile())  # Ask mode handler
    graph.add_node("clarification", create_clarification_subgraph().compile())
    graph.add_node("planning", create_planning_subgraph().compile())
    graph.add_node("confirmation_gate", create_confirmation_subgraph().compile())
    graph.add_node("data_retrieval", create_data_retrieval_subgraph().compile())
    graph.add_node("synthesis", create_synthesis_subgraph().compile())
    graph.add_node("template_manager", create_template_manager_subgraph().compile())
    graph.add_node("section_writers", create_section_writer_subgraph().compile())
    graph.add_node("review", create_review_subgraph().compile())
    graph.add_node("source_mapper", create_source_mapper_subgraph().compile())

    # === Set Entry Point ===
    graph.set_entry_point("ingest_context")

    # === Add Edges ===

    # Entry -> Intent Analysis
    graph.add_edge("ingest_context", "intent_analyzer")

    # Intent Analysis -> Ask Handler, Clarification, or Planning
    graph.add_conditional_edges(
        "intent_analyzer",
        route_after_intent,
        {
            "ask_handler": "ask_handler",  # Ask mode - direct to answer
            "clarification": "clarification",  # Agent mode - needs clarification
            "planning": "planning",  # Agent mode - ready to plan
        },
    )

    # Ask Handler -> END (direct path for Q&A, answer already in messages)
    graph.add_edge("ask_handler", END)

    # Clarification -> Planning
    graph.add_edge("clarification", "planning")

    # Planning -> Confirmation
    graph.add_edge("planning", "confirmation_gate")

    # Confirmation -> Data Retrieval, Planning (loop), or Finalize
    graph.add_conditional_edges(
        "confirmation_gate",
        route_after_confirmation,
        {
            "data_retrieval": "data_retrieval",
            "planning": "planning",
            "finalize": "finalize",
        },
    )

    # Data Retrieval -> Synthesis -> Template -> Sections -> Review -> Sources -> Finalize
    graph.add_edge("data_retrieval", "synthesis")
    graph.add_edge("synthesis", "template_manager")
    graph.add_edge("template_manager", "section_writers")
    graph.add_edge("section_writers", "review")
    graph.add_edge("review", "source_mapper")
    graph.add_edge("source_mapper", "finalize")

    # Finalize -> END
    graph.add_edge("finalize", END)

    logger.debug("Created multi-agent orchestrator graph")

    return graph


def compile_multi_agent_graph(checkpointer: Any = None) -> Any:
    """
    Compile the multi-agent graph with HITL interrupt points.

    Args:
        checkpointer: Optional LangGraph checkpointer for state persistence

    Returns:
        Compiled graph ready for invocation
    """
    graph = create_multi_agent_graph()

    # Define interrupt points for HITL
    # The graph will pause BEFORE these nodes
    interrupt_nodes = [
        "clarification",      # Pause for clarification questions
        "confirmation_gate",  # Pause for plan approval
    ]

    if checkpointer:
        logger.info("Compiling multi-agent graph with checkpointer and interrupts")
        return graph.compile(
            checkpointer=checkpointer,
            interrupt_before=interrupt_nodes,
        )
    else:
        logger.info("Compiling multi-agent graph without checkpointer")
        return graph.compile(
            interrupt_before=interrupt_nodes,
        )
