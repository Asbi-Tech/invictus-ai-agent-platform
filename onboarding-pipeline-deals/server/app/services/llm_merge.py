"""LLM-based merge conflict resolution.

When two deals have the same document type, this module asks the LLM to
recommend which document to keep vs. archive, based on file name, date,
description, and deal context.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prompt ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a financial analyst assistant helping merge two investment deals. "
    "You will be given information about two documents of the same type that "
    "belong to two deals being merged. "
    "Decide which document should be kept as the current version and which "
    "should be archived. "
    "You MUST respond with a single valid JSON object — no markdown, no code "
    "fences, no prose — raw JSON only."
)

_USER_TEMPLATE = """\
We are merging two deals into one. Both deals have a document of type "{doc_type_label}".
Decide which document should be kept as the CURRENT version (the most relevant, \
up-to-date, and comprehensive one) and which should be ARCHIVED.

Consider:
- The merged deal name: "{deal_name}"
- Document recency (newer is usually better)
- File name relevance to the deal
- Description quality and completeness

## Source deal: "{source_deal_name}"
Document:
- File name: {source_file_name}
- Date: {source_date}
- Description: {source_description}

## Target deal: "{target_deal_name}"
Document:
- File name: {target_file_name}
- Date: {target_date}
- Description: {target_description}

Respond with this exact JSON schema:
{{
  "recommendation": "<keep_source or keep_target>",
  "reason": "<1-2 sentence explanation of why this document is the better choice>"
}}
"""


# ── LLM client (reuses batch_analyzer pattern) ──────────────────────────────

def _cfg():
    from app.config import settings
    return settings


def _get_llm_client():
    cfg = _cfg()
    if cfg.use_azure_openai:
        from openai import AzureOpenAI
        return AzureOpenAI(
            api_key=cfg.AZURE_OPENAI_API_KEY,
            azure_endpoint=cfg.AZURE_OPENAI_ENDPOINT,
            api_version=cfg.AZURE_OPENAI_API_VERSION,
        )
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _get_model_name() -> str:
    cfg = _cfg()
    if cfg.use_azure_openai:
        return cfg.AZURE_OPENAI_DEPLOYMENT
    return cfg.OPENAI_MODEL


# ── Public API ───────────────────────────────────────────────────────────────

def resolve_merge_conflict(
    doc_type_label: str,
    deal_name: str,
    source_deal_name: str,
    target_deal_name: str,
    source_file_name: str,
    source_date: Optional[str],
    source_description: Optional[str],
    target_file_name: str,
    target_date: Optional[str],
    target_description: Optional[str],
) -> dict:
    """
    Ask the LLM which document to keep when both deals have the same type.

    Returns {"recommendation": "keep_source"|"keep_target", "reason": "..."}.
    Falls back to "keep_target" if the LLM call fails.
    """
    cfg = _cfg()
    if not (cfg.use_azure_openai or os.getenv("OPENAI_API_KEY")):
        logger.warning("No OpenAI credentials — defaulting to keep_target")
        return {
            "recommendation": "keep_target",
            "reason": "No LLM available; defaulting to target deal's document.",
        }

    user_msg = _USER_TEMPLATE.format(
        doc_type_label=doc_type_label,
        deal_name=deal_name,
        source_deal_name=source_deal_name,
        target_deal_name=target_deal_name,
        source_file_name=source_file_name,
        source_date=source_date or "Unknown",
        source_description=source_description or "No description available",
        target_file_name=target_file_name,
        target_date=target_date or "Unknown",
        target_description=target_description or "No description available",
    )

    try:
        client = _get_llm_client()
        response = client.chat.completions.create(
            model=_get_model_name(),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=300,
        )
        raw = response.choices[0].message.content or ""
        data = json.loads(raw)
        recommendation = data.get("recommendation", "keep_target")
        if recommendation not in ("keep_source", "keep_target"):
            recommendation = "keep_target"
        return {
            "recommendation": recommendation,
            "reason": data.get("reason", "LLM did not provide a reason."),
        }
    except Exception as exc:
        logger.error(f"LLM merge resolution failed: {exc}")
        return {
            "recommendation": "keep_target",
            "reason": "LLM unavailable; defaulting to target deal's document.",
        }
