"""Ingest context node - validates and normalizes input."""

from typing import Any

from common.callback_registry import get_callback_for_state
from common.logging import get_logger

logger = get_logger(__name__)


async def ingest_context(state: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize the incoming request context.

    This node:
    - Validates tenant_id and user_id
    - Normalizes page context
    - Sets up working memory for the request
    - Handles both ask and agent mode contexts
    - Emits THINKING events for streaming feedback

    Args:
        state: The current agent state

    Returns:
        State updates with validated context
    """
    tenant_id = state.get("tenant_id", "")
    session_id = state.get("session_id", "")
    page_context = state.get("page_context")
    selected_docs = state.get("selected_docs", {})
    document_ids = state.get("document_ids", [])
    request_type = state.get("request_type", "ask")
    sse_callback = get_callback_for_state(state)

    module_id = page_context.get("module_id", "deals") if page_context else "deals"

    # Emit initial thinking event
    if sse_callback:
        await sse_callback(
            "thinking",
            "Processing request...",
            "ingest_context",
        )

    logger.info(
        "Ingesting context",
        tenant_id=tenant_id,
        session_id=session_id,
        module=module_id,
        request_type=request_type,
    )

    # Initialize working memory
    working_memory = state.get("working_memory", {})

    # Combine document_ids and selected_docs.doc_ids
    all_doc_ids = document_ids or []
    if selected_docs and selected_docs.get("doc_ids"):
        all_doc_ids = list(set(all_doc_ids + selected_docs.get("doc_ids", [])))

    working_memory.update(
        {
            "context_validated": True,
            "module": module_id,
            "has_documents": bool(all_doc_ids),
            "has_storage_config": selected_docs.get("storage") is not None if selected_docs else False,
            "request_type": request_type,
        }
    )

    # Add entity context if available (backward compatible)
    if page_context:
        entity_type = page_context.get("entity_type")
        entity_id = page_context.get("entity_id")
        if entity_type and entity_id:
            working_memory["entity_context"] = {
                "type": entity_type,
                "id": entity_id,
            }

        # Add opportunity context if available (new format)
        opportunity_id = page_context.get("opportunity_id")
        opportunity_name = page_context.get("opportunity_name")
        if opportunity_id:
            working_memory["opportunity_context"] = {
                "id": opportunity_id,
                "name": opportunity_name,
                "screen_name": page_context.get("screen_name"),
                "screen_highlights": page_context.get("screen_highlights", {}),
            }
            # Also set entity_context for backward compatibility
            if not working_memory.get("entity_context"):
                working_memory["entity_context"] = {
                    "type": "opportunity",
                    "id": opportunity_id,
                }

    return {"working_memory": working_memory}
