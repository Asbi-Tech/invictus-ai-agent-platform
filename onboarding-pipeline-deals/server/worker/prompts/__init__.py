"""
Centralised prompt registry for the worker pipeline.

All LLM prompts live here so they can be versioned, reviewed, and
swapped independently of the business logic that calls them.
"""

from worker.prompts.batch_analysis import (
    BATCH_ANALYSIS_SYSTEM_PROMPT,
    DEFAULT_FIRM_CONTEXT,
    OUTPUT_SCHEMA,
)
from worker.prompts.summarization import (
    SUMMARIZATION_SYSTEM_PROMPT,
    SUMMARIZATION_USER_PROMPT,
)
from worker.prompts.field_extraction import (
    FieldDef,
    FUND_FIELDS,
    DIRECT_FIELDS,
    CO_INVESTMENT_FIELDS,
    FIELDS_BY_INVESTMENT_TYPE,
)

__all__ = [
    # batch analysis
    "BATCH_ANALYSIS_SYSTEM_PROMPT",
    "DEFAULT_FIRM_CONTEXT",
    "OUTPUT_SCHEMA",
    # summarization
    "SUMMARIZATION_SYSTEM_PROMPT",
    "SUMMARIZATION_USER_PROMPT",
    # field extraction
    "FieldDef",
    "FUND_FIELDS",
    "DIRECT_FIELDS",
    "CO_INVESTMENT_FIELDS",
    "FIELDS_BY_INVESTMENT_TYPE",
]
