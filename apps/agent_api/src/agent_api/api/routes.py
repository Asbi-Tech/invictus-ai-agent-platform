"""API routes for the Copilot service."""

import asyncio
from asyncio import Queue
from datetime import datetime
from typing import AsyncGenerator, Callable, Awaitable
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from sse_starlette.sse import EventSourceResponse

from agent_api.api.schemas import (
    AgentCase,
    AgentMessageForUser,
    AgentOutputForSystem,
    ArtifactResponse,
    ChatResponse,
    EditInstruction,
    EditOperation,
    HITLStatus,
    RequestType,
    SSEEvent,
    SSEEventType,
    ToolResultResponse,
    UnifiedChatRequest,
)
from agent_core.graph import compile_multi_agent_graph
from agent_core.memory import CosmosDBCheckpointer, ArtifactStorage
from common.callback_registry import register_sse_callback
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])

# Initialize checkpointer and artifact storage lazily to avoid connection errors at import time
_checkpointer = None
_agent = None
_artifact_storage = None


def get_checkpointer() -> CosmosDBCheckpointer | None:
    """Get or create the Cosmos DB checkpointer."""
    global _checkpointer
    if _checkpointer is None:
        try:
            _checkpointer = CosmosDBCheckpointer(
                endpoint=settings.cosmos_endpoint,
                key=settings.cosmos_key,
                database_name=settings.cosmos_database_name,
                container_name=settings.cosmos_checkpoints_container,
            )
        except Exception as e:
            logger.warning(
                "Failed to initialize Cosmos DB checkpointer, running without persistence",
                error=str(e),
            )
            return None
    return _checkpointer


def get_agent():
    """Get or create the compiled multi-agent graph."""
    global _agent
    if _agent is None:
        checkpointer = get_checkpointer()
        _agent = compile_multi_agent_graph(checkpointer=checkpointer)
    return _agent


def get_artifact_storage() -> ArtifactStorage | None:
    """Get or create the artifact storage instance."""
    global _artifact_storage
    if _artifact_storage is None:
        try:
            _artifact_storage = ArtifactStorage(
                endpoint=settings.cosmos_endpoint,
                key=settings.cosmos_key,
                database_name=settings.cosmos_database_name,
                container_name=settings.cosmos_artifacts_container,
            )
        except Exception as e:
            logger.warning(
                "Failed to initialize artifact storage, artifact persistence disabled",
                error=str(e),
            )
            return None
    return _artifact_storage


# Type alias for SSE callback
SSECallbackType = Callable[[str, str | dict, str | None], Awaitable[None]]


def create_sse_callback(queue: Queue) -> SSECallbackType:
    """Create an SSE callback that puts events into a queue."""

    # Map event type strings to SSEEventType enum
    EVENT_TYPE_MAP = {
        # Status events
        "thinking": SSEEventType.THINKING,
        "status": SSEEventType.STATUS,
        "final": SSEEventType.FINAL,
        "error": SSEEventType.ERROR,
        # Tool events
        "tool_call_start": SSEEventType.TOOL_CALL_START,
        "tool_call_result": SSEEventType.TOOL_CALL_RESULT,
        # Response streaming
        "assistant_delta": SSEEventType.ASSISTANT_DELTA,
        "artifact_update": SSEEventType.ARTIFACT_UPDATE,
        "edit_instruction": SSEEventType.EDIT_INSTRUCTION,
        # HITL events
        "hitl_request": SSEEventType.HITL_REQUEST,
        "clarification_required": SSEEventType.CLARIFICATION_REQUIRED,
        "clarification_resolved": SSEEventType.CLARIFICATION_RESOLVED,
        "plan_generated": SSEEventType.PLAN_GENERATED,
        "awaiting_confirmation": SSEEventType.AWAITING_CONFIRMATION,
        "confirmation_received": SSEEventType.CONFIRMATION_RECEIVED,
        # Phase lifecycle events
        "phase_started": SSEEventType.PHASE_STARTED,
        "phase_completed": SSEEventType.PHASE_COMPLETED,
        "intent_detected": SSEEventType.INTENT_DETECTED,
        "entities_detected": SSEEventType.ENTITIES_DETECTED,
        # Data retrieval events
        "fetching_mcp_data": SSEEventType.FETCHING_MCP_DATA,
        "mcp_data_received": SSEEventType.MCP_DATA_RECEIVED,
        "fetching_rag_data": SSEEventType.FETCHING_RAG_DATA,
        "rag_data_received": SSEEventType.RAG_DATA_RECEIVED,
        "fetching_web_data": SSEEventType.FETCHING_WEB_DATA,
        "web_data_received": SSEEventType.WEB_DATA_RECEIVED,
        # Synthesis events
        "synthesis_started": SSEEventType.SYNTHESIS_STARTED,
        "insight_generated": SSEEventType.INSIGHT_GENERATED,
        "synthesis_completed": SSEEventType.SYNTHESIS_COMPLETED,
        # Template events
        "template_selected": SSEEventType.TEMPLATE_SELECTED,
        "template_adapted": SSEEventType.TEMPLATE_ADAPTED,
        # Section generation events
        "section_started": SSEEventType.SECTION_STARTED,
        "section_progress": SSEEventType.SECTION_PROGRESS,
        "section_completed": SSEEventType.SECTION_COMPLETED,
        # Review events
        "review_started": SSEEventType.REVIEW_STARTED,
        "review_issue_found": SSEEventType.REVIEW_ISSUE_FOUND,
        "review_completed": SSEEventType.REVIEW_COMPLETED,
        # Source attribution events
        "source_mapped": SSEEventType.SOURCE_MAPPED,
    }

    async def callback(event_type: str, data: str | dict, node_name: str | None = None):
        # Map string event type to enum
        sse_event_type = EVENT_TYPE_MAP.get(event_type, SSEEventType.STATUS)

        # Build event data
        if isinstance(data, str):
            event_data = {"message": data}
        else:
            event_data = dict(data)

        # Add node name if provided
        if node_name:
            event_data["node"] = node_name

        event = SSEEvent(event_type=sse_event_type, data=event_data)
        await queue.put(event)

    return callback


