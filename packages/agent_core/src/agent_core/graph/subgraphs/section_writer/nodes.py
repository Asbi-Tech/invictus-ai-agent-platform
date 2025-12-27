"""Section Writer nodes for parallel section generation."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState, SectionAssignment

logger = get_logger(__name__)

SECTION_WRITING_PROMPT = """You are a professional document writer. Write the following section for a {document_type}.

Section: {section_name}
Description: {section_description}

Available Data:
{available_data}

User Request Context: {user_request}
Additional Instructions: {additional_prompt}

Write professional, well-structured content for this section. Include:
- Clear, concise prose
- Relevant data points from the provided information
- Professional tone appropriate for investment documents
- Logical flow and structure

Format your response in markdown. Do not include the section title - just the content."""


def get_llm(temperature: float = 0.7) -> AzureChatOpenAI:
    """Get Azure OpenAI LLM instance."""
    settings = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=temperature,
    )


def get_user_question(state: MultiAgentState) -> str:
    """Get user's question from messages."""
    from langchain_core.messages import HumanMessage
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


async def prepare_sections(state: MultiAgentState) -> dict:
    """
    Prepare sections for parallel writing.

    This node ensures section assignments are ready for generation.
    """
    logger.info("Preparing sections for writing")

    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "phase_started",
            {"phase": "generation", "message": "Writing document sections..."},
            "section_writer",
        )

    section_assignments = state.get("section_assignments", [])

    if not section_assignments:
        logger.warning("No sections to write")
        return {}

    logger.info(f"Prepared {len(section_assignments)} sections for writing")

    return {}


async def write_sections(state: MultiAgentState) -> dict:
    """
    Write all sections in parallel.

    This node uses asyncio.gather to write multiple sections concurrently.
    """
    logger.info("Writing sections in parallel")

    section_assignments = state.get("section_assignments", [])
    intent_analysis = state.get("intent_analysis") or {}
    document_type = intent_analysis.get("document_type", "document")
    additional_prompt = state.get("additional_prompt") or ""
    user_question = get_user_question(state)
    sse_callback = state.get("sse_callback")

    # Gather data for sections
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}
    insights = state.get("synthesized_insights") or {}

    async def write_single_section(assignment: SectionAssignment) -> SectionAssignment:
        """Write a single section."""
        section_id = assignment["section_id"]
        section_name = assignment["section_name"]

        # Emit section started event
        if sse_callback:
            await sse_callback(
                "section_started",
                {"section_id": section_id, "section_name": section_name},
                "section_writer",
            )

        # Gather relevant data for this section
        data_sources = assignment.get("assigned_data", [])
        available_data = _gather_section_data(
            data_sources, mcp_data, rag_data, web_data, insights
        )

        # Get section description from template
        template = state.get("selected_template") or {}
        section_desc = ""
        for s in template.get("sections", []):
            if s["id"] == section_id:
                section_desc = s.get("description", section_name)
                break

        # Build prompt
        prompt = SECTION_WRITING_PROMPT.format(
            document_type=document_type,
            section_name=section_name,
            section_description=section_desc,
            available_data=json.dumps(available_data, indent=2, default=str)[:4000],
            user_request=user_question[:500],
            additional_prompt=additional_prompt[:500] if additional_prompt else "None",
        )

        # Call LLM
        llm = get_llm(temperature=0.7)
        try:
            response = await llm.ainvoke(prompt)
            content = response.content

            # Emit section completed event
            if sse_callback:
                await sse_callback(
                    "section_completed",
                    {
                        "section_id": section_id,
                        "section_name": section_name,
                        "content_length": len(content),
                    },
                    "section_writer",
                )

            return {
                **assignment,
                "content": content,
                "status": "completed",
                "sources": _extract_sources(data_sources, mcp_data, rag_data, web_data),
            }

        except Exception as e:
            logger.error(f"Failed to write section {section_id}", error=str(e))
            return {
                **assignment,
                "status": "failed",
                "error": str(e),
            }

    # Write all sections in parallel
    completed_sections = await asyncio.gather(
        *[write_single_section(a) for a in section_assignments],
        return_exceptions=True,
    )

    # Process results
    results = []
    completed_count = 0
    for i, result in enumerate(completed_sections):
        if isinstance(result, Exception):
            results.append({
                **section_assignments[i],
                "status": "failed",
                "error": str(result),
            })
        else:
            results.append(result)
            if result.get("status") == "completed":
                completed_count += 1

    logger.info(f"Section writing complete: {completed_count}/{len(results)} successful")

    return {
        "section_assignments": results,
        "sections_completed": completed_count,
    }


