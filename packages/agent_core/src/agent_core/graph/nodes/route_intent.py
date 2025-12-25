"""Route intent node - classifies user intent."""

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


INTENT_CLASSIFICATION_PROMPT = """Classify the user's intent into one of these categories:

- qa: Asking a question or seeking information
- generate: Requesting to create new content (report, memo, summary document)
- edit: Requesting to modify existing content
- summarize: Requesting a summary of documents or data
- compare: Requesting comparison between items

User message: {message}

Respond with just the category name (qa, generate, edit, summarize, or compare).
Do not include any other text or explanation."""


async def route_intent(state: dict[str, Any]) -> dict[str, Any]:
    """
    Classify the user's intent based on their message.

    Uses the LLM to determine what the user is trying to accomplish.

    Args:
        state: The current agent state

    Returns:
        State updates with the classified intent
    """
    messages = state.get("messages", [])

    # Get the last human message
    last_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break

    if not last_message:
        logger.warning("No human message found, defaulting to QA intent")
        return {"current_intent": "qa"}

    # Use LLM to classify intent
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=0,
        max_tokens=20,
    )

    try:
        response = await llm.ainvoke(
            INTENT_CLASSIFICATION_PROMPT.format(message=last_message)
        )
        intent_str = response.content.strip().lower()

        # Validate the intent
        valid_intents = {"qa", "generate", "edit", "summarize", "compare"}
        if intent_str not in valid_intents:
            logger.warning(
                "Invalid intent classification, defaulting to qa",
                classified_intent=intent_str,
            )
            intent_str = "qa"

        logger.info(
            "Classified intent",
            intent=intent_str,
            message_preview=last_message[:50],
        )

        return {"current_intent": intent_str}

    except Exception as e:
        logger.error("Intent classification failed", error=str(e))
        return {"current_intent": "qa"}
