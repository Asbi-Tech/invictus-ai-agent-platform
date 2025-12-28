"""Ask Handler nodes for processing Q&A requests."""

import json
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import AzureChatOpenAI

from common.callback_registry import get_callback_for_state
from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState
from agent_core.tools.deals_mcp import call_deals_tool
from agent_core.tools.rag_gateway import (
    StorageConfig,
    extract_fields,
    generate_fields_for_question,
)
from agent_core.tools.web_search import search_for_context

logger = get_logger(__name__)

# Answer generation prompt
ANSWER_GENERATION_PROMPT = """You are an AI assistant for investment professionals.

Answer the user's question based on the available context.

User Question: {question}

Page Context: {page_context}

Additional Instructions: {additional_prompt}

Available Data:
{available_data}

Instructions:
1. Answer the question directly and concisely
2. If you don't have enough information, say so clearly
3. If the question is about specific data (like target raise, deal terms, etc.) and you have that data, provide the specific answer
4. Be helpful and professional

Your response:"""


def get_llm(temperature: float = 0.3) -> AzureChatOpenAI:
    """Get Azure OpenAI LLM instance."""
    settings = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=temperature,
    )


def get_last_human_message(state: MultiAgentState) -> str:
    """Extract the last human message from state."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


async def gather_context(state: MultiAgentState) -> dict:
    """
    Gather relevant context for answering the question.

    This node:
    1. Extracts page context and available data
    2. Formats context for the LLM
    3. Emits thinking events
    """
    logger.info("Gathering context for ask mode")

    # Emit thinking event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "thinking",
            {"message": "Gathering context to answer your question..."},
            "ask_handler",
        )

    # Collect available context
    page_context = state.get("page_context") or {}
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    working_memory = state.get("working_memory") or {}

    # Format available data for the prompt
    available_data = {}

    if page_context:
        available_data["page_context"] = page_context

    if mcp_data:
        available_data["mcp_data"] = mcp_data

    if rag_data:
        available_data["rag_data"] = rag_data

    if working_memory:
        available_data["working_memory"] = working_memory

    logger.info(f"Context gathered: {len(available_data)} data sources")

    return {
        "working_memory": {
            **working_memory,
            "ask_context": available_data,
        },
    }


async def fetch_data(state: MultiAgentState) -> dict:
    """
    Fetch data from MCP tools for answering questions.

    This node:
    1. Checks enabled MCPs in tool_policy
    2. Calls relevant MCP tools based on page context
    3. Stores results in mcp_data and tool_results
    """
    logger.info("Fetching data for ask mode")

    tool_policy = state.get("tool_policy") or {}
    enabled_mcps = tool_policy.get("enabled_mcps", [])
    max_tool_calls = tool_policy.get("max_tool_calls", 10)
    page_context = state.get("page_context") or {}
    tenant_id = state.get("tenant_id", "")

    tool_results = list(state.get("tool_results", []))
    mcp_data: dict[str, Any] = dict(state.get("mcp_data", {}))
    tool_call_count = state.get("tool_call_count", 0)

    # Initialize rag_data
    rag_data: dict[str, Any] = dict(state.get("rag_data", {}))
    rag_enabled = tool_policy.get("rag_enabled", True)

    # Get user question (used by RAG and web search)
    messages = state.get("messages", [])
    user_question = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_question = str(msg.content)
            break

    # Emit thinking event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "thinking",
            {"message": "Fetching data from enabled tools..."},
            "ask_handler",
        )

    # Fetch from Deals MCP if enabled
    if "deals" in enabled_mcps:
        opportunity_id = page_context.get("opportunity_id")

        if opportunity_id and tool_call_count < max_tool_calls:
            logger.info(f"[MCP] Calling deals:get_opportunity_details for {opportunity_id}")

            # Emit fetching event
            if sse_callback := get_callback_for_state(state):
                await sse_callback(
                    "fetching_mcp_data",
                    {"domain": "deals", "message": "Fetching opportunity details..."},
                    "ask_handler",
                )

            # Get opportunity details
            start = datetime.utcnow()
            try:
                result = await call_deals_tool(
                    "get_opportunity_details",
                    {"opportunity_id": opportunity_id, "tenant_id": tenant_id}
                )
                latency = (datetime.utcnow() - start).total_seconds() * 1000

                tool_results.append({
                    "tool_name": "deals:get_opportunity_details",
                    "input_summary": f"Get opportunity {opportunity_id}",
                    "output_summary": (
                        f"Retrieved: {result.data.get('name', 'opportunity')}"
                        if result.success and result.data
                        else result.error or "No data"
                    ),
                    "latency_ms": latency,
                    "success": result.success,
                    "error": result.error,
                    "timestamp": datetime.utcnow().isoformat(),
                })

                if result.success and result.data:
                    mcp_data["opportunity"] = result.data
                    logger.info(f"[MCP] deals:get_opportunity_details succeeded: {result.data.get('name', 'unknown')}")
                else:
                    logger.info(f"[MCP] deals:get_opportunity_details returned no data")

                tool_call_count += 1

            except Exception as e:
                logger.error(f"[MCP] deals:get_opportunity_details failed: {e}")
                tool_results.append({
                    "tool_name": "deals:get_opportunity_details",
                    "input_summary": f"Get opportunity {opportunity_id}",
                    "output_summary": "",
                    "latency_ms": 0,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                })

    # Emit MCP data received event
    if mcp_data and (sse_callback := get_callback_for_state(state)):
        await sse_callback(
            "mcp_data_received",
            {
                "domains_fetched": list(mcp_data.keys()),
                "tool_calls": tool_call_count,
            },
            "ask_handler",
        )

    # ===== Fetch RAG data if documents are selected =====
    if rag_enabled and tool_call_count < max_tool_calls:
        # Get document IDs from both sources
        document_ids = state.get("document_ids", [])
        selected_docs = state.get("selected_docs") or {}
        doc_ids = list(set(document_ids + selected_docs.get("doc_ids", [])))

        if doc_ids:
            storage_dict = selected_docs.get("storage")
            if storage_dict and user_question:
                # Emit fetching event
                if sse_callback := get_callback_for_state(state):
                    await sse_callback(
                        "fetching_rag_data",
                        {
                            "message": f"Searching {len(doc_ids)} documents...",
                            "doc_count": len(doc_ids),
                        },
                        "ask_handler",
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

                    # Call RAG Gateway
                    logger.info(
                        "Calling RAG Gateway",
                        doc_count=len(doc_ids),
                        field_count=len(fields),
                    )

                    result = await extract_fields(
                        tenant_id=tenant_id,
                        doc_ids=doc_ids,
                        fields=fields,
                        storage=storage,
                        user_id=state.get("user_id", ""),
                        session_id=state.get("session_id", ""),
                    )

                    latency = (datetime.utcnow() - start).total_seconds() * 1000

                    tool_results.append({
                        "tool_name": "rag_gateway:extract_fields",
                        "input_summary": f"Extract fields for: {user_question[:50]}...",
                        "output_summary": f"Extracted {len(result.fields)} fields from {len(result.sources)} sources",
                        "latency_ms": latency,
                        "success": True,
                        "timestamp": datetime.utcnow().isoformat(),
                        "citations": result.sources,  # Include sources as citations
                        "raw_output": result.fields,  # Include raw field values
                    })

                    # Store results
                    rag_data["fields"] = result.fields
                    rag_data["field_results"] = [fr.model_dump() for fr in result.field_results]  # Full results with sources
                    rag_data["sources"] = result.sources  # All unique sources
                    rag_data["doc_ids"] = doc_ids
                    rag_data["query"] = user_question

                    tool_call_count += 1

                    logger.info(
                        "RAG extraction completed",
                        field_count=len(result.fields),
                        source_count=len(result.sources),
                        latency_ms=latency,
                    )

                    # Emit RAG data received event
                    if sse_callback := get_callback_for_state(state):
                        await sse_callback(
                            "rag_data_received",
                            {
                                "fields_extracted": len(result.fields),
                                "sources_found": len(result.sources),
                                "doc_count": len(doc_ids),
                                "latency_ms": latency,
                            },
                            "ask_handler",
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

    # ===== Fetch Web data if web search is enabled =====
    web_data: dict[str, Any] = dict(state.get("web_data", {}))
    web_search_enabled = tool_policy.get("web_search_enabled", False)

    if web_search_enabled and tool_call_count < max_tool_calls and user_question:
        # Emit fetching event
        if sse_callback := get_callback_for_state(state):
            await sse_callback(
                "fetching_web_data",
                {"message": "Searching the web for relevant information..."},
                "ask_handler",
            )

        start = datetime.utcnow()
        try:
            # Get opportunity context for better search (if available from MCP)
            opp_data = mcp_data.get("opportunity", {})
            opportunity_name = opp_data.get("name")
            sector = opp_data.get("sector")

            result = await search_for_context(
                user_question=user_question,
                opportunity_name=opportunity_name,
                sector=sector,
            )

            latency = (datetime.utcnow() - start).total_seconds() * 1000

            if result.success:
                # Store web search results
                web_data["results"] = result.results
                web_data["query"] = user_question
                if result.answer:
                    web_data["answer"] = result.answer

                # Create citations from web results FIRST
                web_citations = [
                    {
                        "source": "web",
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "")[:200],
                    }
                    for r in result.results
                ]
                web_data["citations"] = web_citations

                # Now append tool_results WITH citations
                tool_results.append({
                    "tool_name": "tavily:web_search",
                    "input_summary": f"Search: {user_question[:50]}...",
                    "output_summary": f"Found {len(result.results)} results",
                    "latency_ms": latency,
                    "success": True,
                    "error": None,
                    "timestamp": datetime.utcnow().isoformat(),
                    "citations": web_citations,
                })

                tool_call_count += 1

                logger.info(
                    "Web search completed",
                    result_count=len(result.results),
                    has_answer=bool(result.answer),
                    latency_ms=latency,
                )

                # Emit web data received event
                if sse_callback := get_callback_for_state(state):
                    await sse_callback(
                        "web_data_received",
                        {
                            "result_count": len(result.results),
                            "has_answer": bool(result.answer),
                            "latency_ms": latency,
                        },
                        "ask_handler",
                    )
            else:
                # Failure case - no citations
                tool_results.append({
                    "tool_name": "tavily:web_search",
                    "input_summary": f"Search: {user_question[:50]}...",
                    "output_summary": result.error or "No results",
                    "latency_ms": latency,
                    "success": False,
                    "error": result.error,
                    "timestamp": datetime.utcnow().isoformat(),
                    "citations": [],
                })

        except Exception as e:
            logger.error("Web search failed", error=str(e))
            tool_results.append({
                "tool_name": "tavily:web_search",
                "input_summary": f"Search: {user_question[:50]}...",
                "output_summary": "",
                "latency_ms": 0,
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "citations": [],
            })

    logger.info(
        f"Data fetched: MCP={list(mcp_data.keys())}, RAG={bool(rag_data)}, Web={bool(web_data)} ({tool_call_count} tool calls)"
    )

    return {
        "mcp_data": mcp_data,
        "rag_data": rag_data,
        "web_data": web_data,
        "tool_results": tool_results,
        "tool_call_count": tool_call_count,
    }


async def generate_answer(state: MultiAgentState) -> dict:
    """
    Generate an answer to the user's question.

    This node:
    1. Builds the prompt with available context
    2. Calls the LLM to generate an answer
    3. Adds the answer as an AIMessage
    """
    logger.info("Generating answer for ask mode")

    # Emit thinking event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "thinking",
            {"message": "Generating answer..."},
            "ask_handler",
        )

    # Extract context
    user_question = get_last_human_message(state)
    page_context = state.get("page_context") or {}
    additional_prompt = state.get("additional_prompt") or ""
    working_memory = state.get("working_memory") or {}
    ask_context = working_memory.get("ask_context", {})
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}

    # Combine all available data
    all_data = {}
    if ask_context:
        all_data.update(ask_context)
    if mcp_data:
        all_data["mcp_data"] = mcp_data
    if rag_data:
        all_data["rag_data"] = rag_data
    if web_data:
        all_data["web_data"] = web_data

    # Format available data
    if all_data:
        available_data_str = json.dumps(all_data, indent=2, default=str)
    else:
        available_data_str = "No additional data available."

    # Build prompt
    prompt = ANSWER_GENERATION_PROMPT.format(
        question=user_question,
        page_context=json.dumps(page_context, indent=2) if page_context else "None",
        additional_prompt=additional_prompt or "None",
        available_data=available_data_str,
    )

    # Generate answer
    llm = get_llm(temperature=0.3)
    try:
        response = await llm.ainvoke(prompt)
        answer = response.content.strip()

        logger.info(f"Answer generated: {len(answer)} characters")

    except Exception as e:
        logger.error(f"Failed to generate answer: {e}")
        answer = "I apologize, but I encountered an error while generating your answer. Please try again."

    # Emit assistant delta for streaming
    if sse_callback := get_callback_for_state(state):
        # Stream the answer in chunks
        chunk_size = 50
        for i in range(0, len(answer), chunk_size):
            await sse_callback(
                "assistant_delta",
                {"content": answer[i:i + chunk_size]},
                "ask_handler",
            )

    # Add answer as AIMessage
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=answer))

    return {
        "messages": messages,
        "current_intent": "ask",
        "updated_at": datetime.utcnow(),
    }


async def finalize_ask(state: MultiAgentState) -> dict:
    """
    Finalize the ask mode response.

    This node:
    1. Emits the final event
    2. Updates phase tracking
    """
    logger.info("Finalizing ask mode response")

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "ask",
        "to_phase": "complete",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": "Ask mode completed",
    })

    # Emit final event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_completed",
            {
                "phase": "ask",
                "message": "Question answered",
            },
            "ask_handler",
        )

    return {
        "current_phase": "complete",
        "phase_history": phase_history,
        "updated_at": datetime.utcnow(),
    }