def build_initial_state(
    request: UnifiedChatRequest,
    sse_callback: SSECallbackType | None = None,
) -> dict:
    """Build initial agent state from request."""
    session_id = request.session_id or str(uuid4())

    # Register callback in registry for resume access
    # (callbacks can't be serialized in checkpoints)
    if sse_callback:
        register_sse_callback(session_id, sse_callback)

    state = {
        "tenant_id": request.tenant_id,
        "user_id": request.user_id,
        "module_id": request.module_id,
        "session_id": session_id,
        "messages": [HumanMessage(content=request.message)],
        "request_type": request.type.value,
        "agent_case": request.agent_case.value if request.agent_case else None,
        "additional_prompt": request.additional_prompt,
        "document_ids": request.document_ids,
        "tool_policy": {
            "web_search_enabled": request.web_search_enabled,
            "rag_enabled": True,
            "enabled_mcps": request.enabled_mcps,
            "max_tool_calls": 10,
        },
        "tool_results": [],
        "working_memory": {},
        "edit_instructions": [],
        "artifacts": [],
        "tool_call_count": 0,
        "error_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "sse_callback": sse_callback,  # Still set for initial run (works fine)
    }

    # Add page context if provided
    if request.page_context:
        state["page_context"] = {
            "module_id": request.page_context.module_id,
            "screen_name": request.page_context.screen_name,
            "opportunity_id": request.page_context.opportunity_id,
            "opportunity_name": request.page_context.opportunity_name,
            "screen_highlights": request.page_context.screen_highlights,
            "additional_context": request.page_context.additional_context,
        }

    # Add current artifact for edit mode
    # If artifact_id is provided but content is empty, try to fetch from storage
    if request.current_artifact:
        artifact_input = request.current_artifact

        # If content is empty but artifact_id is provided, fetch from storage
        if not artifact_input.content and artifact_input.artifact_id:
            artifact_storage = get_artifact_storage()
            if artifact_storage:
                stored_artifact = artifact_storage.get_artifact(
                    tenant_id=request.tenant_id,
                    artifact_id=artifact_input.artifact_id,
                )
                if stored_artifact:
                    logger.info(
                        "Fetched artifact from storage",
                        artifact_id=artifact_input.artifact_id,
                    )
                    state["current_artifact"] = {
                        "artifact_id": stored_artifact["artifact_id"],
                        "artifact_type": stored_artifact.get("artifact_type", "document"),
                        "title": stored_artifact.get("title", ""),
                        "content": stored_artifact.get("content", ""),
                        "metadata": stored_artifact.get("metadata", {}),
                    }
                else:
                    # Artifact not found in storage - will trigger clarification
                    logger.warning(
                        "Artifact not found in storage",
                        artifact_id=artifact_input.artifact_id,
                    )
                    state["current_artifact"] = {
                        "artifact_id": artifact_input.artifact_id,
                        "artifact_type": artifact_input.artifact_type,
                        "title": artifact_input.title,
                        "content": "",  # Empty content will trigger clarification
                        "metadata": artifact_input.metadata,
                    }
            else:
                # No storage available - use provided data as-is
                state["current_artifact"] = {
                    "artifact_id": artifact_input.artifact_id,
                    "artifact_type": artifact_input.artifact_type,
                    "title": artifact_input.title,
                    "content": artifact_input.content,
                    "metadata": artifact_input.metadata,
                }
        else:
            # Content provided in request - use as-is
            state["current_artifact"] = {
                "artifact_id": artifact_input.artifact_id,
                "artifact_type": artifact_input.artifact_type,
                "title": artifact_input.title,
                "content": artifact_input.content,
                "metadata": artifact_input.metadata,
            }

    # Handle selected_docs (new way) or document_ids (deprecated)
    if request.selected_docs:
        state["selected_docs"] = {
            "doc_ids": request.selected_docs.doc_ids,
            "doc_sets": request.selected_docs.doc_sets,
            "storage": {
                "account_url": request.selected_docs.storage.account_url,
                "filesystem": request.selected_docs.storage.filesystem,
                "base_prefix": request.selected_docs.storage.base_prefix,
            } if request.selected_docs.storage else None,
        }
    elif request.document_ids:
        # Backward compat: document_ids without storage (RAG won't work without storage)
        state["selected_docs"] = {"doc_ids": request.document_ids}

    # Handle template for create/fill modes
    if request.template:
        state["template_definition"] = request.template.model_dump()

    # Handle fill mode
    if request.agent_case and request.agent_case.value == "fill":
        state["fill_mode_active"] = True
        # Extract field keys from template if provided
        if request.template:
            state["fields_to_fill"] = list(request.template.fields.keys())
        state["filled_fields"] = {}

    return state


