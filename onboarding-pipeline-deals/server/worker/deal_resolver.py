"""
Deal attribution and resolution module.

Responsible for:
  - Extracting a deal name candidate from a file's Drive folder path (Signal A)
  - Normalizing deal names for deduplication
  - Looking up or creating Deal records in the database
  - LLM-based deal name clustering (replaces fuzzy string matching)

Signal priority (highest → lowest):
  1. Folder path signal — most reliable; directly reflects how the user organised their Drive
  2. LLM signal        — extracted from document content by batch_analyzer
  3. None              — document stored ungrouped ("Uncategorized" in UI)
"""

import json
import re
import logging
import sys
import os
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Generic folder names to ignore ───────────────────────────────────────────

_GENERIC: set[str] = {
    "docs", "documents", "files", "file", "archive", "archives", "archived",
    "misc", "miscellaneous", "other", "others", "temp", "tmp", "new", "old",
    "uploads", "upload", "download", "downloads", "shared", "share",
    "q1", "q2", "q3", "q4", "h1", "h2",
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    # common VC-firm internal folder names
    "portfolio", "pipeline", "deals", "deal", "investments", "investment",
    "prospects", "prospect", "active", "closed", "leads",
    "inbox", "review", "reviewed", "pending",
    # version/date tokens
    "v1", "v2", "v3", "v4", "v5",
    "2020", "2021", "2022", "2023", "2024", "2025", "2026",
}

# Company suffix patterns to strip before normalizing
_SUFFIX_RE = re.compile(
    r"\s*(,\s*)?(inc\.?|incorporated|ltd\.?|limited|llc\.?|llp\.?|corp\.?|"
    r"corporation|co\.?|group|holdings|ventures|capital|partners|fund)\s*$",
    re.IGNORECASE,
)

# Characters to strip when building the lookup key
_NON_ALNUM = re.compile(r"[^a-z0-9]")

# Common folder suffixes to strip before treating segment as a deal name
_FOLDER_SUFFIX_RE = re.compile(
    r"[_\s-]*(TEST|VALIDATION|DOCS|FILES|DATA|DOCUMENTS|FOLDER)\s*$",
    re.IGNORECASE,
)


# ── Public interface ──────────────────────────────────────────────────────────

def extract_deal_from_folder_path(folder_path: Optional[str]) -> Optional[str]:
    """
    Given a slash-separated folder path string (e.g. "Portfolio/Acme Corp/Q1 2025"),
    return the most likely deal name, or None if only generic segments are found.

    Strategy: walk segments from left to right; return the first non-generic one.
    This means "Portfolio/Acme Corp/Q1 2025" → "Acme Corp" (Portfolio is generic,
    Q1 2025 is generic, Acme Corp is the meaningful middle segment).

    Common folder suffixes like _TEST, _VALIDATION, _DOCS are stripped so that
    "ICG_TEST" → "ICG" and "QUALIA_VALIDATION" → "Qualia".
    """
    if not folder_path:
        return None

    segments = [s.strip() for s in folder_path.split("/") if s.strip()]
    for segment in segments:
        # Strip common folder suffixes before checking
        cleaned = _FOLDER_SUFFIX_RE.sub("", segment).strip()
        cleaned = cleaned.replace("_", " ").strip()
        if not cleaned:
            continue
        key = _normalize_key(cleaned)
        if key and key not in _GENERIC and not key.isdigit() and len(key) >= 2:
            return normalize_deal_name(cleaned)
    return None


def normalize_deal_name(name: str) -> str:
    """Return the normalized display name: stripped of company suffixes, title-cased."""
    name = _SUFFIX_RE.sub("", name.strip())
    return name.strip().title()


def _normalize_key(name: str) -> str:
    """Return lowercase alphanumeric key for deduplication (also strips suffixes)."""
    name = _SUFFIX_RE.sub("", name.lower())
    return _NON_ALNUM.sub("", name)