async def collect_sections(state: MultiAgentState) -> dict:
    """
    Collect written sections and assemble the document.

    This node combines all sections into the final artifact.
    """
    logger.info("Collecting written sections")

    section_assignments = state.get("section_assignments", [])
    intent_analysis = state.get("intent_analysis") or {}
    document_type = intent_analysis.get("document_type", "document")
    mcp_data = state.get("mcp_data") or {}

    # Build document content
    sections_content = []
    all_sources = []

    for assignment in section_assignments:
        if assignment.get("status") == "completed" and assignment.get("content"):
            section_name = assignment["section_name"]
            content = assignment["content"]
            sections_content.append(f"## {section_name}\n\n{content}")

            # Collect sources
            if sources := assignment.get("sources"):
                all_sources.extend(sources)

    # Assemble full document
    opportunity_name = mcp_data.get("opportunity", {}).get("name", "Document")
    title = f"{opportunity_name} - {document_type.replace('_', ' ').title()}"
    full_content = f"# {title}\n\n" + "\n\n".join(sections_content)

    # Create artifact
    artifact = {
        "artifact_id": str(uuid.uuid4())[:8],
        "artifact_type": document_type,
        "title": title,
        "content": full_content,
        "version": 1,
        "citations": all_sources[:20],  # Limit citations
        "metadata": {
            "sections_count": len(section_assignments),
            "sections_completed": len([s for s in section_assignments if s.get("status") == "completed"]),
            "generated_at": datetime.utcnow().isoformat(),
        },
    }

    # Emit artifact update
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "artifact_update",
            artifact,
            "section_writer",
        )

    # Update artifacts list
    artifacts = list(state.get("artifacts", []))
    artifacts.append(artifact)

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "generation",
        "to_phase": "review",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Generated artifact with {len(sections_content)} sections",
    })

    logger.info(f"Document assembled: {len(sections_content)} sections, {len(full_content)} chars")

    return {
        "artifacts": artifacts,
        "current_artifact_id": artifact["artifact_id"],
        "phase_history": phase_history,
        "current_phase": "review",
        "updated_at": datetime.utcnow(),
    }


def _gather_section_data(
    data_sources: list[str],
    mcp_data: dict,
    rag_data: dict,
    web_data: dict,
    insights: dict,
) -> dict[str, Any]:
    """Gather relevant data for a section based on its data sources."""
    data = {}

    for source in data_sources:
        if source.startswith("mcp:"):
            key = source.split(":")[1] if ":" in source else "opportunity"
            if mcp_data.get(key):
                data[f"mcp_{key}"] = mcp_data[key]

        elif source.startswith("rag:"):
            if rag_data.get("fields"):
                data["document_data"] = rag_data["fields"]

        elif source.startswith("web:"):
            if web_data.get("results"):
                data["web_results"] = web_data["results"][:3]
            if web_data.get("answer"):
                data["web_summary"] = web_data["answer"]

        elif source.startswith("insights:"):
            key = source.split(":")[1] if ":" in source else "summary"
            if insights.get("insights"):
                data["insights"] = insights["insights"][:5]
            if insights.get("normalized_data"):
                data["normalized_data"] = insights["normalized_data"]

    return data


def _extract_sources(
    data_sources: list[str],
    mcp_data: dict,
    rag_data: dict,
    web_data: dict,
) -> list[dict]:
    """Extract source references for attribution."""
    sources = []

    for source in data_sources:
        if source.startswith("mcp:"):
            key = source.split(":")[1] if ":" in source else "opportunity"
            if mcp_data.get(key):
                sources.append({
                    "source_type": "mcp",
                    "source_id": f"mcp:{key}",
                    "title": f"MCP {key.title()} Data",
                    "confidence": 0.95,
                })

        elif source.startswith("rag:") and rag_data.get("citations"):
            for citation in rag_data["citations"][:2]:
                sources.append({
                    "source_type": "rag",
                    "source_id": citation.get("document_id", "unknown"),
                    "title": citation.get("title", "Document"),
                    "confidence": 0.85,
                })

        elif source.startswith("web:") and web_data.get("results"):
            for result in web_data["results"][:2]:
                sources.append({
                    "source_type": "web",
                    "source_id": result.get("url", "unknown"),
                    "title": result.get("title", "Web Source"),
                    "url": result.get("url"),
                    "confidence": 0.70,
                })

    return sources
