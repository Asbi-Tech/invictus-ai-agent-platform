"""Planning nodes for execution plan generation."""

import json
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI

from common.callback_registry import get_callback_for_state
from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import (
    MultiAgentState,
    ExecutionPlan,
    SectionPlan,
    DataRequirement,
    ToolUsage,
)

logger = get_logger(__name__)

# Plan generation prompt
PLAN_GENERATION_PROMPT = """You are a planning agent for document generation.

Based on the user's request and available context, generate a detailed execution plan.

User Request: {message}
Request Type: {request_type}
Document Type: {document_type}
Available Data Sources:
- MCP Domains: {enabled_mcps}
- Documents: {document_count} documents available for RAG
- Web Search: {web_search_status}

Page Context: {page_context}
Additional Instructions: {additional_prompt}

Generate a structured execution plan that includes:
1. Section outline - ordered list of sections with descriptions
2. Data requirements - what data to fetch from which sources
3. Tool usage plan - specific tools/queries to execute
4. Template strategy - whether to use existing template, modify one, or generate new
5. Complexity assessment

Respond in JSON format:
{{
    "sections": [
        {{
            "id": "section_id",
            "name": "Section Name",
            "description": "What this section should contain",
            "data_sources": ["mcp:deals", "rag:documents", "web:search"]
        }}
    ],
    "data_requirements": [
        {{
            "source": "mcp|rag|web",
            "domain": "deals|clients|null",
            "query": "get_opportunity_details|extract risk factors|search market trends",
            "priority": 1,
            "purpose": "Why this data is needed"
        }}
    ],
    "tool_usage_plan": [
        {{
            "tool": "deals:get_opportunity_details",
            "purpose": "Fetch opportunity metadata",
            "order": 1
        }}
    ],
    "template_strategy": "use_existing|modify|generate_new",
    "estimated_complexity": "simple|moderate|complex"
}}"""

# Default section structures by document type
DEFAULT_SECTIONS = {
    "investment_memo": [
        {"id": "executive_summary", "name": "Executive Summary", "description": "High-level overview and investment thesis"},
        {"id": "company_overview", "name": "Company Overview", "description": "Business model, history, and operations"},
        {"id": "market_analysis", "name": "Market Analysis", "description": "Industry trends, competitive landscape"},
        {"id": "financial_analysis", "name": "Financial Analysis", "description": "Historical performance, projections"},
        {"id": "investment_highlights", "name": "Investment Highlights", "description": "Key strengths and opportunities"},
        {"id": "risks", "name": "Risk Factors", "description": "Key risks and mitigations"},
        {"id": "recommendation", "name": "Recommendation", "description": "Investment recommendation and terms"},
    ],
    "prescreening": [
        {"id": "overview", "name": "Overview", "description": "Deal summary and key metrics"},
        {"id": "fit_assessment", "name": "Fit Assessment", "description": "Strategy and mandate fit analysis"},
        {"id": "preliminary_analysis", "name": "Preliminary Analysis", "description": "Initial financial and operational review"},
        {"id": "key_considerations", "name": "Key Considerations", "description": "Important factors to evaluate"},
        {"id": "recommendation", "name": "Recommendation", "description": "Pass/pursue recommendation with rationale"},
    ],
    "custom_report": [
        {"id": "introduction", "name": "Introduction", "description": "Context and purpose of the report"},
        {"id": "analysis", "name": "Analysis", "description": "Main analytical content"},
        {"id": "findings", "name": "Key Findings", "description": "Summary of findings"},
        {"id": "conclusion", "name": "Conclusion", "description": "Final thoughts and next steps"},
    ],
}


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


def build_plan_from_template(template_definition: dict, state: MultiAgentState) -> ExecutionPlan:
    """Build an execution plan from a template definition."""
    fields = template_definition.get("fields", {})
    agent_case = state.get("agent_case")
    tool_policy = state.get("tool_policy") or {}

    sections: list[SectionPlan] = []
    data_requirements: list[DataRequirement] = []

    for field_key, field_def in fields.items():
        # Handle nested fields (dict of fields)
        if isinstance(field_def, dict) and "description" not in field_def:
            # This is a nested structure - each key is a subfield
            for subfield_key, subfield_def in field_def.items():
                if isinstance(subfield_def, dict):
                    sections.append({
                        "id": f"{field_key}_{subfield_key}",
                        "name": subfield_key.replace("_", " ").title(),
                        "description": subfield_def.get("description", ""),
                        "data_sources": _infer_data_sources(subfield_def, tool_policy),
                        "template_section": subfield_def.get("instruction", ""),
                    })
        else:
            # Flat field
            sections.append({
                "id": field_key,
                "name": field_key.replace("_", " ").title(),
                "description": field_def.get("description", "") if isinstance(field_def, dict) else "",
                "data_sources": _infer_data_sources(field_def, tool_policy) if isinstance(field_def, dict) else ["mcp:deals"],
                "template_section": field_def.get("instruction", "") if isinstance(field_def, dict) else "",
            })

    # Add basic data requirement for MCP
    if "deals" in tool_policy.get("enabled_mcps", []):
        data_requirements.append({
            "source": "mcp",
            "domain": "deals",
            "query": "get_opportunity_details",
            "priority": 1,
            "purpose": "Fetch opportunity context",
        })

    # Determine complexity based on field count
    complexity = "simple" if len(sections) <= 3 else ("moderate" if len(sections) <= 6 else "complex")

    return {
        "plan_id": str(uuid.uuid4())[:8],
        "sections": sections,
        "data_requirements": data_requirements,
        "tool_usage_plan": [{"tool": "deals:get_opportunity_details", "purpose": "Get opportunity data", "order": 1}],
        "template_strategy": "use_existing",
        "estimated_complexity": complexity,
        "created_at": datetime.utcnow().isoformat(),
    }


