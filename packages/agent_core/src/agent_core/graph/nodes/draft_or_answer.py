"""Draft or answer node - generates the response."""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import AzureChatOpenAI

from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


SYSTEM_PROMPT = """You are an AI assistant for Invictus AI, a wealth management platform.
You help users with:
- Answering questions about opportunities, clients, and investments
- Analyzing documents and data
- Generating reports and memos
- Summarizing information

Always be professional, accurate, and cite your sources when using document information.
If information was extracted from documents, reference it clearly.

{context}"""


def build_context(state: dict[str, Any]) -> str:
    """
    Build context string from working memory for the LLM.

    Args:
        state: The current agent state

    Returns:
        Formatted context string
    """
    working_memory = state.get("working_memory", {})
    context_parts = []

    # Add entity data if available
    for key, value in working_memory.items():
        if key.endswith("_data") and isinstance(value, dict):
            entity_type = key.replace("_data", "")
            context_parts.append(f"\n**{entity_type.title()} Information:**")
            for field, field_value in value.items():
                if field_value is not None:
                    context_parts.append(f"- {field}: {field_value}")

    # Add RAG extraction results if available
    rag_results = working_memory.get("rag_results", {})
    if rag_results:
        context_parts.append("\n**Information Extracted from Documents:**")
        for field_name, field_value in rag_results.items():
            if field_value is not None:
                context_parts.append(f"- {field_name}: {field_value}")

    if context_parts:
        return "\n".join(context_parts)
    return "No additional context available."


async def draft_or_answer(state: dict[str, Any]) -> dict[str, Any]:
    """
    Generate a response based on the user's intent and gathered context.

    Uses the LLM to generate a helpful response incorporating the gathered context.

    Args:
        state: The current agent state

    Returns:
        State updates with the AI response message
    """
    current_intent = state.get("current_intent", "qa")
    messages_list = state.get("messages", [])

    # Build context from gathered data
    context = build_context(state)
    system_prompt = SYSTEM_PROMPT.format(context=context)

    # Build messages for the LLM
    llm_messages = [{"role": "system", "content": system_prompt}]

    for msg in messages_list:
        if isinstance(msg, HumanMessage):
            llm_messages.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage):
            llm_messages.append({"role": "assistant", "content": str(msg.content)})

    # Adjust temperature based on intent
    temperature = 0.7
    if current_intent in ("summarize", "qa"):
        temperature = 0.3  # More factual
    elif current_intent == "generate":
        temperature = 0.7  # More creative

    # Create the LLM instance
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=temperature,
    )

    try:
        response = await llm.ainvoke(llm_messages)

        logger.info(
            "Generated response",
            intent=current_intent,
            response_length=len(response.content),
        )

        # Return the response as a new message
        return {
            "messages": [AIMessage(content=response.content)],
        }

    except Exception as e:
        logger.error("LLM generation failed", error=str(e))

        error_message = (
            "I apologize, but I encountered an error while processing your request. "
            "Please try again or rephrase your question."
        )

        return {
            "messages": [AIMessage(content=error_message)],
            "error_count": state.get("error_count", 0) + 1,
        }