@router.post("/chat", response_model=ChatResponse)
async def chat(request: UnifiedChatRequest) -> ChatResponse:
    """
    Non-streaming chat endpoint for Ask mode only.

    This endpoint supports conversational Q&A with RAG + MCP tools.
    For Agent mode (create/edit), use the /stream endpoint instead.
    """
    # Reject agent mode requests - must use /stream endpoint
    if request.type == RequestType.AGENT:
        raise HTTPException(
            status_code=400,
            detail="Agent mode is only available via the /stream endpoint. "
            "Use POST /v1/copilot/stream for agent mode requests.",
        )

    try:
        initial_state = build_initial_state(request)
        session_id = initial_state["session_id"]

        config = {"configurable": {"thread_id": session_id}}

        logger.info(
            "Processing chat request",
            session_id=session_id,
            tenant_id=request.tenant_id,
        )

        # Run the graph
        agent = get_agent()
        result = await agent.ainvoke(initial_state, config=config)

        # Extract the response message
        messages = result.get("messages", [])
        last_message = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_message = str(msg.content)
                break

        if not last_message:
            last_message = "I couldn't generate a response. Please try again."

        # Build tool results response
        tool_results = [
            ToolResultResponse(
                tool_name=tr.get("tool_name", ""),
                input_summary=tr.get("input_summary", ""),
                output_summary=tr.get("output_summary", ""),
                latency_ms=tr.get("latency_ms", 0),
                success=tr.get("success", False),
                citations=tr.get("citations", []),
            )
            for tr in result.get("tool_results", [])
        ]

        # Collect citations
        citations = []
        for tr in tool_results:
            citations.extend(tr.citations)

        # Build response
        response = ChatResponse(
            session_id=session_id,
            message=last_message,
            tool_results=tool_results,
            citations=citations,
            intent=result.get("current_intent"),
        )

        logger.info(
            "Chat request completed",
            session_id=session_id,
            response_length=len(last_message),
            tool_calls=len(tool_results),
        )

        return response

    except Exception as e:
        import traceback

        error_detail = str(e) or traceback.format_exc()
        logger.error("Chat error", error=error_detail, traceback=traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_detail)


async def get_paused_session_state(session_id: str) -> dict | None:
    """
    Check if a session exists and is paused, returning its state if so.

    Returns the checkpoint state if session is paused, None otherwise.
    """
    if not session_id:
        return None

    checkpointer = get_checkpointer()
    if not checkpointer:
        return None

    config = {"configurable": {"thread_id": session_id}}
    try:
        checkpoint = await checkpointer.aget(config)
        if not checkpoint:
            return None

        state = checkpoint.get("channel_values", {})

        # Check if session is paused (has an active HITL wait reason)
        hitl_wait_reason = state.get("hitl_wait_reason")
        if hitl_wait_reason in ["clarification", "confirmation"]:
            return state

        # Check for clarification pending (interrupt happens BEFORE clarification node)
        # This catches the case where intent analysis completed and flagged clarification_needed
        intent_analysis = state.get("intent_analysis") or {}
        if state.get("clarification_pending") or intent_analysis.get("clarification_needed"):
            # Verify we're past intent analysis
            current_phase = state.get("current_phase", "")
            if current_phase in ["intent", "clarification"]:
                return state

        # Also check for plan pending confirmation
        if state.get("execution_plan") and not state.get("plan_confirmed"):
            current_phase = state.get("current_phase", "")
            if current_phase in ["confirmation", "awaiting_confirmation", "planning"]:
                return state

        return None
    except Exception as e:
        logger.warning(f"Failed to get paused session state: {e}")
        return None


