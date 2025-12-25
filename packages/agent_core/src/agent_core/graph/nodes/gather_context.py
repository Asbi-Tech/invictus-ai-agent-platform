"""Gather context node - retrieves relevant data from tools."""

from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage

from agent_core.tools.mcp_client import get_entity_data, mcp_registry
from agent_core.tools.deals_mcp import call_deals_tool
from agent_core.tools.rag_gateway import (
    StorageConfig,
    extract_fields,
    generate_fields_for_question,
)
from agent_core.tools.web_search import search_for_context
from common.logging import get_logger

logger = get_logger(__name__)


async def gather_context(state: dict[str, Any]) -> dict[str, Any]:
    """
    Gather context by calling relevant tools.

    This node:
    - Calls MCP tools for entity data (if entity context provided)
    - Calls Deals MCP tools for opportunity data
    - Calls RAG Gateway for document extraction (if documents selected)
    - Calls Tavily web search (if web_search_enabled is True)
    - Respects enabled_mcps filter from tool_policy
    - Emits THINKING events for streaming feedback

    Args:
        state: The current agent state

    Returns:
        State updates with tool results and gathered context
    """
    tool_results = list(state.get("tool_results", []))
    working_memory = dict(state.get("working_memory", {}))
    tool_call_count = state.get("tool_call_count", 0)
    tool_policy = state.get("tool_policy", {})
    page_context = state.get("page_context")
    selected_docs = state.get("selected_docs", {})
    document_ids = state.get("document_ids", [])
    tenant_id = state.get("tenant_id", "")
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    messages = state.get("messages", [])
    sse_callback = state.get("sse_callback")

    # Get the user's question
    user_question = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_question = str(msg.content)
            break

    # Check if we've exceeded max tool calls
    max_tool_calls = tool_policy.get("max_tool_calls", 10)
    if tool_call_count >= max_tool_calls:
        logger.warning("Max tool calls reached", count=tool_call_count)
        return {"tool_results": tool_results, "working_memory": working_memory}

    # Get enabled MCPs - support both new and old field names
    # Use explicit None check since empty list [] should mean "no MCPs enabled"
    enabled_mcps = tool_policy.get("enabled_mcps")
    if enabled_mcps is None:
        enabled_mcps = tool_policy.get("mcp_domains_enabled", ["deals"])

    # 1. Get opportunity context from Deals MCP if available
    if page_context and "deals" in enabled_mcps:
        opportunity_id = page_context.get("opportunity_id") or page_context.get("entity_id")
        entity_type = page_context.get("entity_type")

        # Handle opportunity context
        if opportunity_id and (entity_type == "opportunity" or page_context.get("opportunity_id")):
            if sse_callback:
                await sse_callback(
                    "thinking",
                    "Looking up opportunity details...",
                    "gather_context",
                )

            start = datetime.utcnow()

            try:
                result = await call_deals_tool(
                    "get_opportunity_details",
                    {"opportunity_id": opportunity_id, "tenant_id": tenant_id},
                )

                latency = (datetime.utcnow() - start).total_seconds() * 1000

                tool_results.append(
                    {
                        "tool_name": "deals:get_opportunity_details",
                        "input_summary": f"Get opportunity {opportunity_id}",
                        "output_summary": (
                            f"Retrieved: {result.data.get('name', 'Unknown')}"
                            if result.success
                            else result.error
                        ),
                        "latency_ms": latency,
                        "success": result.success,
                        "error": result.error,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                if result.success and result.data:
                    working_memory["opportunity_data"] = result.data

                tool_call_count += 1

            except Exception as e:
                logger.error("Deals MCP call failed", error=str(e))

    # 2. Fallback to generic MCP for other entity types
    if page_context and tool_call_count < max_tool_calls:
        entity_type = page_context.get("entity_type")
        entity_id = page_context.get("entity_id")

        # Skip if already handled as opportunity
        if entity_type and entity_id and entity_type != "opportunity":
            # Map entity type to domain
            domain_map = {
                "client": "clients",
                "risk_profile": "risk_planning",
            }
            domain = domain_map.get(entity_type)

            if domain and domain in enabled_mcps and mcp_registry.is_available(domain):
                if sse_callback:
                    await sse_callback(
                        "thinking",
                        f"Looking up {entity_type} details...",
                        "gather_context",
                    )

                start = datetime.utcnow()

                try:
                    result = await get_entity_data(
                        domain=domain,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        tenant_id=tenant_id,
                    )

                    latency = (datetime.utcnow() - start).total_seconds() * 1000

                    tool_results.append(
                        {
                            "tool_name": f"mcp:{domain}:get_{entity_type}",
                            "input_summary": f"Get {entity_type} {entity_id}",
                            "output_summary": (
                                str(result.data)[:200] if result.success else result.error
                            ),
                            "latency_ms": latency,
                            "success": result.success,
                            "error": result.error,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

                    if result.success and result.data:
                        working_memory[f"{entity_type}_data"] = result.data

                    tool_call_count += 1

                except Exception as e:
                    logger.error("MCP call failed", error=str(e), domain=domain)

    # 3. Query RAG Gateway if documents are selected and we have a question
    # Combine document_ids and selected_docs.doc_ids
    doc_ids = document_ids or []
    if selected_docs and selected_docs.get("doc_ids"):
        doc_ids = list(set(doc_ids + selected_docs.get("doc_ids", [])))

    storage_dict = selected_docs.get("storage") if selected_docs else None
    rag_enabled = tool_policy.get("rag_enabled", True)

    if doc_ids and storage_dict and user_question and rag_enabled and tool_call_count < max_tool_calls:
        if sse_callback:
            await sse_callback(
                "thinking",
                f"Searching {len(doc_ids)} documents...",
                "gather_context",
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
            result = await extract_fields(
                tenant_id=tenant_id,
                doc_ids=doc_ids,
                fields=fields,
                storage=storage,
                user_id=user_id,
                session_id=session_id,
            )

            latency = (datetime.utcnow() - start).total_seconds() * 1000

            tool_results.append(
                {
                    "tool_name": "rag_gateway:extract_fields",
                    "input_summary": f"Extract fields for: {user_question[:50]}...",
                    "output_summary": f"Extracted {len(result.fields)} fields",
                    "latency_ms": latency,
                    "success": True,
                    "raw_output": result.fields,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            # Store results in working memory
            working_memory["rag_results"] = result.fields
            working_memory["rag_citations"] = getattr(result, "citations", [])
            tool_call_count += 1

            logger.info(
                "RAG extraction completed",
                field_count=len(result.fields),
                latency_ms=latency,
            )

        except Exception as e:
            logger.error("RAG extraction failed", error=str(e))
            tool_results.append(
                {
                    "tool_name": "rag_gateway:extract_fields",
                    "input_summary": f"Extract fields for: {user_question[:50]}...",
                    "output_summary": "",
                    "latency_ms": 0,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

    # 4. Web search with Tavily if enabled
    web_search_enabled = tool_policy.get("web_search_enabled", False)

    if web_search_enabled and user_question and tool_call_count < max_tool_calls:
        if sse_callback:
            await sse_callback(
                "thinking",
                "Searching the web for relevant information...",
                "gather_context",
            )

        start = datetime.utcnow()

        try:
            # Get opportunity context for better search
            opportunity_name = None
            sector = None
            if opp_data := working_memory.get("opportunity_data"):
                opportunity_name = opp_data.get("name")
                sector = opp_data.get("sector")

            result = await search_for_context(
                user_question=user_question,
                opportunity_name=opportunity_name,
                sector=sector,
            )

            latency = (datetime.utcnow() - start).total_seconds() * 1000

            tool_results.append(
                {
                    "tool_name": "tavily:web_search",
                    "input_summary": f"Search: {user_question[:50]}...",
                    "output_summary": (
                        f"Found {len(result.results)} results"
                        if result.success
                        else result.error
                    ),
                    "latency_ms": latency,
                    "success": result.success,
                    "error": result.error,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if result.success:
                # Store web search results in working memory
                working_memory["web_search_results"] = result.results
                if result.answer:
                    working_memory["web_search_answer"] = result.answer

                # Create citations from web results
                web_citations = [
                    {
                        "source": "web",
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "")[:200],
                    }
                    for r in result.results
                ]
                working_memory["web_citations"] = web_citations

                logger.info(
                    "Web search completed",
                    result_count=len(result.results),
                    has_answer=bool(result.answer),
                    latency_ms=latency,
                )

            tool_call_count += 1

        except Exception as e:
            logger.error("Web search failed", error=str(e))
            tool_results.append(
                {
                    "tool_name": "tavily:web_search",
                    "input_summary": f"Search: {user_question[:50]}...",
                    "output_summary": "",
                    "latency_ms": 0,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

    # Emit completion thinking event
    if sse_callback:
        await sse_callback(
            "thinking",
            "Context gathered, generating response...",
            "gather_context",
        )

    return {
        "tool_results": tool_results,
        "working_memory": working_memory,
        "tool_call_count": tool_call_count,
    }
