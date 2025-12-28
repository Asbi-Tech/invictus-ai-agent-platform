"""Summary handler nodes for generating LLM-powered user summaries."""

import json
from datetime import datetime

from langchain_openai import AzureChatOpenAI

from common.callback_registry import get_callback_for_state
from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState

logger = get_logger(__name__)


# Prompt for CREATE mode summaries
SUMMARY_PROMPT_CREATE = """You are a helpful assistant summarizing the results of a document generation task.

Document Generated:
- Title: {title}
- Type: {artifact_type}
- Sections: {sections_count}
- Word Count: ~{word_count}

Data Sources Used:
- MCP sources: {mcp_count} queries (domains: {mcp_domains})
- RAG documents: {rag_count} documents searched
- Web search: {web_count} results

Review Results:
- Quality Score: {coherence_score}%
- Issues Found: {issues_count}
{issues_list}

Write a 2-3 sentence summary for the user that:
1. Confirms what was created
2. Highlights key content or insights from the document
3. Notes any issues or gaps they should review (if any)

Be concise and helpful. Focus on what matters to the user. Do not use bullet points - write in flowing prose."""


# Prompt for EDIT mode summaries
SUMMARY_PROMPT_EDIT = """You are summarizing edit instructions generated for a document.

Original Document: {title}
Edit Instructions: {instruction_count}
- Additions: {add_count}
- Modifications: {modify_count}
- Removals: {remove_count}

Changes Summary:
{changes_summary}

Write a 2-3 sentence summary that:
1. Confirms what changes were prepared
2. Highlights the most significant changes
3. Notes any sections that need user attention

Be concise and helpful. Do not use bullet points - write in flowing prose."""


# Prompt for FILL mode summaries
SUMMARY_PROMPT_FILL = """You are summarizing a template filling task.

Template Fields: {total_fields}
Fields Filled: {filled_count}
Fields Skipped: {skipped_count}

Filled Values:
{filled_summary}

Missing/Skipped Fields:
{missing_fields}

Write a 2-3 sentence summary that:
1. Confirms how many fields were filled
2. Highlights key information extracted
3. Notes any fields that couldn't be filled and why (if any)

Be concise and helpful. Do not use bullet points - write in flowing prose."""


def get_llm(temperature: float = 0.3) -> AzureChatOpenAI:
    """Get Azure OpenAI LLM instance for summary generation."""
    settings = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=temperature,
    )


def build_create_summary_prompt(state: MultiAgentState) -> str:
    """Build the summary prompt for CREATE mode."""
    artifacts = state.get("artifacts", [])
    artifact = artifacts[-1] if artifacts else {}

    # Extract artifact info
    title = artifact.get("title", "Untitled Document")
    artifact_type = artifact.get("artifact_type", "document")
    content = artifact.get("content", "")
    word_count = len(content.split()) if content else 0

    # Count sections from section_assignments
    section_assignments = state.get("section_assignments", [])
    sections_count = len(section_assignments)

    # Data source stats
    mcp_data = state.get("mcp_data", {})
    rag_data = state.get("rag_data", {})
    web_data = state.get("web_data", {})

    mcp_count = len(mcp_data)
    mcp_domains = ", ".join(mcp_data.keys()) if mcp_data else "none"
    rag_count = len(rag_data)
    web_count = len(web_data)

    # Review results
    review_result = state.get("review_result") or {}
    coherence_score = review_result.get("coherence_score", 0) * 100
    issues = review_result.get("issues", [])
    issues_count = len(issues)

    # Format issues list
    if issues:
        issues_list = "\n".join(
            f"  - [{issue.get('severity', 'medium')}] {issue.get('description', '')}"
            for issue in issues[:5]  # Limit to 5 issues
        )
        if issues_count > 5:
            issues_list += f"\n  ... and {issues_count - 5} more"
    else:
        issues_list = "  No significant issues found."

    return SUMMARY_PROMPT_CREATE.format(
        title=title,
        artifact_type=artifact_type,
        sections_count=sections_count,
        word_count=word_count,
        mcp_count=mcp_count,
        mcp_domains=mcp_domains,
        rag_count=rag_count,
        web_count=web_count,
        coherence_score=coherence_score,
        issues_count=issues_count,
        issues_list=issues_list,
    )


