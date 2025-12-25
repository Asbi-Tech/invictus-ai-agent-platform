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
    SSEEvent,
    SSEEventType,
    ToolResultResponse,
    UnifiedChatRequest,
    RequestType,
    AgentCase,
    ArtifactResponse,
    EditInstruction,
    EditOperation,
)
from agent_core.graph import compile_agent_graph
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
    """Get or create the compiled agent graph."""
    global _agent
    if _agent is None:
        checkpointer = get_checkpointer()
        _agent = compile_agent_graph(checkpointer=checkpointer)
    return _agent


# Type alias for SSE callback
SSECallbackType = Callable[[str, str | dict, str | None], Awaitable[None]]


def create_sse_callback(queue: Queue) -> SSECallbackType:
    """Create an SSE callback that puts events into a queue."""

    async def callback(event_type: str, data: str | dict, node_name: str | None = None):
        if event_type == "thinking":
            event = SSEEvent(
                event_type=SSEEventType.THINKING,
                data={"message": data, "node": node_name},
            )
        elif event_type == "edit_instruction":
            event = SSEEvent(
                event_type=SSEEventType.EDIT_INSTRUCTION,
                data=data if isinstance(data, dict) else {"content": data},
            )
        elif event_type == "artifact_update":
            event = SSEEvent(
                event_type=SSEEventType.ARTIFACT_UPDATE,
                data=data if isinstance(data, dict) else {"content": data},
            )
        else:
            event = SSEEvent(
                event_type=SSEEventType.STATUS,
                data={"status": data} if isinstance(data, str) else data,
            )
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
    Non-streaming chat endpoint with ask/agent mode support.

    Supports:
    - Ask mode: Conversational flow with RAG + tools
    - Agent mode (create): Generate new artifacts
    - Agent mode (edit): Generate edit instructions for existing artifacts
    """
    try:
        initial_state = build_initial_state(request)
        session_id = initial_state["session_id"]

        config = {"configurable": {"thread_id": session_id}}

        logger.info(
            "Processing chat request",
            session_id=session_id,
            tenant_id=request.tenant_id,
            request_type=request.type.value,
            agent_case=request.agent_case.value if request.agent_case else None,
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

        # Build response based on request type
        response = ChatResponse(
            session_id=session_id,
            message=last_message,
            tool_results=tool_results,
            citations=citations,
            intent=result.get("current_intent"),
        )

        # Add agent mode specific fields
        if request.type == RequestType.AGENT:
            if request.agent_case == AgentCase.CREATE:
                # Include generated artifact
                artifacts = result.get("artifacts", [])
                if artifacts:
                    artifact = artifacts[-1]
                    response.artifact = ArtifactResponse(
                        artifact_id=artifact.get("artifact_id", ""),
                        artifact_type=artifact.get("artifact_type", ""),
                        title=artifact.get("title", ""),
                        content=artifact.get("content", ""),
                        version=artifact.get("version", 1),
                        citations=artifact.get("citations", []),
                        metadata=artifact.get("metadata", {}),
                    )
            elif request.agent_case == AgentCase.EDIT:
                # Include edit instructions
                edit_instructions = result.get("edit_instructions", [])
                response.edit_instructions = [
                    EditInstruction(
                        operation=EditOperation(inst.get("operation", "modify")),
                        section_id=inst.get("section_id"),
                        section_title=inst.get("section_title"),
                        position=inst.get("position"),
                        content=inst.get("content"),
                        reasoning=inst.get("reasoning", ""),
                    )
                    for inst in edit_instructions
                ]

        logger.info(
            "Chat request completed",
            session_id=session_id,
            request_type=request.type.value,
            response_length=len(last_message),
            tool_calls=len(tool_results),
        )

        return response

    except Exception as e:
        import traceback

        error_detail = str(e) or traceback.format_exc()
        logger.error("Chat error", error=error_detail, traceback=traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_detail)


@router.post("/stream")
async def stream(request: UnifiedChatRequest) -> EventSourceResponse:
    """
    Streaming endpoint with THINKING events and ask/agent mode support.

    Emits:
    - THINKING events during processing (e.g., "Looking up opportunity details...")
    - TOOL_CALL_RESULT events for each tool call
    - ASSISTANT_DELTA events for streaming response (ask mode)
    - ARTIFACT_UPDATE events (agent create mode)
    - EDIT_INSTRUCTION events (agent edit mode)
    - FINAL event with complete response
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
            agent = get_agent()

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

            # Emit tool results
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

        except Exception as e:
            logger.error("Stream error", error=str(e))
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                data={"error": str(e)},
            ).to_sse_format()

    return EventSourceResponse(event_generator())