def check_hitl_interrupt(state: dict) -> dict | None:
    """
    Check if the graph has paused at an HITL interrupt point.

    LangGraph's interrupt_before pauses BEFORE the node runs, so:
    - For clarification: clarification_pending is True but questions not yet generated
    - For confirmation: execution_plan exists but plan_confirmed is False

    Returns interrupt info dict if interrupted, None otherwise.
    """
    current_phase = state.get("current_phase", "")
    hitl_wait_reason = state.get("hitl_wait_reason")

    # Method 1: Check explicit hitl_wait_reason (if node partially ran)
    if hitl_wait_reason == "clarification":
        questions = state.get("clarification_questions", [])
        return {
            "interrupt_type": "clarification",
            "questions": questions,
            "missing_inputs": state.get("intent_analysis", {}).get("missing_inputs", []),
            "session_id": state.get("session_id"),
        }

    if hitl_wait_reason == "confirmation":
        execution_plan = state.get("execution_plan", {})
        return {
            "interrupt_type": "confirmation",
            "plan": execution_plan,
            "session_id": state.get("session_id"),
        }

    # Method 2: Detect interrupt from state (interrupt_before means node didn't run)
    # Clarification interrupt: clarification_pending is True
    # BUT: Skip for "ask" requests - they should always attempt to answer directly
    request_type = state.get("intent_analysis", {}).get("request_type", "ask")
    if request_type != "ask":
        if state.get("clarification_pending") and not state.get("clarification_input"):
            return {
                "interrupt_type": "clarification",
                "questions": state.get("clarification_questions", []),
                "missing_inputs": state.get("intent_analysis", {}).get("missing_inputs", []),
                "session_id": state.get("session_id"),
            }

    # Confirmation interrupt: execution_plan exists but not confirmed
    execution_plan = state.get("execution_plan")
    if execution_plan and not state.get("plan_confirmed"):
        # Check we're at the right phase (confirmation or just completed planning)
        if current_phase in ["confirmation", "awaiting_confirmation", "planning"]:
            return {
                "interrupt_type": "confirmation",
                "plan": execution_plan,
                "session_id": state.get("session_id"),
            }

    return None