def build_edit_summary_prompt(state: MultiAgentState) -> str:
    """Build the summary prompt for EDIT mode."""
    edit_instructions = state.get("edit_instructions", [])
    current_artifact = state.get("current_artifact") or {}

    title = current_artifact.get("title", "Document")
    instruction_count = len(edit_instructions)

    # Count by operation type
    add_count = sum(1 for i in edit_instructions if i.get("operation") == "add")
    modify_count = sum(1 for i in edit_instructions if i.get("operation") == "modify")
    remove_count = sum(1 for i in edit_instructions if i.get("operation") == "remove")

    # Build changes summary
    changes_lines = []
    for instr in edit_instructions[:5]:  # Limit to 5
        op = instr.get("operation", "modify")
        section = instr.get("section_title") or instr.get("section_id", "section")
        reasoning = instr.get("reasoning", "")
        changes_lines.append(f"  - {op.upper()} {section}: {reasoning[:100]}")

    changes_summary = "\n".join(changes_lines) if changes_lines else "  No changes."
    if instruction_count > 5:
        changes_summary += f"\n  ... and {instruction_count - 5} more changes"

    return SUMMARY_PROMPT_EDIT.format(
        title=title,
        instruction_count=instruction_count,
        add_count=add_count,
        modify_count=modify_count,
        remove_count=remove_count,
        changes_summary=changes_summary,
    )


def build_fill_summary_prompt(state: MultiAgentState) -> str:
    """Build the summary prompt for FILL mode."""
    filled_fields = state.get("filled_fields", {})
    fields_to_fill = state.get("fields_to_fill", [])
    template_def = state.get("template_definition") or {}

    # Count fields
    total_fields = len(fields_to_fill) if fields_to_fill else len(template_def.get("fields", {}))

    # Count filled vs missing
    filled_count = count_filled_fields(filled_fields)
    skipped_count = total_fields - filled_count

    # Build filled summary (show first 5 fields)
    filled_lines = []
    for key, value in list(flatten_dict(filled_fields).items())[:5]:
        if value is not None:
            value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            filled_lines.append(f"  - {key}: {value_str}")

    filled_summary = "\n".join(filled_lines) if filled_lines else "  No fields filled."
    if filled_count > 5:
        filled_summary += f"\n  ... and {filled_count - 5} more fields"

    # Identify missing fields
    missing = []
    for key, value in flatten_dict(filled_fields).items():
        if value is None:
            missing.append(f"  - {key}")

    missing_fields = "\n".join(missing[:5]) if missing else "  All fields filled successfully."
    if len(missing) > 5:
        missing_fields += f"\n  ... and {len(missing) - 5} more"

    return SUMMARY_PROMPT_FILL.format(
        total_fields=total_fields,
        filled_count=filled_count,
        skipped_count=skipped_count,
        filled_summary=filled_summary,
        missing_fields=missing_fields,
    )


def count_filled_fields(obj: dict, count: int = 0) -> int:
    """Count non-None values in a nested dict."""
    for value in obj.values():
        if isinstance(value, dict):
            count = count_filled_fields(value, count)
        elif value is not None:
            count += 1
    return count


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dict for display."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


async def generate_summary(state: MultiAgentState) -> dict:
    """
    Generate an LLM-powered summary for the user.

    This node:
    1. Determines the agent case (create, edit, fill)
    2. Builds an appropriate prompt with execution details
    3. Calls LLM to generate a human-friendly summary
    4. Returns the summary for inclusion in the final response
    """
    logger.info("Generating user summary")

    agent_case = state.get("agent_case")

    # Emit thinking event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "thinking",
            {"message": "Preparing summary of completed work..."},
            "summary_handler",
        )

    # Build prompt based on agent case
    if agent_case == "create":
        prompt = build_create_summary_prompt(state)
    elif agent_case == "edit":
        prompt = build_edit_summary_prompt(state)
    elif agent_case == "fill":
        prompt = build_fill_summary_prompt(state)
    else:
        # Fallback for unknown cases
        logger.warning(f"Unknown agent_case: {agent_case}, using generic summary")
        return {
            "summary_for_user": "Task completed successfully.",
            "updated_at": datetime.utcnow(),
        }

    try:
        # Call LLM for summary generation
        llm = get_llm(temperature=0.3)
        response = await llm.ainvoke(prompt)
        summary = response.content.strip()

        logger.info(f"Generated summary ({len(summary)} chars) for {agent_case} mode")

        # Emit summary generated event
        if sse_callback := get_callback_for_state(state):
            await sse_callback(
                "phase_completed",
                {"phase": "summary", "summary_length": len(summary)},
                "summary_handler",
            )

        return {
            "summary_for_user": summary,
            "updated_at": datetime.utcnow(),
        }

    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        # Fallback to simple summary
        artifacts = state.get("artifacts", [])
        if artifacts:
            title = artifacts[-1].get("title", "document")
            fallback = f"I've created the {title}."
        else:
            fallback = "Task completed."

        return {
            "summary_for_user": fallback,
            "updated_at": datetime.utcnow(),
        }
