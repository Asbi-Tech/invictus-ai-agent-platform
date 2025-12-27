"""Template Manager nodes for template selection and adaptation."""

from datetime import datetime
from typing import Any

from common.logging import get_logger
from agent_core.graph.state import MultiAgentState

logger = get_logger(__name__)

# Template definitions by document type
TEMPLATES = {
    "investment_memo": {
        "id": "investment_memo_v1",
        "name": "Investment Memo Template",
        "sections": [
            {"id": "executive_summary", "name": "Executive Summary", "required": True},
            {"id": "company_overview", "name": "Company Overview", "required": True},
            {"id": "market_analysis", "name": "Market Analysis", "required": True},
            {"id": "financial_analysis", "name": "Financial Analysis", "required": True},
            {"id": "investment_highlights", "name": "Investment Highlights", "required": True},
            {"id": "risks", "name": "Risk Factors", "required": True},
            {"id": "recommendation", "name": "Recommendation", "required": True},
        ],
    },
    "prescreening": {
        "id": "prescreening_v1",
        "name": "Prescreening Report Template",
        "sections": [
            {"id": "overview", "name": "Deal Overview", "required": True},
            {"id": "fit_assessment", "name": "Strategy Fit Assessment", "required": True},
            {"id": "preliminary_analysis", "name": "Preliminary Analysis", "required": True},
            {"id": "key_considerations", "name": "Key Considerations", "required": True},
            {"id": "recommendation", "name": "Recommendation", "required": True},
        ],
    },
    "custom_report": {
        "id": "custom_report_v1",
        "name": "Custom Report Template",
        "sections": [
            {"id": "introduction", "name": "Introduction", "required": True},
            {"id": "analysis", "name": "Analysis", "required": True},
            {"id": "findings", "name": "Key Findings", "required": True},
            {"id": "conclusion", "name": "Conclusion", "required": True},
        ],
    },
}


async def select_template(state: MultiAgentState) -> dict:
    """
    Select the appropriate template based on document type.

    This node:
    1. Determines the document type from intent analysis
    2. Selects the matching template
    3. Validates template requirements
    """
    logger.info("Selecting template")

    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "phase_started",
            {"phase": "template", "message": "Preparing document template..."},
            "template_manager",
        )

    intent_analysis = state.get("intent_analysis") or {}
    document_type = intent_analysis.get("document_type") or "custom_report"
    template_strategy = state.get("template_strategy", "generate_new")

    # Get template for document type
    template = TEMPLATES.get(document_type, TEMPLATES["custom_report"])

    # Emit template selected event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "template_selected",
            {
                "template_id": template["id"],
                "template_name": template["name"],
                "section_count": len(template["sections"]),
            },
            "template_manager",
        )

    logger.info(f"Selected template: {template['name']} with {len(template['sections'])} sections")

    return {
        "selected_template": template,
    }


async def map_sections(state: MultiAgentState) -> dict:
    """
    Map data sources to template sections.

    This node:
    1. Analyzes available data
    2. Maps data sources to each section
    3. Identifies sections with insufficient data
    """
    logger.info("Mapping sections to data sources")

    template = state.get("selected_template") or {}
    execution_plan = state.get("execution_plan") or {}
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}
    insights = state.get("synthesized_insights") or {}

    template_mapping: dict[str, str] = {}
    section_data_map: dict[str, list[str]] = {}

    # Map each section to available data
    for section in template.get("sections", []):
        section_id = section["id"]
        section_name = section["name"].lower()
        data_sources = []

        # Determine relevant data sources based on section name
        if "executive" in section_name or "overview" in section_name:
            data_sources.extend(["mcp:opportunity", "insights:summary"])

        if "company" in section_name or "business" in section_name:
            data_sources.extend(["mcp:opportunity", "rag:company_info"])

        if "market" in section_name or "industry" in section_name:
            data_sources.extend(["web:search", "rag:market_analysis"])

        if "financial" in section_name:
            data_sources.extend(["mcp:opportunity", "rag:financials"])

        if "risk" in section_name:
            data_sources.extend(["mcp:prescreening", "rag:risks"])

        if "investment" in section_name or "highlight" in section_name:
            data_sources.extend(["mcp:prescreening", "insights:key_findings"])

        if "recommendation" in section_name:
            data_sources.extend(["mcp:prescreening", "insights:recommendation"])

        if "fit" in section_name or "strategy" in section_name:
            data_sources.extend(["mcp:prescreening", "mcp:opportunity"])

        if "analysis" in section_name:
            data_sources.extend(["mcp:opportunity", "rag:analysis", "insights:findings"])

        if "finding" in section_name or "conclusion" in section_name:
            data_sources.extend(["insights:summary", "insights:key_findings"])

        # Default sources if none matched
        if not data_sources:
            data_sources = ["mcp:opportunity", "insights:general"]

        template_mapping[section_id] = ",".join(data_sources[:3])
        section_data_map[section_id] = data_sources

    logger.info(f"Mapped {len(template_mapping)} sections to data sources")

    return {
        "template_mapping": template_mapping,
        "working_memory": {
            **state.get("working_memory", {}),
            "section_data_map": section_data_map,
        },
    }


async def adapt_template(state: MultiAgentState) -> dict:
    """
    Adapt the template based on available data and user requirements.

    This node:
    1. Adjusts sections based on data availability
    2. Applies user's additional prompt
    3. Prepares section assignments for writing
    """
    logger.info("Adapting template")

    template = state.get("selected_template") or {}
    template_mapping = state.get("template_mapping") or {}
    execution_plan = state.get("execution_plan") or {}
    additional_prompt = state.get("additional_prompt")

    # Create section assignments from template
    from agent_core.graph.state import SectionAssignment

    section_assignments: list[SectionAssignment] = []
    for section in template.get("sections", []):
        section_id = section["id"]
        data_sources = template_mapping.get(section_id, "").split(",")

        assignment: SectionAssignment = {
            "section_id": section_id,
            "section_name": section["name"],
            "status": "pending",
            "assigned_data": data_sources,
            "template_section": section.get("template_content"),
            "content": None,
            "sources": [],
            "error": None,
        }
        section_assignments.append(assignment)

    # Emit template adapted event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "template_adapted",
            {
                "sections_prepared": len(section_assignments),
                "has_customization": bool(additional_prompt),
            },
            "template_manager",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "template",
        "to_phase": "generation",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Template prepared with {len(section_assignments)} sections",
    })

    logger.info(f"Template adapted: {len(section_assignments)} sections ready for generation")

    return {
        "section_assignments": section_assignments,
        "sections_total": len(section_assignments),
        "sections_completed": 0,
        "phase_history": phase_history,
        "current_phase": "generation",
        "updated_at": datetime.utcnow(),
    }