async def stream_with_hitl(
    agent,
    initial_state: dict,
    config: dict,
    event_queue: Queue,
    request: UnifiedChatRequest,
) -> AsyncGenerator[str, None]:
    """
    Stream graph execution with HITL interrupt handling.

    Yields SSE events and detects when graph pauses for user input.
    """
    session_id = initial_state["session_id"]

    # Emit initial status
    yield SSEEvent(
        event_type=SSEEventType.STATUS,
        data={
            "status": "processing",
            "session_id": session_id,
            "type": request.type.value,
        },
    ).to_sse_format()

    # Run graph in background task
    async def run_graph():
        return await agent.ainvoke(initial_state, config=config)

    graph_task = asyncio.create_task(run_graph())

    # Stream events from queue while graph is running
    while not graph_task.done():
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
            yield event.to_sse_format()
        except asyncio.TimeoutError:
            continue

    # Get final result
    result = await graph_task

    # Drain any remaining events
    while not event_queue.empty():
        event = event_queue.get_nowait()
        yield event.to_sse_format()

    # Check for HITL interrupt
    interrupt_info = check_hitl_interrupt(result)
    if interrupt_info:
        # Graph paused - emit appropriate HITL event with message_for_user structure
        if interrupt_info["interrupt_type"] == "clarification":
            questions = interrupt_info.get("questions", [])
            yield SSEEvent(
                event_type=SSEEventType.CLARIFICATION_REQUIRED,
                data={
                    "session_id": session_id,
                    "message_for_user": {
                        "type": "clarification",
                        "content": "I need some additional information to proceed. Please answer the following questions.",
                        "questions": questions,
                    },
                    "questions": questions,  # Keep for backward compat
                    "missing_inputs": interrupt_info.get("missing_inputs", []),
                },
            ).to_sse_format()
        elif interrupt_info["interrupt_type"] == "confirmation":
            plan = interrupt_info.get("plan", {})
            # Build human-readable plan summary
            sections = plan.get("sections", [])
            section_names = [s.get("name", s.get("id", "Section")) for s in sections]
            plan_description = f"I will create a document with {len(sections)} sections: {', '.join(section_names)}." if sections else "I have prepared an execution plan."

            yield SSEEvent(
                event_type=SSEEventType.AWAITING_CONFIRMATION,
                data={
                    "session_id": session_id,
                    "message_for_user": {
                        "type": "plan",
                        "content": plan_description,
                        "plan_summary": {
                            "sections": section_names,
                            "complexity": plan.get("estimated_complexity", "moderate"),
                            "template_strategy": plan.get("template_strategy", "generate_new"),
                        },
                    },
                    "plan": plan,  # Keep for backward compat
                    "options": ["approved", "modify", "cancelled"],
                },
            ).to_sse_format()

        # Emit paused status (note: resume is now via /stream with session_id)
        yield SSEEvent(
            event_type=SSEEventType.STATUS,
            data={
                "status": "paused",
                "session_id": session_id,
                "interrupt_type": interrupt_info["interrupt_type"],
                "resume_instructions": "Send another request to /v1/copilot/stream with the same session_id, confirmation_response ('clarified', 'approved', 'modify', or 'cancelled'), and your input in the message field.",
            },
        ).to_sse_format()

        logger.info(
            "Graph paused for HITL",
            session_id=session_id,
            interrupt_type=interrupt_info["interrupt_type"],
        )
        return

    # No interrupt - emit tool results
    for tr in result.get("tool_results", []):
        yield SSEEvent(
            event_type=SSEEventType.TOOL_CALL_RESULT,
            data={
                "tool_name": tr.get("tool_name", ""),
                "success": tr.get("success", False),
                "latency_ms": tr.get("latency_ms", 0),
            },
        ).to_sse_format()

    # Handle response based on request type
    artifact_data = None
    edit_instructions_data = None
    filled_template_data = None
    last_message = ""

    if request.type == RequestType.AGENT:
        if request.agent_case == AgentCase.CREATE:
            # Stream artifact
            artifacts = result.get("artifacts", [])
            if artifacts:
                artifact_data = artifacts[-1]
                yield SSEEvent(
                    event_type=SSEEventType.ARTIFACT_UPDATE,
                    data=artifact_data,
                ).to_sse_format()
        elif request.agent_case == AgentCase.EDIT:
            # Stream edit instructions
            edit_instructions_data = result.get("edit_instructions", [])
            for instruction in edit_instructions_data:
                yield SSEEvent(
                    event_type=SSEEventType.EDIT_INSTRUCTION,
                    data=instruction,
                ).to_sse_format()
        elif request.agent_case == AgentCase.FILL:
            # Get filled template result
            filled_template_data = result.get("filled_fields", {})
            # Emit a status event for fill completion
            yield SSEEvent(
                event_type=SSEEventType.PHASE_COMPLETED,
                data={
                    "phase": "fill",
                    "fields_filled": len(filled_template_data),
                },
            ).to_sse_format()
    else:
        # Ask mode - stream message
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_message = str(msg.content)
                break

        # Stream in chunks
        chunk_size = 50
        for i in range(0, len(last_message), chunk_size):
            yield SSEEvent(
                event_type=SSEEventType.ASSISTANT_DELTA,
                data={"content": last_message[i : i + chunk_size]},
            ).to_sse_format()
            await asyncio.sleep(0.02)

    # Aggregate citations from all tool results
    citations = []
    for tr in result.get("tool_results", []):
        citations.extend(tr.get("citations", []))

    # Build message_for_user based on request type
    if request.type == RequestType.AGENT:
        # Use LLM-generated summary if available (from summary_handler subgraph)
        summary_for_user = result.get("summary_for_user")
        if summary_for_user:
            message_content = summary_for_user
        elif request.agent_case == AgentCase.CREATE:
            artifact_title = artifact_data.get("title", "document") if artifact_data else "document"
            message_content = f"I've created the {artifact_title}."
        elif request.agent_case == AgentCase.EDIT:
            instruction_count = len(edit_instructions_data) if edit_instructions_data else 0
            message_content = f"I've prepared {instruction_count} edit instruction(s) for the document."
        elif request.agent_case == AgentCase.FILL:
            fields_count = len(filled_template_data) if filled_template_data else 0
            message_content = f"I've filled {fields_count} field(s) in the template."
        else:
            message_content = "Request completed."
    else:
        message_content = last_message if last_message else "Request completed."

    message_for_user = {
        "type": "summary",
        "content": message_content,
    }

    # Build output_for_system based on request type
    if request.type == RequestType.AGENT:
        operation = request.agent_case.value if request.agent_case else "notify"
        output_for_system = {
            "operation": operation,
            "artifact": artifact_data,
            "edit_instructions": edit_instructions_data,
            "filled_template": filled_template_data,
            "metadata": {
                "tool_call_count": result.get("tool_call_count", 0),
                "current_phase": result.get("current_phase", "complete"),
            },
        }
    else:
        output_for_system = {
            "operation": "notify",
            "artifact": None,
            "edit_instructions": None,
            "filled_template": None,
            "metadata": {
                "tool_call_count": result.get("tool_call_count", 0),
                "message_length": len(last_message),
            },
        }

    # Save artifacts to storage (for agent create mode)
    if request.type == RequestType.AGENT and artifact_data:
        artifact_storage = get_artifact_storage()
        if artifact_storage:
            try:
                artifact_storage.save_artifact(
                    tenant_id=initial_state.get("tenant_id", "unknown"),
                    session_id=session_id,
                    artifact=artifact_data,
                )
                logger.info(
                    "Saved artifact to storage",
                    artifact_id=artifact_data.get("artifact_id"),
                    session_id=session_id,
                )
            except Exception as e:
                logger.error(
                    "Failed to save artifact to storage",
                    error=str(e),
                    artifact_id=artifact_data.get("artifact_id"),
                )

    # Emit final event with dual response structure
    final_data = {
        "session_id": session_id,
        "type": request.type.value,
        "message_for_user": message_for_user,
        "output_for_system": output_for_system,
        "citations": citations,
    }

    yield SSEEvent(
        event_type=SSEEventType.FINAL,
        data=final_data,
    ).to_sse_format()

    logger.info(
        "Streaming request completed",
        session_id=session_id,
        request_type=request.type.value,
        agent_case=request.agent_case.value if request.agent_case else None,
    )


