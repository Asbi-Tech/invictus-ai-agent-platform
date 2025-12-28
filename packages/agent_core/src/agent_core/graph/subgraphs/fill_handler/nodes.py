"""Fill handler nodes for form filling mode."""

import json
from datetime import datetime
from typing import Any

from langchain_openai import AzureChatOpenAI

from common.callback_registry import get_callback_for_state
from common.config import get_settings
from common.logging import get_logger
from agent_core.graph.state import MultiAgentState

logger = get_logger(__name__)


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


FILL_PROMPT = """You are a form-filling assistant. Your task is to fill in a structured field based on the available data.

Field to fill:
- Name: {field_name}
- Description: {field_description}
- Type: {field_type}
- Instruction: {field_instruction}
{options_text}

Available Data:
{available_data}

Based on the available data and the field's instruction, determine the appropriate value for this field.

IMPORTANT:
- If the data contains clear information for this field, extract and return it.
- If the information is not found or unclear, return null.
- For numeric fields, return a number (no quotes, no units).
- For string fields, return a clean string value.
- For array fields, return a JSON array.
- For object fields, return a JSON object.
- If options are specified, the value MUST be one of the provided options.

Respond in JSON format:
{{
    "value": <the extracted/determined value or null>,
    "confidence": <0.0 to 1.0 confidence score>,
    "reasoning": "<brief explanation of how you determined the value>"
}}"""


async def prepare_fields(state: MultiAgentState) -> dict:
    """
    Prepare fields for filling from the template definition.

    This node:
    1. Extracts field definitions from template
    2. Identifies which fields need to be filled
    3. Prepares the data context for filling
    """
    logger.info("Preparing fields for filling")

    # Emit phase started event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_started",
            {"phase": "fill", "message": "Preparing to fill template fields..."},
            "fill_handler",
        )

    template_def = state.get("template_definition") or {}
    fields = template_def.get("fields", {})

    # Flatten fields list (handle both flat and nested structures)
    fields_to_fill = []
    for field_key, field_def in fields.items():
        if isinstance(field_def, dict):
            if "description" in field_def:
                # This is a leaf field
                fields_to_fill.append(field_key)
            else:
                # This is a nested structure
                for subfield_key in field_def.keys():
                    fields_to_fill.append(f"{field_key}.{subfield_key}")
        else:
            fields_to_fill.append(field_key)

    logger.info(f"Prepared {len(fields_to_fill)} fields to fill")

    return {
        "fields_to_fill": fields_to_fill,
        "fill_mode_active": True,
        "filled_fields": {},
        "current_phase": "fill",
    }


def get_field_definition(template_def: dict, field_key: str) -> dict:
    """Get field definition from template, handling nested keys."""
    fields = template_def.get("fields", {})

    if "." in field_key:
        parts = field_key.split(".", 1)
        parent = fields.get(parts[0], {})
        if isinstance(parent, dict):
            return parent.get(parts[1], {})
        return {}
    else:
        return fields.get(field_key, {})


def set_nested_value(obj: dict, key: str, value: Any) -> None:
    """Set a value in a nested dict using dot notation."""
    if "." in key:
        parts = key.split(".", 1)
        if parts[0] not in obj:
            obj[parts[0]] = {}
        set_nested_value(obj[parts[0]], parts[1], value)
    else:
        obj[key] = value


