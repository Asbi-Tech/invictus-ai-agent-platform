import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models.user import User
from ..models.document import Document
from ..models.worker_run import WorkerRun
from ..services.worker_run_manager import worker_run_manager
from ..utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])
limiter = Limiter(key_func=get_remote_address)

_JWT_ALGORITHM = "HS256"


@router.get("/status")
@limiter.limit("60/minute")
def sync_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the current sync state and document counts for the user.

    Status values:
      not_connected  – Google Drive not linked
      no_folder      – Drive connected but no folder configured
      processing     – Documents are pending ingestion
      idle           – Everything is up to date
    """
    org_id = current_user.organization_id

    total = db.query(Document).filter(Document.organization_id == org_id).count() if org_id else 0

    processed = (
        db.query(Document)
        .filter(
            Document.organization_id == org_id,
            Document.status.in_(["processed", "vectorized"]),
        )
        .count()
    ) if org_id else 0

    pending = (
        db.query(Document)
        .filter(Document.organization_id == org_id, Document.status == "pending")
        .count()
    ) if org_id else 0

    drive_connected = current_user.refresh_token is not None
    folder_configured = current_user.folder_id is not None

    if not drive_connected:
        status = "not_connected"
    elif not folder_configured:
        status = "no_folder"
    elif pending > 0:
        status = "processing"
    else:
        status = "idle"

    # Worker run status
    is_running = worker_run_manager.is_running(org_id) if org_id else False
    active_run_id = worker_run_manager.get_active_run_id(org_id) if org_id else None

    # Clean up stale runs on first status check
    if org_id and not is_running:
        worker_run_manager.cleanup_stale_runs(org_id)

    return {
        "status": status,
        "next_sync": "02:00 AM",
        "drive_connected": drive_connected,
        "folder_configured": folder_configured,
        "total_documents": total,
        "processed_documents": processed,
        "pending_documents": pending,
        "is_running": is_running,
        "active_run_id": active_run_id,
    }


@router.post("/run")
@limiter.limit("10/minute")
def start_pipeline_run(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a pipeline run for the current user's organization."""
    if current_user.organization_id is None:
        raise HTTPException(status_code=403, detail="No organization assigned")

    org_id = current_user.organization_id
    try:
        run_id = worker_run_manager.start_run(org_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"run_id": run_id, "status": "pending"}


@router.post("/run/cancel")
@limiter.limit("10/minute")
def cancel_pipeline_run(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Cancel the active pipeline run for the current user's organization."""
    if current_user.organization_id is None:
        raise HTTPException(status_code=403, detail="No organization assigned")

    cancelled = worker_run_manager.cancel_run(current_user.organization_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="No active run to cancel")

    return {"cancelled": True}


def _get_user_from_token(token: str) -> User:
    """Validate a JWT token and return the user. Used by SSE endpoint."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()


@router.get("/run/progress")
async def stream_progress(
    request: Request,
    token: str = Query(..., description="JWT access token for SSE auth"),
):
    """SSE stream that pushes real-time progress updates for the active run."""
    user = _get_user_from_token(token)
    org_id = user.organization_id
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization assigned")

    async def event_generator():
        last_snapshot = None
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            progress = worker_run_manager.get_progress(org_id)
            if progress != last_snapshot:
                last_snapshot = progress
                data = json.dumps(progress) if progress else json.dumps({"status": "idle"})
                yield f"data: {data}\n\n"

                # If run is terminal, send final event and close
                if progress and progress.get("status") in ("completed", "failed", "cancelled"):
                    break

            # If no active run and no progress, close stream
            if not worker_run_manager.is_running(org_id) and not progress:
                yield f"data: {json.dumps({'status': 'idle'})}\n\n"
                break

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/run/history")
@limiter.limit("30/minute")
def get_run_history(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Return recent pipeline run history for the user's organization."""
    if current_user.organization_id is None:
        raise HTTPException(status_code=403, detail="No organization assigned")

    runs = (
        db.query(WorkerRun)
        .filter(WorkerRun.organization_id == current_user.organization_id)
        .order_by(WorkerRun.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": r.id,
            "status": r.status,
            "current_stage": r.current_stage,
            "progress_data": r.progress_data,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in runs
    ]
