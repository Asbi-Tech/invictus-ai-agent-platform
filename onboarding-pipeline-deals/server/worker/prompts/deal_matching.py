"""
Prompt for LLM-based deal name deduplication.

Used by worker.deal_resolver to cluster raw deal/company names extracted
from investment documents into canonical groups before persisting.
"""

DEAL_MATCHING_SYSTEM_PROMPT = (
    "You are a deal name deduplication assistant. "
    "You will receive a list of deal/company names extracted from investment documents. "
    "Your job is to identify which names refer to the same deal/company and "
    "return a canonical mapping. "
    "Respond with a single valid JSON object. No markdown, no prose — raw JSON only."
)

DEAL_MATCHING_USER_PROMPT = """\
Below are deal/company names extracted from investment documents, plus any
existing deal names already in the database.

## RULES
1. Group names that refer to the SAME company or deal.
2. For each group, pick the SHORTEST unambiguous canonical name (max 3 words).
   Strip legal suffixes (Inc, Ltd, LLC, Corp, Fund, Capital, Partners, Holdings, Group).
3. If a name clearly matches an existing DB deal, use the DB deal's name as canonical
   (preserve the exact spelling/casing from the DB).
4. Do NOT merge names that are clearly different companies.
5. Project codenames (e.g. "Project Venus") should map to the company name if known
   from context, otherwise keep the codename.
6. When in doubt and names share no obvious relationship, keep them separate.
   But DO merge when one name is clearly a longer form of another
   (e.g. "ICG" and "ICG Strategic Equity" are the same deal — use "ICG").

## INPUT

New names from current batch:
{new_names}

Existing deal names in database:
{existing_names}

## OUTPUT

Return JSON:
{{
  "groups": [
    {{
      "canonical": "<shortest unambiguous name>",
      "members": ["<name1>", "<name2>", ...]
    }}
  ]
}}

Every input name (both new and existing) must appear in exactly one group's members list.
"""