async def fill_fields(state: MultiAgentState) -> dict:
    """
    Fill template fields using LLM and available data.

    This node:
    1. Iterates through fields to fill
    2. Uses LLM to determine values based on context
    3. Accumulates filled values
    """
    logger.info("Filling template fields")

    template_def = state.get("template_definition") or {}
    fields_to_fill = state.get("fields_to_fill", [])
    filled_fields = dict(state.get("filled_fields", {}))

    # Gather available data context
    mcp_data = state.get("mcp_data", {})
    rag_data = state.get("rag_data", {})
    page_context = state.get("page_context", {})
    working_memory = state.get("working_memory", {})

    # Build data context string
    data_context = {
        "page_context": page_context,
        "mcp_data": mcp_data,
        "rag_data": {k: v for k, v in rag_data.items() if k != "sources"},  # Exclude raw sources
        "working_memory": {k: v for k, v in working_memory.items() if not k.startswith("_")},
    }
    data_context_str = json.dumps(data_context, indent=2, default=str)[:8000]  # Limit size

    llm = get_llm(temperature=0.2)

    for field_key in fields_to_fill:
        field_def = get_field_definition(template_def, field_key)
        if not field_def:
            logger.warning(f"No definition found for field: {field_key}")
            continue

        # Emit field started event
        if sse_callback := get_callback_for_state(state):
            await sse_callback(
                "section_started",
                {"section_id": field_key, "section_name": field_key.replace("_", " ").title()},
                "fill_handler",
            )

        # Build options text if applicable
        options = field_def.get("options", [])
        options_text = f"- Allowed values: {', '.join(options)}" if options else ""

        # Build prompt
        prompt = FILL_PROMPT.format(
            field_name=field_key.replace("_", " ").title(),
            field_description=field_def.get("description", ""),
            field_type=field_def.get("type", "string"),
            field_instruction=field_def.get("instruction", ""),
            options_text=options_text,
            available_data=data_context_str,
        )

        try:
            response = await llm.ainvoke(prompt)
            response_text = response.content.strip()

            # Parse JSON response
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            result = json.loads(response_text)
            value = result.get("value")

            # Validate against options if specified
            if options and value is not None and value not in options:
                logger.warning(f"Field {field_key}: value '{value}' not in allowed options")
                # Find closest match or set to None
                value = None

            # Set the value
            set_nested_value(filled_fields, field_key, value)

            logger.info(f"Filled field {field_key}: {value} (confidence: {result.get('confidence', 'N/A')})")

            # Emit field completed event
            if sse_callback := get_callback_for_state(state):
                await sse_callback(
                    "section_completed",
                    {
                        "section_id": field_key,
                        "status": "completed" if value is not None else "skipped",
                        "has_value": value is not None,
                    },
                    "fill_handler",
                )

        except Exception as e:
            logger.error(f"Failed to fill field {field_key}: {e}")
            set_nested_value(filled_fields, field_key, None)

    return {
        "filled_fields": filled_fields,
        "fields_to_fill": [],  # Clear the list
    }


async def validate_fill(state: MultiAgentState) -> dict:
    """
    Validate the filled template.

    This node:
    1. Checks that required fields are filled
    2. Validates field types
    3. Reports completion status
    """
    logger.info("Validating filled template")

    template_def = state.get("template_definition") or {}
    fields = template_def.get("fields", {})
    filled_fields = state.get("filled_fields", {})

    # Check required fields
    missing_required = []
    for field_key, field_def in fields.items():
        if isinstance(field_def, dict) and "description" in field_def:
            # Leaf field
            if field_def.get("required", True):
                value = filled_fields.get(field_key)
                if value is None:
                    missing_required.append(field_key)
        elif isinstance(field_def, dict):
            # Nested structure
            for subfield_key, subfield_def in field_def.items():
                if isinstance(subfield_def, dict) and subfield_def.get("required", True):
                    parent = filled_fields.get(field_key, {})
                    if isinstance(parent, dict) and parent.get(subfield_key) is None:
                        missing_required.append(f"{field_key}.{subfield_key}")

    # Calculate fill rate
    total_fields = len([k for k, v in fields.items() if isinstance(v, dict)])
    filled_count = sum(1 for v in filled_fields.values() if v is not None)
    fill_rate = filled_count / total_fields if total_fields > 0 else 1.0

    # Emit phase completed event
    if sse_callback := get_callback_for_state(state):
        await sse_callback(
            "phase_completed",
            {
                "phase": "fill",
                "fields_filled": filled_count,
                "total_fields": total_fields,
                "fill_rate": fill_rate,
                "missing_required": missing_required,
            },
            "fill_handler",
        )

    # Update phase history
    phase_history = list(state.get("phase_history", []))
    phase_history.append({
        "from_phase": "fill",
        "to_phase": "complete",
        "timestamp": datetime.utcnow().isoformat(),
        "reason": f"Fill completed: {filled_count}/{total_fields} fields",
    })

    return {
        "fill_mode_active": False,
        "phase_history": phase_history,
        "current_phase": "complete",
        "updated_at": datetime.utcnow(),
    }
