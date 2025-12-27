"""Synthesis nodes for data normalization and insight generation."""

import json
from datetime import datetime
from typing import Any

from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState, SynthesizedInsights

logger = get_logger(__name__)

SYNTHESIS_PROMPT = """You are a data synthesis agent. Analyze the following data from multiple sources and generate insights.

MCP Data (Structured):
{mcp_data}

RAG Data (Documents):
{rag_data}

Web Data:
{web_data}

User Question: {user_question}
Document Type: {document_type}

Synthesize this data and provide:
1. Normalized data - key facts organized by category
2. Key insights - important observations and findings
3. Data gaps - missing information that would be valuable
4. Contradictions - conflicting information from different sources
5. Confidence scores - reliability of each data point (0-1)

Respond in JSON format:
{{
    "normalized_data": {{
        "category_name": {{
            "key": "value"
        }}
    }},
    "insights": [
        {{
            "insight": "Description of insight",
            "source": "mcp|rag|web|synthesis",
            "importance": "high|medium|low"
        }}
    ],
    "data_gaps": ["Missing information 1", "Missing information 2"],
    "contradictions": [
        {{
            "topic": "What is conflicting",
            "source_1": "First perspective",
            "source_2": "Second perspective"
        }}
    ],
    "confidence_scores": {{
        "data_point": 0.85
    }}
}}"""


def get_llm(temperature: float = 0.2) -> AzureChatOpenAI:
    """Get Azure OpenAI LLM instance."""
    settings = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=temperature,
    )


async def normalize_data(state: MultiAgentState) -> dict:
    """
    Normalize and standardize data from all sources.

    This node prepares data for synthesis by cleaning and organizing it.
    """
    logger.info("Normalizing data")

    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "synthesis_started",
            {"message": "Analyzing and synthesizing data..."},
            "synthesis",
        )

    # Extract data from state
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}

    # Normalize MCP data
    normalized_mcp = {}
    if opportunity := mcp_data.get("opportunity"):
        normalized_mcp["opportunity"] = {
            "name": opportunity.get("name"),
            "status": opportunity.get("status"),
            "sector": opportunity.get("sector"),
            "target_raise": opportunity.get("target_raise"),
            "investment_stage": opportunity.get("investment_stage"),
        }
    if prescreening := mcp_data.get("prescreening"):
        normalized_mcp["prescreening"] = {
            "recommendation": prescreening.get("recommendation"),
            "risk_rating": prescreening.get("risk_rating"),
            "key_findings": prescreening.get("key_findings", []),
        }

    # Normalize RAG data
    normalized_rag = {}
    if fields := rag_data.get("fields"):
        for key, value in fields.items():
            normalized_rag[key] = value

    # Normalize Web data
    normalized_web = {}
    if results := web_data.get("results"):
        normalized_web["search_results"] = [
            {"title": r.get("title"), "snippet": r.get("content", "")[:300]}
            for r in results[:5]
        ]
    if answer := web_data.get("answer"):
        normalized_web["ai_summary"] = answer

    return {
        "working_memory": {
            **state.get("working_memory", {}),
            "normalized_mcp": normalized_mcp,
            "normalized_rag": normalized_rag,
            "normalized_web": normalized_web,
        }
    }


async def generate_insights(state: MultiAgentState) -> dict:
    """
    Generate insights by synthesizing data from all sources.

    This node uses LLM to identify key insights, gaps, and contradictions.
    """
    logger.info("Generating insights")

    working_memory = state.get("working_memory") or {}
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}
    intent_analysis = state.get("intent_analysis") or {}

    # Get user question from messages
    messages = state.get("messages", [])
    user_question = ""
    from langchain_core.messages import HumanMessage
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_question = str(msg.content)
            break

    # Build synthesis prompt
    prompt = SYNTHESIS_PROMPT.format(
        mcp_data=json.dumps(mcp_data, indent=2, default=str)[:3000],
        rag_data=json.dumps(rag_data.get("fields", {}), indent=2, default=str)[:2000],
        web_data=json.dumps(web_data.get("results", [])[:3], indent=2, default=str)[:1000],
        user_question=user_question,
        document_type=intent_analysis.get("document_type", "document"),
    )

    # Call LLM for synthesis
    llm = get_llm(temperature=0.2)
    try:
        response = await llm.ainvoke(prompt)

        # Parse response
        response_text = response.content.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        synthesis_data = json.loads(response_text)

        insights: SynthesizedInsights = {
            "normalized_data": synthesis_data.get("normalized_data", {}),
            "insights": synthesis_data.get("insights", []),
            "data_gaps": synthesis_data.get("data_gaps", []),
            "contradictions": synthesis_data.get("contradictions", []),
            "confidence_scores": synthesis_data.get("confidence_scores", {}),
        }

        # Emit insight events
        if sse_callback := state.get("sse_callback"):
            for insight in insights.get("insights", [])[:3]:
                await sse_callback(
                    "insight_generated",
                    insight,
                    "synthesis",
                )

        logger.info(f"Generated {len(insights.get('insights', []))} insights")

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse synthesis: {e}, using defaults")
        insights: SynthesizedInsights = {
            "normalized_data": working_memory.get("normalized_mcp", {}),
            "insights": [],
            "data_gaps": [],
            "contradictions": [],
            "confidence_scores": {},
        }

    return {"synthesized_insights": insights}


async def score_confidence(state: MultiAgentState) -> dict:
    """
    Assign confidence scores to data points.

    This node evaluates the reliability of gathered data.
    """
    logger.info("Scoring data confidence")

    insights = state.get("synthesized_insights") or {}
    confidence_scores = dict(insights.get("confidence_scores", {}))

    # Add default scores based on source
    mcp_data = state.get("mcp_data") or {}
    rag_data = state.get("rag_data") or {}
    web_data = state.get("web_data") or {}

    # MCP data is most reliable (internal source)
    if mcp_data.get("opportunity"):
        confidence_scores["opportunity_data"] = 0.95

    # RAG data reliability depends on document quality
    if rag_data.get("fields"):
        confidence_scores["document_data"] = 0.85

    # Web data is least reliable
    if web_data.get("results"):
        confidence_scores["web_data"] = 0.70

    # Update insights with scores
    updated_insights = {
        **insights,
        "confidence_scores": confidence_scores,
    }

    # Emit phase completed
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "synthesis_completed",
            {
                "insights_count": len(insights.get("insights", [])),
                "data_gaps": len(insights.get("data_gaps", [])),
            },
            "synthesis",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "synthesis",
        "to_phase": "template",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Synthesis complete: {len(insights.get('insights', []))} insights",
    })

    return {
        "synthesized_insights": updated_insights,
        "phase_history": phase_history,
        "current_phase": "template",
        "updated_at": datetime.utcnow(),
    }