async def stream_resume_with_hitl(
    agent,
    update_values: dict,
    config: dict,
    event_queue: Queue,
    request,
) -> AsyncGenerator[str, None]:
    """
    Resume graph execution from an interrupt point with HITL handling.

    Uses LangGraph's update_state + ainvoke(None) pattern for proper resume.

    Args:
        agent: The compiled LangGraph agent
        update_values: State values to update (user's response to HITL)
        config: LangGraph config with thread_id
        event_queue: Queue for SSE events from nodes
        request: The request object (or mock) for response handling
    """
    session_id = config["configurable"]["thread_id"]

    # Emit initial status
    yield SSEEvent(
        event_type=SSEEventType.STATUS,
        data={
            "status": "processing",
            "session_id": session_id,
            "type": request.type.value,
        },
    ).to_sse_format()

    # Update the checkpoint state with user's response
    # This is the key difference from stream_with_hitl
    await agent.aupdate_state(config, update_values)

    # Resume graph execution from where it paused (pass None as input)
    async def run_graph():
        return await agent.ainvoke(None, config=config)

    graph_task = asyncio.create_task(run_graph())

    # Stream events from queue while graph is running
    while not graph_task.done():
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
            yield event.to_sse_format()
        except asyncio.TimeoutError:
            continue

    # Get final result
    result = await graph_task

    # Drain any remaining events
    while not event_queue.empty():
        event = event_queue.get_nowait()
        yield event.to_sse_format()

    # Check for HITL interrupt (graph may pause again)
    interrupt_info = check_hitl_interrupt(result)
    if interrupt_info:
        # Graph paused again - emit appropriate HITL event
        if interrupt_info["interrupt_type"] == "clarification":
            questions = interrupt_info.get("questions", [])
            yield SSEEvent(
                event_type=SSEEventType.CLARIFICATION_REQUIRED,
                data={
                    "session_id": session_id,
                    "message_for_user": {
                        "type": "clarification",
                        "content": "I need some additional information to proceed. Please answer the following questions.",
                        "questions": questions,
                    },
                    "questions": questions,
                    "missing_inputs": interrupt_info.get("missing_inputs", []),
                },
            ).to_sse_format()
        elif interrupt_info["interrupt_type"] == "confirmation":
            plan = interrupt_info.get("plan", {})
            sections = plan.get("sections", [])
            section_names = [s.get("name", s.get("id", "Section")) for s in sections]
            plan_description = f"I will create a document with {len(sections)} sections: {', '.join(section_names)}." if sections else "I have prepared an execution plan."

            yield SSEEvent(
                event_type=SSEEventType.AWAITING_CONFIRMATION,
                data={
                    "session_id": session_id,
                    "message_for_user": {
                        "type": "plan",
                        "content": plan_description,
                        "plan_summary": {
                            "sections": section_names,
                            "complexity": plan.get("estimated_complexity", "moderate"),
                            "template_strategy": plan.get("template_strategy", "generate_new"),
                        },
                    },
                    "plan": plan,
                    "options": ["approved", "modify", "cancelled"],
                },
            ).to_sse_format()

        yield SSEEvent(
            event_type=SSEEventType.STATUS,
            data={
                "status": "paused",
                "session_id": session_id,
                "interrupt_type": interrupt_info["interrupt_type"],
                "resume_instructions": "Send another request to /v1/copilot/stream with the same session_id and appropriate response fields.",
            },
        ).to_sse_format()

        logger.info(
            "Graph paused for HITL (resume)",
            session_id=session_id,
            interrupt_type=interrupt_info["interrupt_type"],
        )
        return

    # No interrupt - emit tool results
    for tr in result.get("tool_results", []):
        yield SSEEvent(
            event_type=SSEEventType.TOOL_CALL_RESULT,
            data={
                "tool_name": tr.get("tool_name", ""),
                "success": tr.get("success", False),
                "latency_ms": tr.get("latency_ms", 0),
            },
        ).to_sse_format()

    # Handle response based on request type
    artifact_data = None
    edit_instructions_data = None
    filled_template_data = None
    last_message = ""

    if request.type == RequestType.AGENT:
        if request.agent_case == AgentCase.CREATE:
            artifacts = result.get("artifacts", [])
            if artifacts:
                artifact_data = artifacts[-1]
                yield SSEEvent(
                    event_type=SSEEventType.ARTIFACT_UPDATE,
                    data=artifact_data,
                ).to_sse_format()
        elif request.agent_case == AgentCase.EDIT:
            edit_instructions_data = result.get("edit_instructions", [])
            for instruction in edit_instructions_data:
                yield SSEEvent(
                    event_type=SSEEventType.EDIT_INSTRUCTION,
                    data=instruction,
                ).to_sse_format()
        elif request.agent_case == AgentCase.FILL:
            filled_template_data = result.get("filled_fields", {})
            yield SSEEvent(
                event_type=SSEEventType.PHASE_COMPLETED,
                data={
                    "phase": "fill",
                    "fields_filled": len(filled_template_data),
                },
            ).to_sse_format()
    else:
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_message = str(msg.content)
                break

        chunk_size = 50
        for i in range(0, len(last_message), chunk_size):
            yield SSEEvent(
                event_type=SSEEventType.ASSISTANT_DELTA,
                data={"content": last_message[i : i + chunk_size]},
            ).to_sse_format()
            await asyncio.sleep(0.02)

    # Aggregate citations
    citations = []
    for tr in result.get("tool_results", []):
        citations.extend(tr.get("citations", []))

    # Build message_for_user and output_for_system
    # Check if plan was cancelled - handle this case specially
    if result.get("plan_confirmation_response") == "cancelled":
        message_for_user = {
            "type": "cancelled",
            "content": "I've cancelled the plan as requested. No document was created.",
        }
        output_for_system = {
            "operation": "cancelled",
            "artifact": None,
            "edit_instructions": None,
            "filled_template": None,
            "metadata": {
                "cancelled_at_phase": result.get("current_phase", "confirmation"),
            },
        }
    elif request.type == RequestType.AGENT:
        # Use LLM-generated summary if available (from summary_handler subgraph)
        summary_for_user = result.get("summary_for_user")
        if summary_for_user:
            message_content = summary_for_user
        elif request.agent_case == AgentCase.CREATE:
            artifact_title = artifact_data.get("title", "document") if artifact_data else "document"
            message_content = f"I've created the {artifact_title}."
        elif request.agent_case == AgentCase.EDIT:
            instruction_count = len(edit_instructions_data) if edit_instructions_data else 0
            message_content = f"I've prepared {instruction_count} edit instruction(s) for the document."
        elif request.agent_case == AgentCase.FILL:
            fields_count = len(filled_template_data) if filled_template_data else 0
            message_content = f"I've filled {fields_count} field(s) in the template."
        else:
            message_content = "Request completed."

        message_for_user = {
            "type": "summary",
            "content": message_content,
        }

        operation = request.agent_case.value if request.agent_case else "notify"
        output_for_system = {
            "operation": operation,
            "artifact": artifact_data,
            "edit_instructions": edit_instructions_data,
            "filled_template": filled_template_data,
            "metadata": {
                "tool_call_count": result.get("tool_call_count", 0),
                "current_phase": result.get("current_phase", "complete"),
            },
        }
    else:
        # Non-agent (ask mode) requests
        message_for_user = {
            "type": "summary",
            "content": last_message if last_message else "Request completed.",
        }
        output_for_system = {
            "operation": "notify",
            "artifact": None,
            "edit_instructions": None,
            "filled_template": None,
            "metadata": {
                "tool_call_count": result.get("tool_call_count", 0),
                "message_length": len(last_message) if last_message else 0,
            },
        }

    # Save artifacts to storage (for agent create mode, on resume)
    if request.type == RequestType.AGENT and artifact_data:
        artifact_storage = get_artifact_storage()
        if artifact_storage:
            try:
                # Get tenant_id from the result state
                tenant_id = result.get("tenant_id", "unknown")
                artifact_storage.save_artifact(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    artifact=artifact_data,
                )
                logger.info(
                    "Saved artifact to storage (resume)",
                    artifact_id=artifact_data.get("artifact_id"),
                    session_id=session_id,
                )
            except Exception as e:
                logger.error(
                    "Failed to save artifact to storage (resume)",
                    error=str(e),
                    artifact_id=artifact_data.get("artifact_id"),
                )

    # Emit final event
    final_data = {
        "session_id": session_id,
        "type": request.type.value,
        "message_for_user": message_for_user,
        "output_for_system": output_for_system,
        "citations": citations,
    }

    yield SSEEvent(
        event_type=SSEEventType.FINAL,
        data=final_data,
    ).to_sse_format()

    logger.info(
        "Resume streaming completed",
        session_id=session_id,
        request_type=request.type.value,
        agent_case=request.agent_case.value if request.agent_case else None,
    )