def _infer_data_sources(field_def: dict, tool_policy: dict) -> list[str]:
    """Infer data sources based on field instruction and available tools."""
    instruction = field_def.get("instruction", "").lower()
    sources = []

    # Check for MCP data needs
    if any(keyword in instruction for keyword in ["extract", "opportunity", "company", "mcp", "deal"]):
        sources.append("mcp:deals")

    # Check for RAG data needs
    if any(keyword in instruction for keyword in ["document", "rag", "file", "extract from"]):
        sources.append("rag:documents")

    # Check for web search needs
    if any(keyword in instruction for keyword in ["search", "web", "market", "industry"]) and tool_policy.get("web_search_enabled"):
        sources.append("web:search")

    # Default to MCP if no sources inferred
    if not sources:
        sources.append("mcp:deals")

    return sources


async def generate_plan(state: MultiAgentState) -> dict:
    """
    Generate the execution plan for document generation.

    This node:
    1. Checks for template_definition and uses it if provided
    2. Otherwise, analyzes the request and available data sources
    3. Generates a structured section outline
    4. Plans data requirements and tool usage
    5. Determines template strategy
    """
    logger.info("Generating execution plan")

    # Emit phase started event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_started",
            {"phase": "planning", "message": "Creating execution plan..."},
            "planning",
        )

    intent_analysis = state.get("intent_analysis") or {}
    request_type = intent_analysis.get("request_type", "ask")
    document_type = intent_analysis.get("document_type") or "custom_report"
    tool_policy = state.get("tool_policy") or {}
    agent_case = state.get("agent_case")

    # Check for template definition first
    template_definition = state.get("template_definition")
    if template_definition and agent_case in ["create", "fill"]:
        logger.info("Building plan from template definition")
        plan = build_plan_from_template(template_definition, state)

        # Emit plan generated event
        if sse_callback := get_callback_for_state(state):
            await sse_callback(
                "plan_generated",
                {
                    "plan_id": plan["plan_id"],
                    "sections_count": len(plan["sections"]),
                    "complexity": plan["estimated_complexity"],
                    "sections": [{"id": s["id"], "name": s["name"]} for s in plan["sections"]],
                    "from_template": True,
                },
                "planning",
            )

        return {
            "execution_plan": plan,
            "template_strategy": plan["template_strategy"],
            "sections_total": len(plan["sections"]),
        }

    user_message = get_last_human_message(state)
    page_context = state.get("page_context") or {}
    additional_prompt = state.get("additional_prompt") or ""

    # Check for clarification context and modification input
    working_memory = state.get("working_memory") or {}
    clarification_context = working_memory.get("clarification_context", "")
    modification_request = working_memory.get("plan_modification_request") or state.get("plan_modification_input", "")

    # Build additional context from clarification and modifications
    additional_context = ""
    if clarification_context:
        additional_context += f"\n\nUser clarification: {clarification_context}"
    if modification_request:
        additional_context += f"\n\nModification request: {modification_request}"

    # Calculate document count
    document_ids = state.get("document_ids", [])
    selected_docs = state.get("selected_docs") or {}
    doc_count = len(document_ids) + len(selected_docs.get("doc_ids", []))

    # Build prompt
    prompt = PLAN_GENERATION_PROMPT.format(
        message=user_message + additional_context,
        request_type=request_type,
        document_type=document_type,
        enabled_mcps=", ".join(tool_policy.get("enabled_mcps", ["deals"])),
        document_count=doc_count,
        web_search_status="Enabled" if tool_policy.get("web_search_enabled") else "Disabled",
        page_context=json.dumps(page_context, indent=2) if page_context else "None",
        additional_prompt=additional_prompt or "None",
    )

    # Call LLM for plan generation
    llm = get_llm(temperature=0.3)
    try:
        response = await llm.ainvoke(prompt)

        # Parse JSON response
        response_text = response.content.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        plan_data = json.loads(response_text)

        # Build typed plan
        sections: list[SectionPlan] = []
        for s in plan_data.get("sections", []):
            sections.append({
                "id": s.get("id", f"section_{len(sections)}"),
                "name": s["name"],
                "description": s.get("description", ""),
                "data_sources": s.get("data_sources", []),
                "template_section": None,
            })

        data_requirements: list[DataRequirement] = []
        for d in plan_data.get("data_requirements", []):
            data_requirements.append({
                "source": d.get("source", "mcp"),
                "domain": d.get("domain"),
                "query": d.get("query", ""),
                "priority": d.get("priority", 1),
                "purpose": d.get("purpose", ""),
            })

        tool_usage: list[ToolUsage] = []
        for t in plan_data.get("tool_usage_plan", []):
            tool_usage.append({
                "tool": t.get("tool", ""),
                "purpose": t.get("purpose", ""),
                "order": t.get("order", 1),
            })

        plan: ExecutionPlan = {
            "plan_id": str(uuid.uuid4())[:8],
            "sections": sections,
            "data_requirements": data_requirements,
            "tool_usage_plan": tool_usage,
            "template_strategy": plan_data.get("template_strategy", "generate_new"),
            "estimated_complexity": plan_data.get("estimated_complexity", "moderate"),
            "created_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Plan generated: {len(sections)} sections, {len(data_requirements)} data reqs, "
            f"complexity={plan['estimated_complexity']}"
        )

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse plan: {e}, using default structure")

        # Use default sections for the document type
        default_sections = DEFAULT_SECTIONS.get(document_type, DEFAULT_SECTIONS["custom_report"])
        sections = []
        for s in default_sections:
            sections.append({
                "id": s["id"],
                "name": s["name"],
                "description": s["description"],
                "data_sources": ["mcp:deals", "rag:documents"] if doc_count > 0 else ["mcp:deals"],
                "template_section": None,
            })

        plan: ExecutionPlan = {
            "plan_id": str(uuid.uuid4())[:8],
            "sections": sections,
            "data_requirements": [
                {"source": "mcp", "domain": "deals", "query": "get_opportunity_details", "priority": 1, "purpose": "Fetch opportunity context"},
            ],
            "tool_usage_plan": [
                {"tool": "deals:get_opportunity_details", "purpose": "Get opportunity data", "order": 1},
            ],
            "template_strategy": "generate_new",
            "estimated_complexity": "moderate",
            "created_at": datetime.utcnow().isoformat(),
        }

    # Emit plan generated event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "plan_generated",
            {
                "plan_id": plan["plan_id"],
                "sections_count": len(plan["sections"]),
                "complexity": plan["estimated_complexity"],
                "sections": [{"id": s["id"], "name": s["name"]} for s in plan["sections"]],
            },
            "planning",
        )

    return {
        "execution_plan": plan,
        "template_strategy": plan["template_strategy"],
        "sections_total": len(plan["sections"]),
    }


