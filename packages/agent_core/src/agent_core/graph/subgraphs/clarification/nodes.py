"""Clarification nodes for HITL interactions."""

import json
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState, ClarificationQuestion

logger = get_logger(__name__)

# Question generation prompt
QUESTION_GENERATION_PROMPT = """You are a helpful assistant that generates clarification questions.

The user made a request but some information is missing or unclear.

User Request: {message}
Request Type: {request_type}
Document Type: {document_type}
Missing Information: {missing_inputs}
Current Context: {context}

Generate 1-3 targeted clarification questions to gather the missing information.
For each question, provide options if there are clear choices.

Respond in JSON format:
{{
    "questions": [
        {{
            "question_id": "unique_id",
            "question": "The clarification question",
            "options": ["Option 1", "Option 2"] or null,
            "required": true/false
        }}
    ]
}}"""


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


async def generate_questions(state: MultiAgentState) -> dict:
    """
    Generate clarification questions based on missing inputs.

    This node:
    1. Analyzes what information is missing
    2. Generates targeted questions to gather that info
    3. Prepares the questions for user presentation
    """
    logger.info("Generating clarification questions")

    intent_analysis = state.get("intent_analysis") or {}
    missing_inputs = intent_analysis.get("missing_inputs", [])

    # If no missing inputs, skip question generation
    if not missing_inputs:
        logger.info("No missing inputs, skipping clarification")
        return {
            "clarification_questions": [],
            "clarification_pending": False,
        }

    # Extract context for question generation
    user_message = get_last_human_message(state)
    request_type = intent_analysis.get("request_type", "ask")
    document_type = intent_analysis.get("document_type")
    page_context = state.get("page_context") or {}

    # Build prompt
    prompt = QUESTION_GENERATION_PROMPT.format(
        message=user_message,
        request_type=request_type,
        document_type=document_type or "unknown",
        missing_inputs=", ".join(missing_inputs),
        context=json.dumps(page_context, indent=2) if page_context else "None",
    )

    # Call LLM for question generation
    llm = get_llm(temperature=0.3)
    try:
        response = await llm.ainvoke(prompt)

        # Parse JSON response
        response_text = response.content.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        data = json.loads(response_text)
        raw_questions = data.get("questions", [])

        # Convert to typed questions
        questions: list[ClarificationQuestion] = []
        for q in raw_questions:
            questions.append({
                "question_id": q.get("question_id", str(uuid.uuid4())[:8]),
                "question": q["question"],
                "options": q.get("options"),
                "required": q.get("required", True),
            })

        logger.info(f"Generated {len(questions)} clarification questions")

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse questions: {e}, generating default questions")

        # Generate default questions based on missing inputs
        questions = []
        for i, missing in enumerate(missing_inputs[:3]):  # Max 3 questions
            questions.append({
                "question_id": f"q_{i}",
                "question": f"Could you please specify the {missing}?",
                "options": None,
                "required": True,
            })

    # Emit clarification required event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "clarification_required",
            {
                "questions": questions,
                "missing_inputs": missing_inputs,
            },
            "clarification",
        )

    return {
        "clarification_questions": questions,
        "clarification_pending": True,
        "hitl_wait_reason": "clarification",
        "current_phase": "clarification",
    }


async def wait_for_response(state: MultiAgentState) -> dict:
    """
    Wait point for user clarification response.

    This node serves as an INTERRUPT POINT in the graph.
    The graph will pause here until the user provides responses
    via the /resume endpoint.

    The actual waiting is handled by LangGraph's interrupt mechanism.
    This node just prepares the state for resumption.
    """
    logger.info("Waiting for user clarification response")

    # Emit waiting event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "thinking",
            {"message": "Waiting for your response..."},
            "clarification",
        )

    # This node returns minimal changes - the graph will be interrupted
    # before this node, and when resumed, the state will contain
    # clarification_responses from the user
    return {
        "hitl_wait_reason": "clarification",
        "updated_at": datetime.utcnow(),
    }


async def process_response(state: MultiAgentState) -> dict:
    """
    Process the user's clarification responses.

    This node:
    1. Extracts user responses from state
    2. Updates the intent analysis with new information
    3. Clears the clarification pending state
    4. Prepares for planning phase
    """
    logger.info("Processing clarification responses")

    responses = state.get("clarification_responses", {})
    questions = state.get("clarification_questions", [])
    intent_analysis = state.get("intent_analysis") or {}

    # Log received responses
    for question in questions:
        qid = question["question_id"]
        if qid in responses:
            logger.info(f"Question {qid}: {question['question']} -> {responses[qid]}")

    # Update intent analysis based on responses
    updated_intent = dict(intent_analysis)

    # Check for document type in responses
    for qid, response in responses.items():
        response_lower = str(response).lower()

        # Try to detect document type from response
        if "memo" in response_lower or "investment" in response_lower:
            updated_intent["document_type"] = "investment_memo"
        elif "prescreening" in response_lower or "pre-screening" in response_lower:
            updated_intent["document_type"] = "prescreening"
        elif "report" in response_lower:
            updated_intent["document_type"] = "custom_report"

    # Clear missing inputs that were addressed
    remaining_missing = []
    addressed_missing = set()

    for missing in intent_analysis.get("missing_inputs", []):
        # Check if any response addresses this missing input
        addressed = False
        for qid, response in responses.items():
            # Find the question for this response
            for q in questions:
                if q["question_id"] == qid and missing.lower() in q["question"].lower():
                    addressed = True
                    addressed_missing.add(missing)
                    break
            if addressed:
                break

        if not addressed:
            remaining_missing.append(missing)

    updated_intent["missing_inputs"] = remaining_missing
    updated_intent["clarification_needed"] = len(remaining_missing) > 0

    # Emit clarification resolved event
    if sse_callback := state.get("sse_callback"):
        await sse_callback(
            "clarification_resolved",
            {
                "responses_count": len(responses),
                "remaining_missing": remaining_missing,
            },
            "clarification",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "clarification",
        "to_phase": "planning",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"User provided {len(responses)} clarification(s)",
    })

    logger.info(
        f"Clarification processed: {len(responses)} responses, "
        f"{len(remaining_missing)} still missing"
    )

    return {
        "intent_analysis": updated_intent,
        "clarification_pending": False,
        "hitl_wait_reason": None,
        "phase_history": phase_history,
        "current_phase": "planning",
        "updated_at": datetime.utcnow(),
    }
