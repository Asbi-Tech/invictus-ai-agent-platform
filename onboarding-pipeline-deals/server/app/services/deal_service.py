"""Deal management operations: delete and merge."""

import logging
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.deal import Deal
from ..models.deal_field import DealField
from ..models.document import Document
from ..constants import DOC_TYPES

logger = logging.getLogger(__name__)

# ── Name normalization (replicated from worker.deal_resolver lines 62-103) ───

_SUFFIX_RE = re.compile(
    r"\s*(,\s*)?(inc\.?|incorporated|ltd\.?|limited|llc\.?|llp\.?|corp\.?|"
    r"corporation|co\.?|group|holdings|ventures|capital|partners|fund)\s*$",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize_deal_name(name: str) -> str:
    return _SUFFIX_RE.sub("", name.strip()).strip().title()


def _normalize_deal_key(name: str) -> str:
    return _NON_ALNUM.sub("", _SUFFIX_RE.sub("", name.lower()))


# ── Delete ───────────────────────────────────────────────────────────────────


def delete_deal(db: Session, deal_id: int, organization_id: int) -> dict:
    """
    Delete a deal, unlinking its documents so they can be re-grouped later.

    Documents are NOT deleted — they are unlinked (deal_id=NULL) with
    vectorizer state cleared so the worker can re-process them.
    DealField rows cascade-delete automatically.
    """
    deal = (
        db.query(Deal)
        .filter(Deal.id == deal_id, Deal.organization_id == organization_id)
        .first()
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    deal_name = deal.name

    # Collect doc IDs before unlinking (needed for targeted status reset)
    doc_ids = [
        row[0]
        for row in db.query(Document.id).filter(Document.deal_id == deal_id).all()
    ]
    doc_count = len(doc_ids)

    if doc_ids:
        # Reset vectorized → processed first (while we can still filter by deal_id)
        db.query(Document).filter(
            Document.id.in_(doc_ids),
            Document.status == "vectorized",
        ).update({"status": "processed"}, synchronize_session="fetch")

        # Unlink documents: clear deal association and vectorizer state
        db.query(Document).filter(Document.id.in_(doc_ids)).update(
            {
                "deal_id": None,
                "vectorizer_doc_id": None,
                "version_status": "current",
            },
            synchronize_session="fetch",
        )

    # Delete the deal (DealField rows cascade via relationship)
    db.delete(deal)
    db.commit()

    logger.info(
        f"Deleted deal {deal_id} ({deal_name!r}), unlinked {doc_count} document(s)"
    )

    return {
        "deal_id": deal_id,
        "deal_name": deal_name,
        "documents_unlinked": doc_count,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

_TYPE_LABELS: dict[str, str] = {
    "pitch_deck": "Pitch Deck",
    "investment_memo": "Investment Memo",
    "prescreening_report": "Prescreening Report",
    "meeting_minutes": "Meeting Minutes",
}


def _fmt_date(dt) -> str | None:
    return dt.strftime("%Y-%m-%d") if dt else None


def _best_current_doc_per_type(docs: list[Document]) -> dict[str, Document]:
    """Pick the newest current doc per doc_type from a list of documents."""
    by_type: dict[str, Document] = {}
    for doc in docs:
        existing = by_type.get(doc.doc_type)
        if existing is None or (
            doc.doc_created_date
            and (
                existing.doc_created_date is None
                or doc.doc_created_date > existing.doc_created_date
            )
        ):
            by_type[doc.doc_type] = doc
    return by_type


def _fetch_current_docs(db: Session, deal_id: int) -> list[Document]:
    return (
        db.query(Document)
        .filter(
            Document.deal_id == deal_id,
            Document.version_status == "current",
            Document.doc_type.in_(DOC_TYPES),
        )
        .all()
    )


def _validate_merge_deals(
    db: Session, source_deal_id: int, target_deal_id: int, organization_id: int
) -> tuple[Deal, Deal]:
    """Validate and return (source_deal, target_deal)."""
    if source_deal_id == target_deal_id:
        raise HTTPException(
            status_code=400, detail="Cannot merge a deal with itself"
        )

    source_deal = (
        db.query(Deal)
        .filter(Deal.id == source_deal_id, Deal.organization_id == organization_id)
        .first()
    )
    if not source_deal:
        raise HTTPException(status_code=404, detail="Source deal not found")

    target_deal = (
        db.query(Deal)
        .filter(Deal.id == target_deal_id, Deal.organization_id == organization_id)
        .first()
    )
    if not target_deal:
        raise HTTPException(status_code=404, detail="Target deal not found")

    return source_deal, target_deal


# ── Preview merge (LLM-assisted) ────────────────────────────────────────────


def preview_merge(
    db: Session,
    source_deal_id: int,
    target_deal_id: int,
    organization_id: int,
    new_name: Optional[str] = None,
) -> dict:
    """
    Preview a merge: find doc-type conflicts and get LLM recommendations.

    Returns a dict matching MergePreviewResponse schema.
    """
    from .llm_merge import resolve_merge_conflict

    source_deal, target_deal = _validate_merge_deals(
        db, source_deal_id, target_deal_id, organization_id
    )

    source_by_type = _best_current_doc_per_type(_fetch_current_docs(db, source_deal_id))
    target_by_type = _best_current_doc_per_type(_fetch_current_docs(db, target_deal_id))

    deal_name = new_name.strip() if new_name and new_name.strip() else target_deal.name

    conflicts = []
    conflict_types = set()
    for dtype in DOC_TYPES:
        s_doc = source_by_type.get(dtype)
        t_doc = target_by_type.get(dtype)
        if s_doc and t_doc:
            conflict_types.add(dtype)
            llm_result = resolve_merge_conflict(
                doc_type_label=_TYPE_LABELS.get(dtype, dtype),
                deal_name=deal_name,
                source_deal_name=source_deal.name,
                target_deal_name=target_deal.name,
                source_file_name=s_doc.file_name,
                source_date=_fmt_date(s_doc.doc_created_date),
                source_description=s_doc.description,
                target_file_name=t_doc.file_name,
                target_date=_fmt_date(t_doc.doc_created_date),
                target_description=t_doc.description,
            )
            conflicts.append({
                "doc_type": dtype,
                "doc_type_label": _TYPE_LABELS.get(dtype, dtype),
                "source_doc": {
                    "id": s_doc.id,
                    "file_name": s_doc.file_name,
                    "date": _fmt_date(s_doc.doc_created_date),
                    "description": s_doc.description,
                },
                "target_doc": {
                    "id": t_doc.id,
                    "file_name": t_doc.file_name,
                    "date": _fmt_date(t_doc.doc_created_date),
                    "description": t_doc.description,
                },
                "recommendation": llm_result["recommendation"],
                "reason": llm_result["reason"],
            })

    # Count source docs that will move without conflict
    total_source_docs = (
        db.query(Document)
        .filter(Document.deal_id == source_deal_id)
        .count()
    )

    source_doc_count = sum(1 for v in source_by_type.values() if v is not None)
    target_doc_count = sum(1 for v in target_by_type.values() if v is not None)

    return {
        "source_deal": {
            "id": source_deal.id,
            "name": source_deal.name,
            "doc_count": source_doc_count,
        },
        "target_deal": {
            "id": target_deal.id,
            "name": target_deal.name,
            "doc_count": target_doc_count,
        },
        "conflicts": conflicts,
        "documents_to_move": total_source_docs,
    }


# ── Merge ────────────────────────────────────────────────────────────────────


def merge_deals(
    db: Session,
    source_deal_id: int,
    target_deal_id: int,
    organization_id: int,
    new_name: Optional[str] = None,
    resolutions: Optional[list[dict]] = None,
) -> dict:
    """
    Merge source deal into target deal.

    - Documents from source are reassigned to target.
    - When both deals have a current doc of the same type:
      - If resolutions are provided (from user via preview), use those choices.
      - Otherwise fall back to date-based comparison (newer stays current).
    - Analytical results and vectorizer state are cleared so the worker
      re-processes the merged deal on its next run.
    - The source deal is deleted after merge.
    """
    source_deal, target_deal = _validate_merge_deals(
        db, source_deal_id, target_deal_id, organization_id
    )

    source_by_type = _best_current_doc_per_type(_fetch_current_docs(db, source_deal_id))
    target_by_type = _best_current_doc_per_type(_fetch_current_docs(db, target_deal_id))

    # Build resolution lookup: doc_type → keep_doc_id
    resolution_map: dict[str, int] = {}
    if resolutions:
        for r in resolutions:
            resolution_map[r["doc_type"]] = r["keep_doc_id"]

    # ── Version conflict resolution ──────────────────────────────────────
    documents_superseded = 0
    for dtype in DOC_TYPES:
        s_doc = source_by_type.get(dtype)
        t_doc = target_by_type.get(dtype)
        if s_doc and t_doc:
            if dtype in resolution_map:
                # User chose which to keep
                keep_id = resolution_map[dtype]
                if keep_id == s_doc.id:
                    t_doc.version_status = "superseded"
                else:
                    s_doc.version_status = "superseded"
            else:
                # Fallback: date-based, tie-break: target wins
                s_date = s_doc.doc_created_date
                t_date = t_doc.doc_created_date
                if s_date and (t_date is None or s_date > t_date):
                    t_doc.version_status = "superseded"
                else:
                    s_doc.version_status = "superseded"
            documents_superseded += 1

    # ── Reassign all source documents to target deal ─────────────────────
    documents_moved = (
        db.query(Document)
        .filter(Document.deal_id == source_deal_id)
        .update({"deal_id": target_deal_id}, synchronize_session="fetch")
    )

    # ── Rename target deal if requested ──────────────────────────────────
    if new_name and new_name.strip():
        normalized_name = _normalize_deal_name(new_name)
        normalized_key = _normalize_deal_key(new_name)

        # Check for name collision with other deals in the org
        collision = (
            db.query(Deal.id)
            .filter(
                Deal.organization_id == organization_id,
                Deal.name_key == normalized_key,
                Deal.id != target_deal_id,
            )
            .first()
        )
        if collision:
            raise HTTPException(
                status_code=409,
                detail="A deal with this name already exists",
            )

        target_deal.name = normalized_name
        target_deal.name_key = normalized_key

    # ── Clear analytical results for re-processing ───────────────────────
    target_deal.vectorizer_job_id = None
    target_deal.investment_type = None
    target_deal.deal_status = None
    target_deal.deal_reason = None

    # Delete deal fields (will be re-extracted after re-vectorization)
    db.query(DealField).filter(DealField.deal_id == target_deal_id).delete(
        synchronize_session="fetch"
    )

    # Clear vectorizer_doc_id on all merged docs so worker re-vectorizes
    db.query(Document).filter(Document.deal_id == target_deal_id).update(
        {"vectorizer_doc_id": None}, synchronize_session="fetch"
    )

    # Reset vectorized docs back to processed
    db.query(Document).filter(
        Document.deal_id == target_deal_id,
        Document.status == "vectorized",
    ).update({"status": "processed"}, synchronize_session="fetch")

    # ── Delete source deal (DealField rows cascade) ──────────────────────
    db.delete(source_deal)
    db.commit()

    logger.info(
        f"Merged deal {source_deal_id} into {target_deal_id} "
        f"({target_deal.name!r}): moved {documents_moved} doc(s), "
        f"superseded {documents_superseded}"
    )

    return {
        "target_deal_id": target_deal_id,
        "target_deal_name": target_deal.name,
        "source_deal_id": source_deal_id,
        "documents_moved": documents_moved,
        "documents_superseded": documents_superseded,
    }
