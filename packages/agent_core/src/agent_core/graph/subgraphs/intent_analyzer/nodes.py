"""Intent Analyzer nodes for request classification and entity detection."""

import json
from datetime import datetime

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI

from common.callback_registry import get_callback_for_state
from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState, IntentAnalysis

logger = get_logger(__name__)

# Intent classification prompt
INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for an AI copilot system.

Analyze the user's request and classify it into one of these categories:
- "ask": The user is asking a question or seeking information
- "create": The user wants to generate a new document/artifact
- "edit": The user wants to modify an existing document/artifact
- "extend": The user wants to add content to an existing document

Also identify:
1. Document type (if applicable): "prescreening", "investment_memo", "custom_report", or null
2. Entities mentioned: opportunity, client, fund, deal, document, etc.
3. Missing information needed to complete the request
4. Confidence level (0-1)

User Message: {message}

Page Context: {page_context}

Additional Context: {additional_prompt}

Respond in JSON format:
{{
    "request_type": "ask|create|edit|extend",
    "document_type": "prescreening|investment_memo|custom_report|null",
    "entities_detected": ["list of entity types found"],
    "missing_inputs": ["list of missing required information"],
    "clarification_needed": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}"""


def get_llm(temperature: float = 0.0) -> AzureChatOpenAI:
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


async def analyze_request(state: MultiAgentState) -> dict:
    """
    Analyze the user's request to classify intent and detect document type.

    This node:
    1. Checks if agent_case is explicitly set (from API request)
    2. If not, uses LLM to classify the request type
    3. Identifies the target document type if applicable
    4. Returns intent analysis results

    Note: When agent_case is explicitly provided in the request (edit, create, fill),
    it takes precedence over LLM classification to ensure user intent is respected.
    """
    logger.info("Analyzing request intent")

    # Extract context
    user_message = get_last_human_message(state)
    page_context = state.get("page_context") or {}
    additional_prompt = state.get("additional_prompt") or ""

    # Check if agent_case is explicitly set from the API request
    # This takes precedence over LLM classification
    explicit_agent_case = state.get("agent_case")

    # Emit thinking event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_started",
            {"phase": "intent", "message": "Analyzing your request..."},
            "intent_analyzer",
        )

    # Build classification prompt
    prompt = INTENT_CLASSIFICATION_PROMPT.format(
        message=user_message,
        page_context=json.dumps(page_context, indent=2) if page_context else "None",
        additional_prompt=additional_prompt or "None",
    )

    # Call LLM for classification
    llm = get_llm(temperature=0.0)
    try:
        response = await llm.ainvoke(prompt)

        # Parse JSON response
        response_text = response.content.strip()
        # Handle markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        intent_data = json.loads(response_text)

        # Use explicit agent_case if provided, otherwise use LLM classification
        if explicit_agent_case in ["create", "edit", "fill"]:
            request_type = explicit_agent_case
            logger.info(f"Using explicit agent_case: {explicit_agent_case}")
            # When agent_case is explicit, don't use LLM's missing_inputs/clarification_needed
            # These will be determined by check_completeness() based on actual state
            llm_missing_inputs = []
            llm_clarification_needed = False
        else:
            request_type = intent_data.get("request_type", "ask")
            llm_missing_inputs = intent_data.get("missing_inputs", [])
            llm_clarification_needed = intent_data.get("clarification_needed", False)

        intent_analysis: IntentAnalysis = {
            "request_type": request_type,
            "document_type": intent_data.get("document_type"),
            "entities_detected": intent_data.get("entities_detected", []),
            "missing_inputs": llm_missing_inputs,
            "clarification_needed": llm_clarification_needed,
            "confidence": intent_data.get("confidence", 0.8),
        }

        logger.info(
            f"Intent analysis complete: type={intent_analysis['request_type']}, "
            f"doc_type={intent_analysis['document_type']}, "
            f"clarification_needed={intent_analysis['clarification_needed']}"
        )

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse intent response: {e}, defaulting to 'ask'")
        # Still respect explicit agent_case even on parse failure
        if explicit_agent_case in ["create", "edit", "fill"]:
            request_type = explicit_agent_case
        else:
            request_type = "ask"

        intent_analysis: IntentAnalysis = {
            "request_type": request_type,
            "document_type": None,
            "entities_detected": [],
            "missing_inputs": [],
            "clarification_needed": False,
            "confidence": 0.5,
        }

    # Emit intent detected event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "intent_detected",
            {
                "request_type": intent_analysis["request_type"],
                "document_type": intent_analysis["document_type"],
                "confidence": intent_analysis["confidence"],
            },
            "intent_analyzer",
        )

    return {
        "intent_analysis": intent_analysis,
        "document_type": intent_analysis["document_type"],
        "current_phase": "intent",
    }


async def detect_entities(state: MultiAgentState) -> dict:
    """
    Detect and validate entities from the request and page context.

    This node:
    1. Extracts entity references from page_context
    2. Validates that referenced entities are available
    3. Updates the entities_detected list
    """
    logger.info("Detecting entities from context")

    intent_analysis = state.get("intent_analysis") or {}
    page_context = state.get("page_context") or {}
    entities_detected = list(intent_analysis.get("entities_detected", []))

    # Extract entities from page context
    entity_mappings = {
        "opportunity_id": "opportunity",
        "opportunity_name": "opportunity",
        "client_id": "client",
        "fund_id": "fund",
        "deal_id": "deal",
    }

    for field, entity_type in entity_mappings.items():
        if page_context.get(field) and entity_type not in entities_detected:
            entities_detected.append(entity_type)

    # Check for documents
    document_ids = state.get("document_ids", [])
    selected_docs = state.get("selected_docs") or {}
    if document_ids or selected_docs.get("doc_ids"):
        if "document" not in entities_detected:
            entities_detected.append("document")

    # Update intent analysis with detected entities
    updated_intent = {
        **intent_analysis,
        "entities_detected": entities_detected,
    }

    # Emit entities detected event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "entities_detected",
            {"entities": entities_detected},
            "intent_analyzer",
        )

    logger.info(f"Entities detected: {entities_detected}")

    return {
        "intent_analysis": updated_intent,
    }


async def check_completeness(state: MultiAgentState) -> dict:
    """
    Check if the request has all required information.

    This node:
    1. Validates required fields based on request type
    2. Identifies missing inputs
    3. Determines if clarification is needed
    """
    logger.info("Checking request completeness")

    intent_analysis = state.get("intent_analysis") or {}
    request_type = intent_analysis.get("request_type", "ask")
    document_type = intent_analysis.get("document_type")
    entities_detected = intent_analysis.get("entities_detected", [])
    page_context = state.get("page_context") or {}
    current_artifact = state.get("current_artifact")

    missing_inputs = list(intent_analysis.get("missing_inputs", []))
    clarification_needed = intent_analysis.get("clarification_needed", False)

    # Check requirements based on request type
    if request_type == "create":
        # Create mode requires knowing what to create
        if not document_type:
            if "document type" not in missing_inputs:
                missing_inputs.append("document type")
            clarification_needed = True

        # Usually needs opportunity context for investment documents
        if document_type in ["investment_memo", "prescreening"]:
            if "opportunity" not in entities_detected and not page_context.get("opportunity_id"):
                if "opportunity context" not in missing_inputs:
                    missing_inputs.append("opportunity context")
                clarification_needed = True

    elif request_type in ["edit", "extend"]:
        # Edit and extend modes require an existing artifact with content
        # Check if artifact exists AND has actual content (not just the object)
        has_artifact_content = (
            current_artifact
            and isinstance(current_artifact, dict)
            and current_artifact.get("content")
        )
        if not has_artifact_content:
            if "current artifact" not in missing_inputs:
                missing_inputs.append("current artifact")
            clarification_needed = True
            logger.info(
                f"Edit/extend mode missing artifact content. "
                f"Has artifact: {current_artifact is not None}, "
                f"Has content: {bool(current_artifact.get('content') if current_artifact else False)}"
            )

    # Update intent analysis
    updated_intent: IntentAnalysis = {
        **intent_analysis,
        "missing_inputs": missing_inputs,
        "clarification_needed": clarification_needed,
    }

    # Determine if we need to enter clarification phase
    # "Ask" requests should never trigger clarification - always attempt to answer
    if request_type == "ask":
        clarification_pending = False
    else:
        clarification_pending = clarification_needed and len(missing_inputs) > 0

    # Emit phase completed event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_completed",
            {
                "phase": "intent",
                "clarification_needed": clarification_pending,
                "missing_inputs": missing_inputs,
            },
            "intent_analyzer",
        )

    logger.info(
        f"Completeness check: clarification_needed={clarification_pending}, "
        f"missing={missing_inputs}"
    )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "intent",
        "to_phase": "clarification" if clarification_pending else "planning",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Missing: {missing_inputs}" if clarification_pending else "Complete",
    })

    return {
        "intent_analysis": updated_intent,
        "clarification_pending": clarification_pending,
        "phase_history": phase_history,
        "updated_at": datetime.utcnow(),
    }
