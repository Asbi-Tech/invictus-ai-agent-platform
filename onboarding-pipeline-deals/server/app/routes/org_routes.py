import logging
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..config import settings
from ..database import get_db
from ..models.organization import Organization
from ..models.user import User
from ..models.document import Document
from ..models.deal import Deal
from ..schemas.org_schema import (
    OrgCreateRequest,
    OrgJoinRequest,
    OrgSettingsUpdate,
    OrgResponse,
    OrgQuotaResponse,
    OrgListItem,
)
from ..utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/org", tags=["organization"])
limiter = Limiter(key_func=get_remote_address)

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize_key(name: str) -> str:
    """Lowercase alphanumeric slug for org deduplication."""
    return _NON_ALNUM.sub("", name.lower().strip())


def _classification_count(db: Session, org_id: int) -> int:
    return (
        db.query(Document)
        .filter(Document.organization_id == org_id, Document.status != "pending")
        .count()
    )


def _vectorization_count(db: Session, org_id: int) -> int:
    return (
        db.query(Document)
        .filter(
            Document.organization_id == org_id,
            Document.vectorizer_doc_id.isnot(None),
        )
        .count()
    )


@router.post("/create", response_model=OrgResponse)
@limiter.limit("20/minute")
def create_org(
    body: OrgCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgResponse:
    """Create a new organization and assign the current user to it."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Organization name is required")

    key = _normalize_key(name)
    if not key or len(key) < 2:
        raise HTTPException(status_code=400, detail="Organization name too short")

    existing = db.query(Organization).filter(Organization.name_key == key).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Organization '{existing.name}' already exists. Use the join endpoint instead.",
        )

    org = Organization(
        name=name,
        name_key=key,
        classification_limit=settings.DEFAULT_CLASSIFICATION_LIMIT,
        vectorization_limit=settings.DEFAULT_VECTORIZATION_LIMIT,
    )
    db.add(org)
    db.flush()

    current_user.organization_id = org.id
    # Sync company_name for backwards compat
    current_user.company_name = name
    db.commit()
    db.refresh(org)

    logger.info(f"User {current_user.id} created org '{name}' (id={org.id})")
    return OrgResponse.model_validate(org)


@router.post("/join", response_model=OrgResponse)
@limiter.limit("20/minute")
def join_org(
    body: OrgJoinRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgResponse:
    """Join an existing organization. Optionally migrate data from the user's current org."""
    org = db.query(Organization).filter(Organization.id == body.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    old_org_id = current_user.organization_id

    if old_org_id == org.id:
        raise HTTPException(status_code=400, detail="Already a member of this organization")

    # Migrate data if requested and user has an existing org
    if body.migrate_data and old_org_id is not None:
        _migrate_data(db, old_org_id, org.id)

    current_user.organization_id = org.id
    current_user.company_name = org.name
    db.commit()
    db.refresh(org)

    logger.info(
        f"User {current_user.id} joined org '{org.name}' (id={org.id})"
        f"{' with data migration' if body.migrate_data else ''}"
    )
    return OrgResponse.model_validate(org)


def _migrate_data(db: Session, from_org_id: int, to_org_id: int) -> None:
    """Move documents and deals from one org to another, handling dedup."""
    # Get file_ids already in the target org to avoid unique constraint violations
    existing_file_ids = {
        row[0]
        for row in db.query(Document.file_id)
        .filter(Document.organization_id == to_org_id)
        .all()
    }

    # Move non-conflicting documents
    docs_to_move = (
        db.query(Document)
        .filter(
            Document.organization_id == from_org_id,
            Document.file_id.notin_(existing_file_ids) if existing_file_ids else True,
        )
        .all()
    )
    for doc in docs_to_move:
        doc.organization_id = to_org_id

    # Get deal name_keys already in the target org
    existing_deal_keys = {
        row[0]
        for row in db.query(Deal.name_key)
        .filter(Deal.organization_id == to_org_id)
        .all()
    }

    # For deals that already exist in target: reassign their documents
    deals_to_merge = (
        db.query(Deal)
        .filter(
            Deal.organization_id == from_org_id,
            Deal.name_key.in_(existing_deal_keys) if existing_deal_keys else False,
        )
        .all()
    )
    for old_deal in deals_to_merge:
        target_deal = (
            db.query(Deal)
            .filter(Deal.organization_id == to_org_id, Deal.name_key == old_deal.name_key)
            .first()
        )
        if target_deal:
            # Reassign docs from old deal to target deal (that were already moved above)
            db.query(Document).filter(
                Document.deal_id == old_deal.id,
                Document.organization_id == to_org_id,
            ).update({"deal_id": target_deal.id}, synchronize_session="fetch")

    # Move remaining deals (no name conflict)
    db.query(Deal).filter(
        Deal.organization_id == from_org_id,
        Deal.name_key.notin_(existing_deal_keys) if existing_deal_keys else True,
    ).update({"organization_id": to_org_id}, synchronize_session="fetch")

    db.flush()


@router.get("/list", response_model=List[OrgListItem])
@limiter.limit("30/minute")
def list_orgs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[OrgListItem]:
    """List all organizations with member counts."""
    from sqlalchemy import func

    rows = (
        db.query(
            Organization.id,
            Organization.name,
            func.count(User.id).label("member_count"),
        )
        .outerjoin(User, User.organization_id == Organization.id)
        .group_by(Organization.id)
        .order_by(Organization.name)
        .all()
    )
    return [
        OrgListItem(id=r.id, name=r.name, member_count=r.member_count)
        for r in rows
    ]


@router.get("/me", response_model=OrgQuotaResponse)
@limiter.limit("60/minute")
def get_my_org(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgQuotaResponse:
    """Return the current user's organization with quota usage."""
    if current_user.organization_id is None:
        raise HTTPException(status_code=403, detail="No organization assigned")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    member_count = (
        db.query(User).filter(User.organization_id == org.id).count()
    )

    return OrgQuotaResponse(
        id=org.id,
        name=org.name,
        classification_used=_classification_count(db, org.id),
        classification_limit=org.classification_limit,
        vectorization_used=_vectorization_count(db, org.id),
        vectorization_limit=org.vectorization_limit,
        member_count=member_count,
        custom_prompt=org.custom_prompt,
        processing_timeout_hours=settings.ORG_PROCESSING_TIMEOUT_HOURS,
        tenant_id=org.tenant_id,
    )


@router.patch("/settings", response_model=OrgQuotaResponse)
@limiter.limit("30/minute")
def update_org_settings(
    body: OrgSettingsUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgQuotaResponse:
    """Update organization settings (custom prompt)."""
    if current_user.organization_id is None:
        raise HTTPException(status_code=403, detail="No organization assigned")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if body.custom_prompt is not None:
        org.custom_prompt = body.custom_prompt or None
    if body.classification_limit is not None:
        if body.classification_limit < 0:
            raise HTTPException(status_code=400, detail="Classification limit must be non-negative")
        org.classification_limit = body.classification_limit
    if body.vectorization_limit is not None:
        if body.vectorization_limit < 0:
            raise HTTPException(status_code=400, detail="Vectorization limit must be non-negative")
        org.vectorization_limit = body.vectorization_limit
    if body.tenant_id is not None:
        org.tenant_id = body.tenant_id.strip() or None

    db.commit()
    db.refresh(org)

    member_count = db.query(User).filter(User.organization_id == org.id).count()

    return OrgQuotaResponse(
        id=org.id,
        name=org.name,
        classification_used=_classification_count(db, org.id),
        classification_limit=org.classification_limit,
        vectorization_used=_vectorization_count(db, org.id),
        vectorization_limit=org.vectorization_limit,
        member_count=member_count,
        custom_prompt=org.custom_prompt,
        processing_timeout_hours=settings.ORG_PROCESSING_TIMEOUT_HOURS,
        tenant_id=org.tenant_id,
    )
