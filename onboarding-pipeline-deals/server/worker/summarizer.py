"""
Document summarization module.

Generates a two-sentence description of an investment document using an LLM.
Falls back to extracting the first two sentences from the raw text when
the LLM is unavailable (no API key or network error).
"""

import logging
import os
import time
from typing import Optional

from worker.prompts.summarization import (
    SUMMARIZATION_SYSTEM_PROMPT,
    SUMMARIZATION_USER_PROMPT,
)

logger = logging.getLogger(__name__)


def _cfg():
    """Lazy-import settings so the module can be imported without .env present."""
    from app.config import settings
    return settings


_MAX_LLM_RETRIES = 3
_LLM_RETRY_BACKOFF = (5.0, 15.0, 30.0)   # wait (seconds) before attempt n+1


def _get_llm_client():
    """Return the appropriate OpenAI-compatible client (Azure or direct)."""
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
    """Return the model/deployment name to use in completions."""
    cfg = _cfg()
    if cfg.use_azure_openai:
        return cfg.AZURE_OPENAI_DEPLOYMENT
    return cfg.OPENAI_MODEL


def generate_description(text: str) -> Optional[str]:
    """
    Generate a short two-sentence description of the document.

    Args:
        text: Full extracted document text (truncated internally to 3 000 chars).

    Returns:
        A two-sentence summary string, or a plain-text fallback, or None.
    """
    cfg = _cfg()
    if not (cfg.use_azure_openai or os.getenv("OPENAI_API_KEY")):
        logger.warning("No OpenAI credentials set – using fallback summarization")
        return _fallback_summary(text)

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_LLM_RETRIES + 1):
        try:
            client = _get_llm_client()
            truncated = text[:3000]
            response = client.chat.completions.create(
                model=_get_model_name(),
                messages=[
                    {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
                    {"role": "user", "content": SUMMARIZATION_USER_PROMPT.format(text=truncated)},
                ],
                max_tokens=120,
                temperature=0.3,
            )
            summary = response.choices[0].message.content.strip()
            logger.info("Document summary generated via LLM")
            return summary
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_LLM_RETRIES:
                wait = _LLM_RETRY_BACKOFF[min(attempt - 1, len(_LLM_RETRY_BACKOFF) - 1)]
                logger.warning(
                    f"LLM summarization attempt {attempt}/{_MAX_LLM_RETRIES} failed: {exc} "
                    f"\u2014 retrying in {wait:.0f}s"
                )
                time.sleep(wait)
    logger.error(f"LLM summarization failed after {_MAX_LLM_RETRIES} attempts: {last_exc}")
    return _fallback_summary(text)


# ── Fallback ──────────────────────────────────────────────────────────────────

def text_summary(text: str) -> Optional[str]:
    """Extract a two-sentence summary from raw text without any LLM call."""
    return _fallback_summary(text)


def _fallback_summary(text: str) -> Optional[str]:
    """
    Return the first two meaningful sentences from the document.
    Used when the LLM is unavailable.
    """
    if not text:
        return None
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]
    if sentences:
        return ". ".join(sentences[:2]) + "."
    return text[:200] if text else None
