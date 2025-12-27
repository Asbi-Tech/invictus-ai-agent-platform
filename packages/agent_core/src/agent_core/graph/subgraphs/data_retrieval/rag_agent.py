"""RAG Agent for document extraction."""

from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage

from agent_core.tools.rag_gateway import (
    StorageConfig,
    extract_fields,
    generate_fields_for_question,
)
from agent_core.graph.state import MultiAgentState
from common.logging import get_logger

logger = get_logger(__name__)


async def fetch_rag_data(state: MultiAgentState) -> dict:
    """
    Fetch data from documents via RAG Gateway.

    This node:
    1. Extracts document IDs and storage config
    2. Generates field definitions based on user question
    3. Calls RAG Gateway to extract fields
    4. Stores results in rag_data
    """
    logger.info("Fetching RAG data")

    tool_results = list(state.get("tool_results", []))
    rag_data: dict[str, Any] = dict(state.get("rag_data", {}))
    tool_call_count = state.get("tool_call_count", 0)
    tool_policy = state.get("tool_policy", {})

    max_tool_calls = tool_policy.get("max_tool_calls", 10)
    rag_enabled = tool_policy.get("rag_enabled", True)

    # Check if RAG is enabled and we have capacity
    if not rag_enabled or tool_call_count >= max_tool_calls:
        logger.info("RAG skipped: disabled or max tools reached")
        return {"rag_data": rag_data, "tool_results": tool_results}

    # Get document IDs
    document_ids = state.get("document_ids", [])
    selected_docs = state.get("selected_docs") or {}
    doc_ids = list(set(document_ids + selected_docs.get("doc_ids", [])))

    if not doc_ids:
        logger.info("No documents to search")
        return {"rag_data": rag_data, "tool_results": tool_results}

    # Get storage config
    storage_dict = selected_docs.get("storage")
    if not storage_dict:
        logger.warning("No storage config, skipping RAG")
        return {"rag_data": rag_data, "tool_results": tool_results}

    # Get user question
    messages = state.get("messages", [])
    user_question = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_question = str(msg.content)
            break

    if not user_question:
        logger.warning("No user question, skipping RAG")
        return {"rag_data": rag_data, "tool_results": tool_results}

    # Emit fetching event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "fetching_rag_data",
            {"message": f"Searching {len(doc_ids)} documents...", "doc_count": len(doc_ids)},
            "data_retrieval",
        )

    start = datetime.utcnow()

    try:
        # Create storage config
        storage = StorageConfig(
            account_url=storage_dict.get("account_url", ""),
            filesystem=storage_dict.get("filesystem", "documents"),
            base_prefix=storage_dict.get("base_prefix", ""),
        )

        # Generate field definitions based on the question
        fields = generate_fields_for_question(user_question)

        # Call the RAG Gateway
        tenant_id = state.get("tenant_id", "")
        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")

        result = await extract_fields(
            tenant_id=tenant_id,
            doc_ids=doc_ids,
            fields=fields,
            storage=storage,
            user_id=user_id,
            session_id=session_id,
        )

        latency = (datetime.utcnow() - start).total_seconds() * 1000

        tool_results.append({
            "tool_name": "rag_gateway:extract_fields",
            "input_summary": f"Extract fields for: {user_question[:50]}...",
            "output_summary": f"Extracted {len(result.fields)} fields",
            "latency_ms": latency,
            "success": True,
            "raw_output": result.fields,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Store results
        rag_data["fields"] = result.fields
        rag_data["citations"] = getattr(result, "citations", [])
        rag_data["doc_ids"] = doc_ids
        rag_data["query"] = user_question

        logger.info(
            "RAG extraction completed",
            field_count=len(result.fields),
            latency_ms=latency,
        )

        # Emit RAG data received event
        if sse_callback := state.get("sse_callback"):
            await sse_callback(
                "rag_data_received",
                {
                    "fields_extracted": len(result.fields),
                    "doc_count": len(doc_ids),
                    "latency_ms": latency,
                },
                "data_retrieval",
            )

    except Exception as e:
        logger.error("RAG extraction failed", error=str(e))
        tool_results.append({
            "tool_name": "rag_gateway:extract_fields",
            "input_summary": f"Extract fields for: {user_question[:50]}...",
            "output_summary": "",
            "latency_ms": 0,
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        })

    return {
        "rag_data": rag_data,
        "tool_results": tool_results,
        "tool_call_count": tool_call_count + 1,
    }
