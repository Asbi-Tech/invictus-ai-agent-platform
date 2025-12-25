"""Gather context for artifact creation."""

from datetime import datetime
from typing import Any

from common.logging import get_logger
from agent_core.tools.deals_mcp import call_deals_tool
from agent_core.tools.rag_gateway import extract_fields, generate_fields_for_question

logger = get_logger(__name__)


async def gather_for_create(state: dict[str, Any]) -> dict[str, Any]:
    """
    Gather comprehensive context for creating a new artifact.

    This node uses all available tools:
    - MCP tools from enabled_mcps
    - RAG for document context
    - Web search if enabled

    Args:
        state: Current graph state

    Returns:
        Updated state with gathered context for creation
    """
    tool_results = list(state.get("tool_results", []))
    working_memory = dict(state.get("working_memory", {}))
    page_context = state.get("page_context", {})
    tool_policy = state.get("tool_policy", {})
    tenant_id = state.get("tenant_id", "")
    document_ids = state.get("document_ids", [])
    selected_docs = state.get("selected_docs", {})
    messages = state.get("messages", [])
    sse_callback = state.get("sse_callback")

    enabled_mcps = tool_policy.get("enabled_mcps", ["deals"])
    max_tool_calls = tool_policy.get("max_tool_calls", 10)
    tool_call_count = state.get("tool_call_count", 0)

    # Get user message for context
    user_message = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            user_message = str(msg.content)
            break
        elif hasattr(msg, "content") and not hasattr(msg, "type"):
            # Fallback for different message types
            from langchain_core.messages import HumanMessage
            if isinstance(msg, HumanMessage):
                user_message = str(msg.content)
                break

    opportunity_id = page_context.get("opportunity_id") or page_context.get("entity_id")

    # 1. Get opportunity details if available
    if opportunity_id and "deals" in enabled_mcps and tool_call_count < max_tool_calls:
        if sse_callback:
            await sse_callback(
                "thinking",
                "Looking up opportunity details...",
                "gather_for_create",
            )

        start_time = datetime.utcnow()
        result = await call_deals_tool(
            "get_opportunity_details",
            {"opportunity_id": opportunity_id, "tenant_id": tenant_id},
        )
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        if result.success:
            working_memory["opportunity_data"] = result.data
            tool_results.append({
                "tool_name": "deals:get_opportunity_details",
                "input_summary": f"Get details for opportunity {opportunity_id}",
                "output_summary": f"Retrieved opportunity: {result.data.get('name', 'Unknown')}",
                "latency_ms": latency_ms,
                "success": True,
                "citations": [],
                "raw_output": result.data,
            })
            tool_call_count += 1

    # 2. Get prescreening report if available
    if opportunity_id and "deals" in enabled_mcps and tool_call_count < max_tool_calls:
        if sse_callback:
            await sse_callback(
                "thinking",
                "Retrieving prescreening report...",
                "gather_for_create",
            )

        start_time = datetime.utcnow()
        result = await call_deals_tool(
            "get_prescreening_report",
            {"opportunity_id": opportunity_id, "tenant_id": tenant_id},
        )
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        if result.success:
            working_memory["prescreening_data"] = result.data
            tool_results.append({
                "tool_name": "deals:get_prescreening_report",
                "input_summary": f"Get prescreening for opportunity {opportunity_id}",
                "output_summary": f"Retrieved prescreening report: {result.data.get('recommendation', 'Unknown')}",
                "latency_ms": latency_ms,
                "success": True,
                "citations": [],
                "raw_output": result.data,
            })
            tool_call_count += 1

    # 3. Get investment memo if available
    if opportunity_id and "deals" in enabled_mcps and tool_call_count < max_tool_calls:
        if sse_callback:
            await sse_callback(
                "thinking",
                "Checking for existing investment memo...",
                "gather_for_create",
            )

        start_time = datetime.utcnow()
        result = await call_deals_tool(
            "get_investment_memo",
            {"opportunity_id": opportunity_id, "tenant_id": tenant_id},
        )
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        if result.success:
            working_memory["investment_memo_data"] = result.data
            tool_results.append({
                "tool_name": "deals:get_investment_memo",
                "input_summary": f"Get investment memo for opportunity {opportunity_id}",
                "output_summary": f"Retrieved investment memo v{result.data.get('version', '1.0')}",
                "latency_ms": latency_ms,
                "success": True,
                "citations": [],
                "raw_output": result.data,
            })
            tool_call_count += 1

    # 4. Get activity timeline
    if opportunity_id and "deals" in enabled_mcps and tool_call_count < max_tool_calls:
        start_time = datetime.utcnow()
        result = await call_deals_tool(
            "get_opportunity_activity",
            {"opportunity_id": opportunity_id, "tenant_id": tenant_id, "limit": 10},
        )
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        if result.success:
            working_memory["activity_data"] = result.data
            tool_results.append({
                "tool_name": "deals:get_opportunity_activity",
                "input_summary": f"Get activity for opportunity {opportunity_id}",
                "output_summary": f"Retrieved {result.data.get('total', 0)} activities",
                "latency_ms": latency_ms,
                "success": True,
                "citations": [],
                "raw_output": result.data,
            })
            tool_call_count += 1

    # 5. RAG for documents if available
    doc_ids = document_ids or (selected_docs.get("doc_ids", []) if selected_docs else [])
    storage_config = selected_docs.get("storage") if selected_docs else None

    if doc_ids and storage_config and tool_policy.get("rag_enabled", True) and tool_call_count < max_tool_calls:
        if sse_callback:
            await sse_callback(
                "thinking",
                f"Searching {len(doc_ids)} documents...",
                "gather_for_create",
            )

        try:
            # Generate extraction fields based on user question
            start_time = datetime.utcnow()
            fields = await generate_fields_for_question(user_message or "Generate relevant content")
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            if fields:
                # Extract fields from documents
                rag_result = await extract_fields(
                    tenant_id=tenant_id,
                    question=user_message,
                    fields=fields,
                    doc_ids=doc_ids,
                    storage={
                        "account_url": storage_config.get("account_url", ""),
                        "filesystem": storage_config.get("filesystem", "documents"),
                        "base_prefix": storage_config.get("base_prefix", ""),
                    },
                )

                if rag_result and rag_result.fields:
                    working_memory["rag_results"] = rag_result.fields
                    working_memory["rag_citations"] = rag_result.citations or []
                    tool_results.append({
                        "tool_name": "rag:extract_fields",
                        "input_summary": f"Extract fields from {len(doc_ids)} documents",
                        "output_summary": f"Extracted {len(rag_result.fields)} fields",
                        "latency_ms": latency_ms,
                        "success": True,
                        "citations": rag_result.citations or [],
                    })
                    tool_call_count += 1

        except Exception as e:
            logger.warning("RAG extraction failed", error=str(e))

    # Mark context as gathered
    working_memory["create_context_gathered"] = True
    working_memory["gather_timestamp"] = datetime.utcnow().isoformat()

    if sse_callback:
        await sse_callback(
            "thinking",
            "Context gathered, generating content...",
            "gather_for_create",
        )

    logger.info(
        "Gathered context for artifact creation",
        opportunity_id=opportunity_id,
        tool_calls=tool_call_count,
        has_rag=bool(working_memory.get("rag_results")),
    )

    return {
        "tool_results": tool_results,
        "working_memory": working_memory,
        "tool_call_count": tool_call_count,
    }
