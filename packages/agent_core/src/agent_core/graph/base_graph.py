"""Main LangGraph agent graph."""

from datetime import datetime
from typing import Annotated, Any, Callable, Awaitable, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

# Ask mode nodes
from agent_core.graph.nodes.draft_or_answer import draft_or_answer
from agent_core.graph.nodes.finalize import finalize
from agent_core.graph.nodes.gather_context import gather_context
from agent_core.graph.nodes.ingest_context import ingest_context
from agent_core.graph.nodes.route_intent import route_intent

# Routing nodes
from agent_core.graph.nodes.route_request import route_request, route_after_request_type
from agent_core.graph.nodes.determine_action import determine_action, route_agent_action

# Agent mode nodes
from agent_core.graph.nodes.gather_for_edit import gather_for_edit
from agent_core.graph.nodes.gather_for_create import gather_for_create
from agent_core.graph.nodes.generate_edit_instructions import generate_edit_instructions
from agent_core.graph.nodes.generate_artifact import generate_artifact
from agent_core.graph.nodes.finalize_agent import finalize_agent

from common.logging import get_logger

logger = get_logger(__name__)


# Type alias for SSE callback
SSECallbackType = Callable[[str, str | dict, str | None], Awaitable[None]]


class GraphState(TypedDict, total=False):
    """State schema for the agent graph - extended for ask/agent modes."""

    # Identity
    tenant_id: str
    user_id: str
    session_id: str
    module_id: str

    # Request type (new)
    request_type: str  # "ask" or "agent"
    agent_case: str | None  # "edit" or "create"

    # Conversation - uses add_messages reducer to accumulate messages
    messages: Annotated[list[BaseMessage], add_messages]

    # Additional context (new)
    additional_prompt: str | None

    # Context
    page_context: dict[str, Any] | None
    document_ids: list[str]
    selected_docs: dict[str, Any]

    # Current artifact for edit mode (new)
    current_artifact: dict[str, Any] | None

    # Edit instructions for agent edit mode (new)
    edit_instructions: list[dict[str, Any]]

    # Policy
    tool_policy: dict[str, Any]

    # Working state
    current_intent: str | None
    working_memory: dict[str, Any]
    tool_results: list[dict[str, Any]]

    # Artifacts
    artifacts: list[dict[str, Any]]
    current_artifact_id: str | None

    # HITL
    hitl_pending: dict[str, Any] | None

    # SSE callback (new - excluded from persistence)
    sse_callback: SSECallbackType | None

    # Metadata
    created_at: datetime
    updated_at: datetime
    tool_call_count: int
    error_count: int


def create_agent_graph() -> StateGraph:
    """
    Create the main agent graph with ask/agent mode support.

    Flow for ASK mode:
    ingest_context -> route_request -> route_intent -> gather_context -> draft_or_answer -> finalize -> END

    Flow for AGENT mode:
    ingest_context -> route_request -> determine_action ->
        [EDIT]: gather_for_edit -> generate_edit_instructions -> finalize_agent -> END
        [CREATE]: gather_for_create -> generate_artifact -> finalize_agent -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    # Create the graph with typed state for proper message handling
    graph = StateGraph(GraphState)

    # Add shared nodes
    graph.add_node("ingest_context", ingest_context)
    graph.add_node("route_request", route_request)

    # Add ask mode nodes
    graph.add_node("route_intent", route_intent)
    graph.add_node("gather_context", gather_context)
    graph.add_node("draft_or_answer", draft_or_answer)
    graph.add_node("finalize", finalize)

    # Add agent mode nodes
    graph.add_node("determine_action", determine_action)
    graph.add_node("gather_for_edit", gather_for_edit)
    graph.add_node("gather_for_create", gather_for_create)
    graph.add_node("generate_edit_instructions", generate_edit_instructions)
    graph.add_node("generate_artifact", generate_artifact)
    graph.add_node("finalize_agent", finalize_agent)

    # Set entry point
    graph.set_entry_point("ingest_context")

    # Shared flow: ingest -> route_request
    graph.add_edge("ingest_context", "route_request")

    # Conditional routing after route_request
    graph.add_conditional_edges(
        "route_request",
        route_after_request_type,
        {
            "route_intent": "route_intent",
            "determine_action": "determine_action",
        },
    )

    # Ask mode flow
    graph.add_edge("route_intent", "gather_context")
    graph.add_edge("gather_context", "draft_or_answer")
    graph.add_edge("draft_or_answer", "finalize")
    graph.add_edge("finalize", END)

    # Agent mode conditional routing
    graph.add_conditional_edges(
        "determine_action",
        route_agent_action,
        {
            "gather_for_edit": "gather_for_edit",
            "gather_for_create": "gather_for_create",
        },
    )

    # Edit flow
    graph.add_edge("gather_for_edit", "generate_edit_instructions")
    graph.add_edge("generate_edit_instructions", "finalize_agent")

    # Create flow
    graph.add_edge("gather_for_create", "generate_artifact")
    graph.add_edge("generate_artifact", "finalize_agent")

    # Finalize agent
    graph.add_edge("finalize_agent", END)

    logger.debug("Created agent graph with ask/agent mode support")

    return graph


def create_ask_only_graph() -> StateGraph:
    """
    Create a simplified graph for ask mode only (backward compatible).

    Flow:
    ingest_context -> route_intent -> gather_context -> draft_or_answer -> finalize -> END

    Returns:
        Configured StateGraph (not compiled)
    """
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("ingest_context", ingest_context)
    graph.add_node("route_intent", route_intent)
    graph.add_node("gather_context", gather_context)
    graph.add_node("draft_or_answer", draft_or_answer)
    graph.add_node("finalize", finalize)

    # Add edges (simple linear flow)
    graph.set_entry_point("ingest_context")
    graph.add_edge("ingest_context", "route_intent")
    graph.add_edge("route_intent", "gather_context")
    graph.add_edge("gather_context", "draft_or_answer")
    graph.add_edge("draft_or_answer", "finalize")
    graph.add_edge("finalize", END)

    logger.debug("Created ask-only agent graph")

    return graph


def compile_agent_graph(checkpointer: Any = None) -> Any:
    """
    Compile the graph with optional checkpointer.

    Args:
        checkpointer: Optional LangGraph checkpointer for state persistence

    Returns:
        Compiled graph ready for invocation
    """
    graph = create_agent_graph()

    if checkpointer:
        logger.info("Compiling graph with checkpointer")
        return graph.compile(checkpointer=checkpointer)
    else:
        logger.info("Compiling graph without checkpointer")
        return graph.compile()


# Convenience function for creating a basic compiled agent
def create_agent(checkpointer: Any = None) -> Any:
    """
    Create a compiled agent ready for use.

    Args:
        checkpointer: Optional checkpointer for state persistence

    Returns:
        Compiled agent graph
    """
    return compile_agent_graph(checkpointer)