@router.post("/stream")
async def stream(request: UnifiedChatRequest) -> EventSourceResponse:
    """
    Unified streaming endpoint for both new requests and resuming paused sessions.

    This endpoint handles:
    - New ask/agent mode requests
    - Resuming paused HITL sessions (auto-detected when session_id has paused state)

    For new requests:
    - Starts a new graph execution
    - May pause at clarification or confirmation HITL points

    For resume (when session_id exists with paused state):
    - Use confirmation_response with values: "clarified", "approved", "modify", or "cancelled"
    - Put user input (clarification answers, modifications) in the 'message' field

    Emits:
    - STATUS events (processing, paused, resuming)
    - THINKING events during processing
    - PHASE_STARTED/PHASE_COMPLETED events for multi-agent flow
    - CLARIFICATION_REQUIRED when user input needed
    - AWAITING_CONFIRMATION when plan approval needed
    - TOOL_CALL_RESULT events for each tool call
    - ASSISTANT_DELTA events for streaming response (ask mode)
    - ARTIFACT_UPDATE events (agent create mode)
    - EDIT_INSTRUCTION events (agent edit mode)
    - FINAL event with complete response including message_for_user and output_for_system
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        # Create queue for SSE events from nodes
        event_queue: Queue = Queue()
        sse_callback = create_sse_callback(event_queue)

        try:
            # Check if this is a resume request (session_id with paused state)
            paused_state = None
            if request.session_id:
                paused_state = await get_paused_session_state(request.session_id)

            if paused_state:
                # ========================================
                # RESUME PATH
                # ========================================
                session_id = request.session_id
                config = {"configurable": {"thread_id": session_id}}

                logger.info(
                    "Resuming paused execution",
                    session_id=session_id,
                    has_clarification=request.confirmation_response == "clarified",
                    has_confirmation=request.confirmation_response is not None,
                )

                # Register callback in registry for nodes to access on resume
                # (callbacks can't be serialized in checkpoints, so don't include in update_state)
                register_sse_callback(session_id, sse_callback)

                # Update state with user's response (only serializable values)
                update_state = {}

                if request.confirmation_response == "clarified":
                    # User provided clarification via message field
                    update_state["clarification_input"] = request.message
                    update_state["clarification_pending"] = False
                    update_state["hitl_wait_reason"] = None

                    yield SSEEvent(
                        event_type=SSEEventType.CLARIFICATION_RESOLVED,
                        data={
                            "session_id": session_id,
                            "message": request.message,
                        },
                    ).to_sse_format()

                elif request.confirmation_response == "approved":
                    # User approved the plan
                    update_state["plan_confirmation_response"] = "approved"
                    update_state["plan_confirmed"] = True
                    update_state["hitl_wait_reason"] = None

                    yield SSEEvent(
                        event_type=SSEEventType.CONFIRMATION_RECEIVED,
                        data={
                            "session_id": session_id,
                            "response": "approved",
                        },
                    ).to_sse_format()

                elif request.confirmation_response == "modify":
                    # User wants to modify the plan (modification details in message)
                    update_state["plan_confirmation_response"] = "modify"
                    update_state["plan_modification_input"] = request.message
                    update_state["hitl_wait_reason"] = None

                    yield SSEEvent(
                        event_type=SSEEventType.CONFIRMATION_RECEIVED,
                        data={
                            "session_id": session_id,
                            "response": "modify",
                            "modifications": request.message,
                        },
                    ).to_sse_format()

                elif request.confirmation_response == "cancelled":
                    # User cancelled the operation
                    update_state["plan_confirmation_response"] = "cancelled"
                    update_state["hitl_wait_reason"] = None

                    yield SSEEvent(
                        event_type=SSEEventType.CONFIRMATION_RECEIVED,
                        data={
                            "session_id": session_id,
                            "response": "cancelled",
                        },
                    ).to_sse_format()

                # Emit resuming status
                yield SSEEvent(
                    event_type=SSEEventType.STATUS,
                    data={
                        "status": "resuming",
                        "session_id": session_id,
                    },
                ).to_sse_format()

                # Determine request type from current state for response handling
                request_type_str = paused_state.get("request_type", "ask")
                agent_case_str = paused_state.get("agent_case")

                # Create a mock request for stream_resume_with_hitl
                class MockRequest:
                    def __init__(self, request_type: str, agent_case: str | None):
                        self.type = RequestType(request_type) if request_type else RequestType.ASK
                        self.agent_case = AgentCase(agent_case) if agent_case else None

                mock_request = MockRequest(request_type_str, agent_case_str)

                # Resume graph execution using proper LangGraph resume mechanism
                # (update_state + ainvoke(None) instead of passing merged state)
                agent = get_agent()
                async for event_str in stream_resume_with_hitl(
                    agent, update_state, config, event_queue, mock_request
                ):
                    yield event_str

            else:
                # ========================================
                # NEW REQUEST PATH
                # ========================================
                initial_state = build_initial_state(request, sse_callback=sse_callback)
                session_id = initial_state["session_id"]

                config = {"configurable": {"thread_id": session_id}}

                logger.info(
                    "Starting streaming request",
                    session_id=session_id,
                    tenant_id=request.tenant_id,
                    request_type=request.type.value,
                    agent_case=request.agent_case.value if request.agent_case else None,
                    has_template=request.template is not None,
                )

                # Run graph with HITL handling
                agent = get_agent()
                async for event_str in stream_with_hitl(
                    agent, initial_state, config, event_queue, request
                ):
                    yield event_str

        except Exception as e:
            import traceback

            logger.error("Stream error", error=str(e), traceback=traceback.format_exc())
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                data={"error": str(e)},
            ).to_sse_format()

    return EventSourceResponse(event_generator())



# NOTE: /stream/resume endpoint has been removed.
# Resume functionality is now handled by the unified /stream endpoint.
# When session_id is provided and the session is paused, /stream auto-detects
# and handles the resume flow.
