"""Review nodes for coherence checking and validation."""

import json
from datetime import datetime

from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState, ReviewResult, ReviewIssue

logger = get_logger(__name__)

REVIEW_PROMPT = """You are a document reviewer. Review the following document for:
1. Coherence - Does the document flow logically?
2. Consistency - Is terminology and tone consistent throughout?
3. Citations - Are claims properly supported by sources?
4. Completeness - Are all sections adequately developed?
5. Redundancy - Is there unnecessary repetition?

Document:
{document_content}

Provide your review in JSON format:
{{
    "coherence_score": 0.0-1.0,
    "issues": [
        {{
            "issue_type": "coherence|citation|terminology|redundancy|completeness",
            "severity": "low|medium|high",
            "section_id": "section_id or null",
            "description": "Description of the issue",
            "suggestion": "How to fix it"
        }}
    ],
    "suggestions": ["General improvement suggestion"],
    "approved": true/false
}}"""


def get_llm(temperature: float = 0.1) -> AzureChatOpenAI:
    """Get Azure OpenAI LLM instance."""
    settings = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=temperature,
    )


async def check_coherence(state: MultiAgentState) -> dict:
    """
    Check document coherence and consistency.

    This node analyzes the generated document for quality issues.
    """
    logger.info("Checking document coherence")

    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "review_started",
            {"message": "Reviewing document quality..."},
            "review",
        )

    # Get the generated artifact
    artifacts = state.get("artifacts", [])
    if not artifacts:
        logger.warning("No artifacts to review")
        return {
            "review_result": {
                "coherence_score": 1.0,
                "issues": [],
                "suggestions": [],
                "approved": True,
            }
        }

    artifact = artifacts[-1]  # Latest artifact
    content = artifact.get("content", "")

    # Call LLM for review
    llm = get_llm(temperature=0.1)
    prompt = REVIEW_PROMPT.format(document_content=content[:8000])

    try:
        response = await llm.ainvoke(prompt)

        # Parse response
        response_text = response.content.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        review_data = json.loads(response_text)

        # Build typed review result
        issues: list[ReviewIssue] = []
        for issue in review_data.get("issues", []):
            issues.append({
                "issue_type": issue.get("issue_type", "coherence"),
                "severity": issue.get("severity", "low"),
                "section_id": issue.get("section_id"),
                "description": issue.get("description", ""),
                "suggestion": issue.get("suggestion"),
            })

        review_result: ReviewResult = {
            "coherence_score": review_data.get("coherence_score", 0.8),
            "issues": issues,
            "suggestions": review_data.get("suggestions", []),
            "approved": review_data.get("approved", True),
        }

        logger.info(
            f"Review complete: score={review_result['coherence_score']}, "
            f"issues={len(issues)}, approved={review_result['approved']}"
        )

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse review: {e}, using defaults")
        review_result: ReviewResult = {
            "coherence_score": 0.8,
            "issues": [],
            "suggestions": [],
            "approved": True,
        }

    return {"review_result": review_result}


async def check_citations(state: MultiAgentState) -> dict:
    """
    Validate citations and source references.

    This node checks that claims are properly attributed.
    """
    logger.info("Checking citations")

    review_result = state.get("review_result") or {}
    artifacts = state.get("artifacts", [])
    source_ledger = state.get("source_ledger") or {}

    issues = list(review_result.get("issues", []))

    if artifacts:
        artifact = artifacts[-1]
        citations = artifact.get("citations", [])

        if len(citations) < 2:
            issues.append({
                "issue_type": "citation",
                "severity": "medium",
                "section_id": None,
                "description": "Document has few source citations",
                "suggestion": "Consider adding more source references",
            })

    # Update review result
    updated_review: ReviewResult = {
        **review_result,
        "issues": issues,
    }

    return {"review_result": updated_review}


async def generate_suggestions(state: MultiAgentState) -> dict:
    """
    Generate improvement suggestions based on review.

    This node provides actionable feedback.
    """
    logger.info("Generating suggestions")

    review_result = state.get("review_result") or {}
    issues = review_result.get("issues", [])
    suggestions = list(review_result.get("suggestions", []))

    # Add suggestions based on issues
    high_severity = [i for i in issues if i.get("severity") == "high"]
    if high_severity:
        suggestions.insert(0, "Address high-priority issues before finalizing")

    # Emit review issue events
    if sse_callback := state.get("sse_callback"):
        for issue in issues[:5]:  # Emit up to 5 issues
            await sse_callback(
                "review_issue_found",
                issue,
                "review",
            )

    # Update review result
    updated_review: ReviewResult = {
        **review_result,
        "suggestions": suggestions,
    }

    # Emit review completed
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "review_completed",
            {
                "coherence_score": updated_review.get("coherence_score", 0.8),
                "issues_count": len(issues),
                "approved": updated_review.get("approved", True),
            },
            "review",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "review",
        "to_phase": "source_mapping",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Review complete: {len(issues)} issues found",
    })

    logger.info(f"Review finalized: {len(issues)} issues, {len(suggestions)} suggestions")

    return {
        "review_result": updated_review,
        "phase_history": phase_history,
        "current_phase": "source_mapping",
        "updated_at": datetime.utcnow(),
    }