def get_or_create_deal(
    db: Session,
    organization_id: int,
    raw_name: str,
    existing_deals: list | None = None,
    *,
    user_id: int | None = None,
):
    """
    Look up a Deal by normalized key for this organization; create it if not found.
    Returns the Deal ORM object.

    Pass `existing_deals` (pre-fetched list of Deal ORM objects for this org)
    to avoid a repeated DB scan on every call.  When omitted, falls back to
    querying the DB — preserves backwards compatibility.

    `user_id` is stored on new deals for audit (who originally created it).

    Deduplication: "Acme Corp", "ACME INC", and "acme" all produce key "acme"
    and resolve to the same Deal row.
    """
    from app.models.deal import Deal

    display_name = normalize_deal_name(raw_name)
    key = _normalize_key(raw_name)

    if not key or len(key) < 2:
        return None

    # Exact key match — check cache first, then DB
    if existing_deals is not None:
        deal = next((d for d in existing_deals if d.name_key == key), None)
    else:
        deal = (
            db.query(Deal)
            .filter(Deal.organization_id == organization_id, Deal.name_key == key)
            .first()
        )
    if deal:
        return deal

    try:
        deal = Deal(
            organization_id=organization_id,
            user_id=user_id or 0,
            name=display_name,
            name_key=key,
        )
        db.add(deal)
        db.commit()
        db.refresh(deal)
        # Add to the caller's cache so subsequent lookups see this new deal
        if existing_deals is not None:
            existing_deals.append(deal)
        logger.info(
            f"Created new deal: '{display_name}' (key='{key}') for org {organization_id}"
        )
        return deal
    except IntegrityError:
        # Another concurrent insert beat us — roll back and fetch the winner
        db.rollback()
        return (
            db.query(Deal)
            .filter(Deal.organization_id == organization_id, Deal.name_key == key)
            .first()
        )


# ── LLM-based deal name deduplication ────────────────────────────────────────


def resolve_deal_names_llm(
    new_names: list[str],
    existing_deal_names: list[str],
) -> dict[str, str]:
    """
    Call the LLM to cluster deal names and return a mapping:
      { raw_name → canonical_name } for every name in new_names.

    Also maps existing DB deal names so the LLM can merge new names into
    existing deals when appropriate.

    Falls back to identity mapping (no merging) on any error.
    """
    from worker.batch_analyzer import _get_llm_client, _get_model_name
    from worker.prompts.deal_matching import (
        DEAL_MATCHING_SYSTEM_PROMPT,
        DEAL_MATCHING_USER_PROMPT,
    )

    if not new_names:
        return {}

    # Format the input lists for the prompt
    new_list = "\n".join(f"- {n}" for n in sorted(set(new_names)))
    existing_list = (
        "\n".join(f"- {n}" for n in sorted(set(existing_deal_names)))
        if existing_deal_names
        else "(none)"
    )

    user_prompt = DEAL_MATCHING_USER_PROMPT.format(
        new_names=new_list,
        existing_names=existing_list,
    )

    try:
        client = _get_llm_client()
        response = client.chat.completions.create(
            model=_get_model_name(),
            messages=[
                {"role": "system", "content": DEAL_MATCHING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_completion_tokens=1000,
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        groups = data.get("groups", [])

        # Build mapping: every member → canonical name
        mapping: dict[str, str] = {}
        for group in groups:
            canonical = group.get("canonical", "")
            members = group.get("members", [])
            for member in members:
                if isinstance(member, str) and member.strip():
                    mapping[member.strip()] = canonical.strip()

        logger.info(
            f"LLM deal name dedup: {len(new_names)} names → "
            f"{len(groups)} groups, mapping={mapping}"
        )
        return mapping

    except Exception as exc:
        logger.warning(
            f"LLM deal name dedup failed, falling back to identity: {exc}"
        )
        # Identity mapping — each name maps to itself (no merging)
        return {n: n for n in new_names}
