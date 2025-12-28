"""Source Mapper nodes for source attribution."""

from datetime import datetime
from typing import Any

from common.callback_registry import get_callback_for_state
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState, SourceLedger, SourceRef

logger = get_logger(__name__)


async def build_ledger(state: MultiAgentState) -> dict:
    """
    Build a comprehensive source ledger.

    This node creates a structured list of all sources used.
    """
    logger.info("Building source ledger")

    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_started",
            {"phase": "source_mapping", "message": "Building source attribution..."},
            "source_mapper",
        )

    sources: list[SourceRef] = []
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}

    # Add MCP sources
    for key, data in mcp_data.items():
        if data:
            sources.append({
                "source_id": f"mcp:{key}",
                "source_type": "mcp",
                "title": f"MCP {key.replace('_', ' ').title()}",
                "url": None,
                "document_id": None,
                "chunk_id": None,
                "confidence": 0.95,
                "metadata": {"domain": key},
            })

    # Add RAG sources
    if citations := rag_data.get("citations", []):
        for citation in citations:
            sources.append({
                "source_id": f"rag:{citation.get('document_id', 'unknown')}",
                "source_type": "rag",
                "title": citation.get("title", "Document"),
                "url": None,
                "document_id": citation.get("document_id"),
                "chunk_id": citation.get("chunk_id"),
                "confidence": 0.85,
                "metadata": citation.get("metadata", {}),
            })

    # Add Web sources
    if results := web_data.get("results", []):
        for result in results:
            sources.append({
                "source_id": f"web:{result.get('url', 'unknown')}",
                "source_type": "web",
                "title": result.get("title", "Web Source"),
                "url": result.get("url"),
                "document_id": None,
                "chunk_id": None,
                "confidence": 0.70,
                "metadata": {"snippet": result.get("content", "")[:200]},
            })

    logger.info(f"Built source ledger with {len(sources)} sources")

    # Initialize source ledger
    source_ledger: SourceLedger = {
        "sources": sources,
        "section_mappings": {},
        "confidence_scores": {},
    }

    return {"source_ledger": source_ledger}


async def map_to_sections(state: MultiAgentState) -> dict:
    """
    Map sources to document sections.

    This node links each section to its source references.
    """
    logger.info("Mapping sources to sections")

    source_ledger = state.get("source_ledger") or {}
    sources = source_ledger.get("sources", [])
    section_assignments = state.get("section_assignments", [])

    section_mappings: dict[str, list[str]] = {}
    confidence_scores: dict[str, float] = {}

    for assignment in section_assignments:
        section_id = assignment["section_id"]
        section_sources = assignment.get("sources", [])

        # Map source IDs to this section
        source_ids = []
        for src in section_sources:
            source_id = src.get("source_id", "")
            if source_id:
                source_ids.append(source_id)
                # Track confidence
                confidence_scores[source_id] = src.get("confidence", 0.8)

        section_mappings[section_id] = source_ids

    # Update source ledger
    updated_ledger: SourceLedger = {
        "sources": sources,
        "section_mappings": section_mappings,
        "confidence_scores": confidence_scores,
    }

    # Emit source mapped event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "source_mapped",
            {
                "total_sources": len(sources),
                "sections_mapped": len(section_mappings),
            },
            "source_mapper",
        )

    # Emit phase completed
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_completed",
            {
                "phase": "source_mapping",
                "sources_count": len(sources),
            },
            "source_mapper",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "source_mapping",
        "to_phase": "complete",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Mapped {len(sources)} sources to {len(section_mappings)} sections",
    })

    logger.info(f"Source mapping complete: {len(section_mappings)} sections mapped")

    return {
        "source_ledger": updated_ledger,
        "phase_history": phase_history,
        "current_phase": "complete",
        "updated_at": datetime.utcnow(),
    }
