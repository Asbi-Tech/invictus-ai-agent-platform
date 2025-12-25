"""Generate edit instructions for artifact modification."""

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


EDIT_INSTRUCTIONS_PROMPT = """You are an AI assistant that generates precise edit instructions for documents.

Current artifact type: {artifact_type}
Current artifact title: {artifact_title}

Current artifact sections:
{artifact_sections}

User's edit request: {user_message}
Additional context from user: {additional_prompt}

Gathered data:
{context}

Generate edit instructions as a JSON object with an "instructions" array. Each instruction should have:
- operation: "add", "remove", or "modify"
- section_id: identifier for the section (e.g., "section_1") or null for new sections
- section_title: human-readable section name
- position: "before", "after", or "replace" (for add/modify operations)
- content: the new or modified content in markdown format
- reasoning: brief explanation of why this change is needed

Focus on making targeted, precise changes based on the user's request and the gathered context.
Only include changes that are directly requested or clearly necessary.

Respond with valid JSON only, no other text."""


def format_sections(sections: list[dict]) -> str:
    """Format sections for prompt."""
    if not sections:
        return "No sections parsed"

    parts = []
    for section in sections:
        level = section.get("level", 0)
        prefix = "#" * level if level > 0 else ""
        parts.append(f"{section.get('section_id', 'unknown')}: {prefix} {section.get('title', 'Untitled')}")
        content_preview = section.get("content", "")[:200]
        if content_preview:
            parts.append(f"   Preview: {content_preview}...")
    return "\n".join(parts)


def format_context(working_memory: dict) -> str:
    """Format gathered context for prompt."""
    parts = []

    if opp := working_memory.get("opportunity_data"):
        parts.append(f"Opportunity: {opp.get('name', 'Unknown')}")
        parts.append(f"  Status: {opp.get('status', 'Unknown')}")
        parts.append(f"  Stage: {opp.get('stage', 'Unknown')}")
        parts.append(f"  Sector: {opp.get('sector', 'Unknown')}")

    if prescreening := working_memory.get("prescreening_data"):
        parts.append(f"\nPrescreening: {prescreening.get('recommendation', 'Unknown')}")
        if findings := prescreening.get("key_findings"):
            parts.append(f"  Key findings: {', '.join(findings[:3])}")

    if memo := working_memory.get("investment_memo_data"):
        parts.append(f"\nExisting memo version: {memo.get('version', 'Unknown')}")

    if rag := working_memory.get("rag_results"):
        parts.append("\nDocument context:")
        for field, value in rag.items():
            if value:
                parts.append(f"  {field}: {str(value)[:200]}")

    return "\n".join(parts) if parts else "No additional context gathered"


async def generate_edit_instructions(state: dict[str, Any]) -> dict[str, Any]:
    """
    Generate diff-based edit instructions for the artifact.

    This node uses the LLM to generate structured edit instructions
    based on the user's request and gathered context.

    Args:
        state: Current graph state

    Returns:
        Updated state with edit instructions
    """
    current_artifact = state.get("current_artifact", {})
    messages = state.get("messages", [])
    additional_prompt = state.get("additional_prompt", "")
    working_memory = state.get("working_memory", {})
    sse_callback = state.get("sse_callback")

    # Emit thinking event
    if sse_callback:
        await sse_callback(
            "thinking",
            "Generating edit recommendations...",
            "generate_edit_instructions",
        )

    # Get user message
    user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = str(msg.content)
            break

    # Get artifact sections
    sections = working_memory.get("artifact_sections", [])
    artifact_type = working_memory.get("artifact_type", "document")
    artifact_title = working_memory.get("artifact_title", "Untitled")

    # Format prompt
    prompt = EDIT_INSTRUCTIONS_PROMPT.format(
        artifact_type=artifact_type,
        artifact_title=artifact_title,
        artifact_sections=format_sections(sections),
        user_message=user_message,
        additional_prompt=additional_prompt or "None provided",
        context=format_context(working_memory),
    )

    logger.info(
        "Generating edit instructions",
        artifact_type=artifact_type,
        section_count=len(sections),
        has_context=bool(working_memory.get("opportunity_data")),
    )

    try:
        # Call LLM with JSON mode
        llm = AzureChatOpenAI(
            deployment_name=settings.azure_openai_deployment_name,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            temperature=0.3,  # Lower temperature for precise edits
        )

        # Note: response_format requires newer API versions
        response = await llm.ainvoke(prompt)
        response_text = str(response.content)

        # Parse JSON response
        # Handle potential markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        instructions_data = json.loads(response_text.strip())
        instructions = instructions_data.get("instructions", [])

        # Stream individual instructions if callback available
        if sse_callback:
            for instruction in instructions:
                await sse_callback(
                    "edit_instruction",
                    instruction,
                    "generate_edit_instructions",
                )

        logger.info(
            "Generated edit instructions",
            instruction_count=len(instructions),
        )

        # Create summary message
        summary_parts = []
        for inst in instructions:
            op = inst.get("operation", "modify")
            section = inst.get("section_title", "section")
            summary_parts.append(f"- {op.title()} {section}")

        summary = f"Generated {len(instructions)} edit instructions:\n" + "\n".join(summary_parts)

        return {
            "edit_instructions": instructions,
            "messages": [AIMessage(content=summary)],
        }

    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON", error=str(e))
        return {
            "edit_instructions": [],
            "messages": [AIMessage(content="Failed to generate edit instructions. Please try again.")],
            "error_count": state.get("error_count", 0) + 1,
        }

    except Exception as e:
        logger.error("Failed to generate edit instructions", error=str(e))
        return {
            "edit_instructions": [],
            "messages": [AIMessage(content=f"Error generating edit instructions: {str(e)}")],
            "error_count": state.get("error_count", 0) + 1,
        }
