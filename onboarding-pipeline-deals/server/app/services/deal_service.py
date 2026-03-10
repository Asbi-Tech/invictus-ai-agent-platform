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


# ── Merge ────────────────────────────────────────────────────────────────────


def merge_deals(
    db: Session,
    source_deal_id: int,
    target_deal_id: int,
    organization_id: int,
    new_name: Optional[str] = None,
) -> dict:
    """
    Merge source deal into target deal.

    - Documents from source are reassigned to target.
    - When both deals have a current doc of the same type, the newer one
      (by doc_created_date) stays current; the older one is superseded.
    - Analytical results and vectorizer state are cleared so the worker
      re-processes the merged deal on its next run.
    - The source deal is deleted after merge.
    """
    if source_deal_id == target_deal_id:
        raise HTTPException(
            status_code=400, detail="Cannot merge a deal with itself"
        )

    # Fetch both deals with org ownership check
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

    # ── Version conflict resolution ──────────────────────────────────────
    # For each doc_type, if both deals have a current doc, keep the newer one.

    source_docs = (
        db.query(Document)
        .filter(
            Document.deal_id == source_deal_id,
            Document.version_status == "current",
            Document.doc_type.in_(DOC_TYPES),
        )
        .all()
    )
    target_docs = (
        db.query(Document)
        .filter(
            Document.deal_id == target_deal_id,
            Document.version_status == "current",
            Document.doc_type.in_(DOC_TYPES),
        )
        .all()
    )

    # Build lookup: doc_type → newest current doc per deal
    source_by_type: dict[str, Document] = {}
    for doc in source_docs:
        existing = source_by_type.get(doc.doc_type)
        if existing is None or (
            doc.doc_created_date
            and (
                existing.doc_created_date is None
                or doc.doc_created_date > existing.doc_created_date
            )
        ):
            source_by_type[doc.doc_type] = doc

    target_by_type: dict[str, Document] = {}
    for doc in target_docs:
        existing = target_by_type.get(doc.doc_type)
        if existing is None or (
            doc.doc_created_date
            and (
                existing.doc_created_date is None
                or doc.doc_created_date > existing.doc_created_date
            )
        ):
            target_by_type[doc.doc_type] = doc

    # Resolve conflicts: when both have the same type, supersede the older one
    documents_superseded = 0
    for dtype in DOC_TYPES:
        s_doc = source_by_type.get(dtype)
        t_doc = target_by_type.get(dtype)
        if s_doc and t_doc:
            # Determine which is newer; tie-break: target wins
            s_date = s_doc.doc_created_date
            t_date = t_doc.doc_created_date
            if s_date and (t_date is None or s_date > t_date):
                # Source doc is newer — supersede target's doc
                t_doc.version_status = "superseded"
            else:
                # Target doc is newer or tie — supersede source's doc
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
