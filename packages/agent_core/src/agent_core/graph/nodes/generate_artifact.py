"""Generate new artifact for create mode."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


ARTIFACT_GENERATION_PROMPT = """You are an expert financial analyst and document author. Generate a high-quality {artifact_type} based on the following context.

User request: {user_message}
Additional context from user: {additional_prompt}

Available data:
{context}

Guidelines:
1. Use professional financial language appropriate for institutional investors
2. Structure the document with clear sections using markdown headers
3. Include specific data points and metrics where available
4. Be concise but comprehensive
5. Include relevant risk factors and considerations
6. Use bullet points for key highlights

Generate the {artifact_type} content in markdown format."""


def determine_artifact_type(state: dict[str, Any]) -> str:
    """Determine the type of artifact to generate based on context."""
    messages = state.get("messages", [])
    user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = str(msg.content).lower()
            break

    if "memo" in user_message or "investment memo" in user_message:
        return "investment_memo"
    elif "report" in user_message:
        return "report"
    elif "summary" in user_message or "summarize" in user_message:
        return "summary"
    elif "analysis" in user_message:
        return "analysis"
    elif "strategy" in user_message:
        return "strategy_doc"
    else:
        return "document"


def generate_title(state: dict[str, Any]) -> str:
    """Generate a title for the artifact."""
    working_memory = state.get("working_memory", {})
    artifact_type = determine_artifact_type(state)

    opp_name = None
    if opp := working_memory.get("opportunity_data"):
        opp_name = opp.get("name")

    type_titles = {
        "investment_memo": "Investment Memo",
        "report": "Report",
        "summary": "Summary",
        "analysis": "Analysis",
        "strategy_doc": "Strategy Document",
        "document": "Document",
    }

    base_title = type_titles.get(artifact_type, "Document")

    if opp_name:
        return f"{opp_name} - {base_title}"
    return f"{base_title} - {datetime.utcnow().strftime('%Y-%m-%d')}"


def format_context(working_memory: dict) -> str:
    """Format gathered context for prompt."""
    parts = []

    if opp := working_memory.get("opportunity_data"):
        parts.append("## Opportunity Details")
        parts.append(f"- Name: {opp.get('name', 'Unknown')}")
        parts.append(f"- Type: {opp.get('type', 'Unknown')}")
        parts.append(f"- Status: {opp.get('status', 'Unknown')}")
        parts.append(f"- Stage: {opp.get('stage', 'Unknown')}")
        parts.append(f"- Sector: {opp.get('sector', 'Unknown')}")
        parts.append(f"- Geography: {opp.get('geography', 'Unknown')}")
        parts.append(f"- Target Raise: ${opp.get('target_raise', 0):,.0f}")
        parts.append(f"- Current Committed: ${opp.get('current_committed', 0):,.0f}")
        parts.append(f"- Manager: {opp.get('manager', 'Unknown')}")
        parts.append(f"- Management Fee: {opp.get('management_fee', 'N/A')}")
        parts.append(f"- Carry: {opp.get('carry', 'N/A')}")
        if desc := opp.get("description"):
            parts.append(f"- Description: {desc}")

    if prescreening := working_memory.get("prescreening_data"):
        parts.append("\n## Prescreening Report")
        parts.append(f"- Recommendation: {prescreening.get('recommendation', 'Unknown')}")
        parts.append(f"- Risk Rating: {prescreening.get('risk_rating', 'Unknown')}")
        if summary := prescreening.get("executive_summary"):
            parts.append(f"- Executive Summary: {summary}")
        if findings := prescreening.get("key_findings"):
            parts.append("- Key Findings:")
            for f in findings:
                parts.append(f"  - {f}")
        if concerns := prescreening.get("concerns"):
            parts.append("- Concerns:")
            for c in concerns:
                parts.append(f"  - {c}")
        if thesis := prescreening.get("investment_thesis"):
            parts.append(f"- Investment Thesis: {thesis}")
        if fin := prescreening.get("financial_highlights"):
            parts.append("- Financial Highlights:")
            for k, v in fin.items():
                parts.append(f"  - {k}: {v}")

    if memo := working_memory.get("investment_memo_data"):
        parts.append("\n## Existing Investment Memo")
        parts.append(f"- Version: {memo.get('version', 'Unknown')}")
        if sections := memo.get("sections"):
            for section_name, section_content in sections.items():
                parts.append(f"- {section_name}: {str(section_content)[:300]}...")

    if activity := working_memory.get("activity_data"):
        activities = activity.get("activities", [])
        if activities:
            parts.append("\n## Recent Activity")
            for act in activities[:5]:
                parts.append(f"- {act.get('date', 'Unknown')}: {act.get('action', 'Unknown')}")

    if rag := working_memory.get("rag_results"):
        parts.append("\n## Document Extracts")
        for field, value in rag.items():
            if value:
                parts.append(f"- {field}: {str(value)[:500]}")

    return "\n".join(parts) if parts else "No additional context available."


async def generate_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """
    Generate a new artifact from gathered context.

    This node uses the LLM to generate structured content
    based on the gathered context and user request.

    Args:
        state: Current graph state

    Returns:
        Updated state with generated artifact
    """
    messages = state.get("messages", [])
    additional_prompt = state.get("additional_prompt", "")
    working_memory = state.get("working_memory", {})
    sse_callback = state.get("sse_callback")

    # Emit thinking event
    if sse_callback:
        await sse_callback(
            "thinking",
            "Generating content...",
            "generate_artifact",
        )

    # Get user message
    user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = str(msg.content)
            break

    # Determine artifact type and title
    artifact_type = determine_artifact_type(state)
    title = generate_title(state)

    # Format prompt
    prompt = ARTIFACT_GENERATION_PROMPT.format(
        artifact_type=artifact_type.replace("_", " "),
        user_message=user_message,
        additional_prompt=additional_prompt or "None provided",
        context=format_context(working_memory),
    )

    logger.info(
        "Generating artifact",
        artifact_type=artifact_type,
        title=title,
        has_opportunity=bool(working_memory.get("opportunity_data")),
        has_prescreening=bool(working_memory.get("prescreening_data")),
    )

    try:
        # Call LLM
        llm = AzureChatOpenAI(
            deployment_name=settings.azure_openai_deployment_name,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            temperature=0.7,  # Higher temperature for creative content
        )

        response = await llm.ainvoke(prompt)
        content = str(response.content)

        # Collect citations from context
        citations = []
        if rag_citations := working_memory.get("rag_citations"):
            citations.extend(rag_citations)

        # Create artifact
        artifact = {
            "artifact_id": str(uuid4()),
            "artifact_type": artifact_type,
            "title": title,
            "content": content,
            "version": 1,
            "citations": citations,
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "opportunity_id": working_memory.get("opportunity_data", {}).get("opportunity_id"),
                "has_prescreening": bool(working_memory.get("prescreening_data")),
            },
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Emit artifact update if callback available
        if sse_callback:
            await sse_callback(
                "artifact_update",
                artifact,
                "generate_artifact",
            )

        logger.info(
            "Generated artifact",
            artifact_id=artifact["artifact_id"],
            artifact_type=artifact_type,
            content_length=len(content),
        )

        return {
            "artifacts": [artifact],
            "current_artifact_id": artifact["artifact_id"],
            "messages": [AIMessage(content=f"Generated {artifact_type.replace('_', ' ')}: {title}")],
        }

    except Exception as e:
        logger.error("Failed to generate artifact", error=str(e))
        return {
            "artifacts": [],
            "messages": [AIMessage(content=f"Error generating artifact: {str(e)}")],
            "error_count": state.get("error_count", 0) + 1,
        }
