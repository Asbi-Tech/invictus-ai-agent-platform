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
    ChatResponse,
    HITLStatus,
    SSEEvent,
    SSEEventType,
    ToolResultResponse,
    UnifiedChatRequest,
    ResumeRequest,
    RequestType,
    AgentCase,
    ArtifactResponse,
    EditInstruction,
    EditOperation,
)
from agent_core.graph import compile_multi_agent_graph
from agent_core.memory import CosmosDBCheckpointer
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])

# Initialize checkpointer lazily to avoid connection errors at import time
_checkpointer = None
_agent = None


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
        "sse_callback": sse_callback,
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
    if request.current_artifact:
        state["current_artifact"] = {
            "artifact_id": request.current_artifact.artifact_id,
            "artifact_type": request.current_artifact.artifact_type,
            "title": request.current_artifact.title,
            "content": request.current_artifact.content,
            "metadata": request.current_artifact.metadata,
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
    if state.get("clarification_pending") and not state.get("clarification_responses"):
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
        # Graph paused - emit appropriate HITL event
        if interrupt_info["interrupt_type"] == "clarification":
            yield SSEEvent(
                event_type=SSEEventType.CLARIFICATION_REQUIRED,
                data={
                    "session_id": session_id,
                    "questions": interrupt_info["questions"],
                    "message": "Please provide additional information to continue.",
                },
            ).to_sse_format()
        elif interrupt_info["interrupt_type"] == "confirmation":
            yield SSEEvent(
                event_type=SSEEventType.AWAITING_CONFIRMATION,
                data={
                    "session_id": session_id,
                    "plan": interrupt_info["plan"],
                    "message": "Please review and approve the execution plan.",
                },
            ).to_sse_format()

        # Emit paused status
        yield SSEEvent(
            event_type=SSEEventType.STATUS,
            data={
                "status": "paused",
                "session_id": session_id,
                "interrupt_type": interrupt_info["interrupt_type"],
                "resume_endpoint": "/v1/copilot/stream/resume",
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
    if request.type == RequestType.AGENT:
        if request.agent_case == AgentCase.CREATE:
            # Stream artifact
            artifacts = result.get("artifacts", [])
            if artifacts:
                artifact = artifacts[-1]
                yield SSEEvent(
                    event_type=SSEEventType.ARTIFACT_UPDATE,
                    data=artifact,
                ).to_sse_format()
        elif request.agent_case == AgentCase.EDIT:
            # Stream edit instructions
            for instruction in result.get("edit_instructions", []):
                yield SSEEvent(
                    event_type=SSEEventType.EDIT_INSTRUCTION,
                    data=instruction,
                ).to_sse_format()
    else:
        # Ask mode - stream message
        messages = result.get("messages", [])
        last_message = ""
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

    # Emit final event
    final_data = {
        "session_id": session_id,
        "type": request.type.value,
        "tool_call_count": result.get("tool_call_count", 0),
        "intent": result.get("current_intent"),
        "current_phase": result.get("current_phase", "complete"),
    }

    # Add type-specific data to final event
    if request.type == RequestType.AGENT:
        if request.agent_case == AgentCase.CREATE:
            final_data["artifact_count"] = len(result.get("artifacts", []))
        elif request.agent_case == AgentCase.EDIT:
            final_data["instruction_count"] = len(result.get("edit_instructions", []))

    yield SSEEvent(
        event_type=SSEEventType.FINAL,
        data=final_data,
    ).to_sse_format()

    logger.info(
        "Streaming request completed",
        session_id=session_id,
        request_type=request.type.value,
    )


@router.post("/stream")
async def stream(request: UnifiedChatRequest) -> EventSourceResponse:
    """
    Streaming endpoint with THINKING events, HITL support, and ask/agent mode.

    Emits:
    - STATUS events (processing, paused)
    - THINKING events during processing
    - PHASE_STARTED/PHASE_COMPLETED events for multi-agent flow
    - CLARIFICATION_REQUIRED when user input needed
    - AWAITING_CONFIRMATION when plan approval needed
    - TOOL_CALL_RESULT events for each tool call
    - ASSISTANT_DELTA events for streaming response (ask mode)
    - ARTIFACT_UPDATE events (agent create mode)
    - EDIT_INSTRUCTION events (agent edit mode)
    - FINAL event with complete response

    If the graph pauses for HITL, use /stream/resume to continue.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        # Create queue for SSE events from nodes
        event_queue: Queue = Queue()
        sse_callback = create_sse_callback(event_queue)

        try:
            initial_state = build_initial_state(request, sse_callback=sse_callback)
            session_id = initial_state["session_id"]

            config = {"configurable": {"thread_id": session_id}}

            logger.info(
                "Starting streaming request",
                session_id=session_id,
                tenant_id=request.tenant_id,
                request_type=request.type.value,
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


@router.post("/stream/resume")
async def resume_stream(request: ResumeRequest) -> EventSourceResponse:
    """
    Resume a paused execution with user input.

    Use this endpoint after receiving a CLARIFICATION_REQUIRED or
    AWAITING_CONFIRMATION event from /stream.

    For clarification:
    - Provide clarification_response: {question_id: answer}

    For confirmation:
    - Provide confirmation_response: "approved", "modify", or "cancelled"
    - Optionally provide plan_modifications if response is "modify"
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        # Create queue for SSE events
        event_queue: Queue = Queue()
        sse_callback = create_sse_callback(event_queue)

        try:
            session_id = request.session_id
            config = {"configurable": {"thread_id": session_id}}

            logger.info(
                "Resuming paused execution",
                session_id=session_id,
                has_clarification=request.clarification_response is not None,
                has_confirmation=request.confirmation_response is not None,
            )

            # Get checkpointer to retrieve current state
            checkpointer = get_checkpointer()
            if not checkpointer:
                raise HTTPException(
                    status_code=503,
                    detail="State persistence not available. Cannot resume session.",
                )

            # Get current checkpoint state
            checkpoint = await checkpointer.aget(config)
            if not checkpoint:
                raise HTTPException(
                    status_code=404,
                    detail=f"No paused session found for session_id: {session_id}",
                )

            # Retrieve the current state from checkpoint
            current_state = checkpoint.get("channel_values", {})

            # Update state with user's response
            update_state = {"sse_callback": sse_callback}

            if request.clarification_response:
                # User provided clarification responses
                update_state["clarification_responses"] = request.clarification_response
                update_state["clarification_pending"] = False
                update_state["hitl_wait_reason"] = None

                yield SSEEvent(
                    event_type=SSEEventType.CLARIFICATION_RESOLVED,
                    data={
                        "session_id": session_id,
                        "responses": request.clarification_response,
                    },
                ).to_sse_format()

            if request.confirmation_response:
                # User provided confirmation response
                update_state["plan_confirmation_response"] = request.confirmation_response
                update_state["hitl_wait_reason"] = None

                if request.confirmation_response == "approved":
                    update_state["plan_confirmed"] = True
                elif request.confirmation_response == "modify" and request.plan_modifications:
                    update_state["plan_modifications"] = request.plan_modifications

                yield SSEEvent(
                    event_type=SSEEventType.CONFIRMATION_RECEIVED,
                    data={
                        "session_id": session_id,
                        "response": request.confirmation_response,
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

            # Resume graph execution with updated state
            agent = get_agent()

            # Merge current state with updates
            resume_state = {**current_state, **update_state}

            # Determine request type from current state for response handling
            request_type_str = current_state.get("request_type", "ask")
            agent_case_str = current_state.get("agent_case")

            # Create a mock request for stream_with_hitl
            class MockRequest:
                def __init__(self, request_type: str, agent_case: str | None):
                    self.type = RequestType(request_type) if request_type else RequestType.ASK
                    self.agent_case = AgentCase(agent_case) if agent_case else None

            mock_request = MockRequest(request_type_str, agent_case_str)

            # Resume graph execution
            async for event_str in stream_with_hitl(
                agent, resume_state, config, event_queue, mock_request
            ):
                yield event_str

        except HTTPException:
            raise
        except Exception as e:
            import traceback

            logger.error(
                "Resume stream error", error=str(e), traceback=traceback.format_exc()
            )
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                data={"error": str(e)},
            ).to_sse_format()

    return EventSourceResponse(event_generator())
