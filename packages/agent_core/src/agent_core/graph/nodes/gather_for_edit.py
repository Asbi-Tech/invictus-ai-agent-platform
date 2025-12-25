"""Gather context for edit operations."""

import re
from datetime import datetime
from typing import Any

from common.logging import get_logger
from agent_core.tools.deals_mcp import call_deals_tool

logger = get_logger(__name__)


def parse_artifact_sections(content: str) -> list[dict[str, Any]]:
    """
    Parse markdown content into sections.

    Args:
        content: Markdown content

    Returns:
        List of sections with id, title, level, and content
    """
    sections = []
    lines = content.split("\n")

    current_section = None
    current_content = []
    section_id = 0

    for line in lines:
        # Check for headers (## or ###)
        header_match = re.match(r"^(#{1,4})\s+(.+)$", line)
        if header_match:
            # Save previous section
            if current_section:
                current_section["content"] = "\n".join(current_content).strip()
                sections.append(current_section)

            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            section_id += 1

            current_section = {
                "section_id": f"section_{section_id}",
                "title": title,
                "level": level,
                "content": "",
            }
            current_content = []
        else:
            current_content.append(line)

    # Save last section
    if current_section:
        current_section["content"] = "\n".join(current_content).strip()
        sections.append(current_section)
    elif current_content:
        # Content without headers
        sections.append({
            "section_id": "section_0",
            "title": "Main",
            "level": 0,
            "content": "\n".join(current_content).strip(),
        })

    return sections


async def gather_for_edit(state: dict[str, Any]) -> dict[str, Any]:
    """
    Gather context specifically for editing an existing artifact.

    This node:
    - Calls enabled MCP tools for entity data
    - Uses RAG for document context
    - Analyzes current artifact structure

    Args:
        state: Current graph state

    Returns:
        Updated state with gathered context for editing
    """
    tool_results = list(state.get("tool_results", []))
    working_memory = dict(state.get("working_memory", {}))
    current_artifact = state.get("current_artifact")
    page_context = state.get("page_context", {})
    tool_policy = state.get("tool_policy", {})
    tenant_id = state.get("tenant_id", "")
    sse_callback = state.get("sse_callback")

    enabled_mcps = tool_policy.get("enabled_mcps", ["deals"])
    tool_call_count = state.get("tool_call_count", 0)

    # Emit thinking event
    if sse_callback:
        await sse_callback(
            "thinking",
            "Analyzing artifact structure...",
            "gather_for_edit",
        )

    # Analyze artifact structure
    if current_artifact:
        content = current_artifact.get("content", "")
        sections = parse_artifact_sections(content)
        working_memory["artifact_sections"] = sections
        working_memory["artifact_type"] = current_artifact.get("artifact_type", "document")
        working_memory["artifact_title"] = current_artifact.get("title", "Untitled")
        working_memory["section_count"] = len(sections)

        logger.info(
            "Parsed artifact structure",
            section_count=len(sections),
            artifact_type=working_memory["artifact_type"],
        )

    # Get opportunity context if available
    opportunity_id = page_context.get("opportunity_id") or page_context.get("entity_id")

    if opportunity_id and "deals" in enabled_mcps:
        if sse_callback:
            await sse_callback(
                "thinking",
                "Looking up opportunity details...",
                "gather_for_edit",
            )

        start_time = datetime.utcnow()

        # Get opportunity details for context
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

            logger.info(
                "Retrieved opportunity data for edit context",
                opportunity_id=opportunity_id,
                latency_ms=latency_ms,
            )

    # Mark context as gathered
    working_memory["edit_context_gathered"] = True
    working_memory["gather_timestamp"] = datetime.utcnow().isoformat()

    if sse_callback:
        await sse_callback(
            "thinking",
            "Context gathered, determining edit instructions...",
            "gather_for_edit",
        )

    return {
        "tool_results": tool_results,
        "working_memory": working_memory,
        "tool_call_count": tool_call_count,
    }