async def validate_plan(state: MultiAgentState) -> dict:
    """
    Validate the execution plan for feasibility.

    This node:
    1. Checks that required data sources are available
    2. Validates section structure
    3. Ensures tools are enabled
    """
    logger.info("Validating execution plan")

    plan = state.get("execution_plan")
    if not plan:
        logger.warning("No execution plan to validate")
        return {}

    tool_policy = state.get("tool_policy") or {}
    enabled_mcps = tool_policy.get("enabled_mcps", [])
    web_search_enabled = tool_policy.get("web_search_enabled", False)

    issues = []

    # Validate data requirements
    for req in plan.get("data_requirements", []):
        source = req.get("source")
        domain = req.get("domain")

        if source == "mcp" and domain and domain not in enabled_mcps:
            issues.append(f"MCP domain '{domain}' not enabled")

        if source == "web" and not web_search_enabled:
            issues.append("Web search required but not enabled")

    # Validate sections
    sections = plan.get("sections", [])
    if not sections:
        issues.append("No sections defined in plan")

    # Log validation results
    if issues:
        logger.warning(f"Plan validation issues: {issues}")
    else:
        logger.info("Plan validation passed")

    # Emit phase completed event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_completed",
            {
                "phase": "planning",
                "valid": len(issues) == 0,
                "issues": issues,
            },
            "planning",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "planning",
        "to_phase": "confirmation",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": "Plan ready for confirmation" if not issues else f"Issues: {issues}",
    })

    return {
        "phase_history": phase_history,
        "current_phase": "confirmation",
        "updated_at": datetime.utcnow(),
    }
