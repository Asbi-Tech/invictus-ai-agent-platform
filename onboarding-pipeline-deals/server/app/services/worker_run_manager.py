"""
Singleton manager for UI-triggered worker pipeline runs.

Runs the worker in a background thread, tracks progress in-memory (for SSE)
and in the database (for persistence / history), and supports cancellation.
"""

import logging
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.sql import func

from ..database import SessionLocal
from ..models.organization import Organization
from ..models.user import User
from ..models.worker_run import WorkerRun

logger = logging.getLogger(__name__)


class WorkerRunManager:
    """Process-level singleton that manages background worker threads."""

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._global_lock = threading.Lock()
                    inst._active_runs: dict[int, dict] = {}  # org_id → run info
                    inst._progress: dict[int, dict] = {}     # org_id → latest snapshot
                    cls._instance = inst
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────

    def start_run(self, org_id: int, user_id: int) -> int:
        """Start a pipeline run for an organization. Returns the run_id.

        Raises ValueError if a run is already active for this org.
        """
        with self._global_lock:
            if org_id in self._active_runs:
                raise ValueError(f"A pipeline run is already active for org {org_id}")

            # Create the WorkerRun row
            db = SessionLocal()
            try:
                run = WorkerRun(
                    organization_id=org_id,
                    triggered_by=user_id,
                    status="pending",
                )
                db.add(run)
                db.commit()
                db.refresh(run)
                run_id = run.id
            finally:
                db.close()

            cancel_event = threading.Event()
            thread = threading.Thread(
                target=self._run_worker_thread,
                args=(org_id, run_id, cancel_event),
                name=f"worker-org-{org_id}",
                daemon=True,
            )
            self._active_runs[org_id] = {
                "thread": thread,
                "cancel_event": cancel_event,
                "run_id": run_id,
            }
            self._progress[org_id] = {
                "run_id": run_id,
                "stage": "pending",
                "status": "pending",
                "data": {},
            }
            thread.start()
            logger.info(f"Started pipeline run {run_id} for org {org_id}")
            return run_id

    def cancel_run(self, org_id: int) -> bool:
        """Signal cancellation for the active run. Returns True if cancelled."""
        with self._global_lock:
            info = self._active_runs.get(org_id)
            if not info:
                return False
            info["cancel_event"].set()
            logger.info(f"Cancellation requested for org {org_id} run {info['run_id']}")
            return True

    def get_progress(self, org_id: int) -> dict | None:
        """Return the latest progress snapshot for an org, or None."""
        return self._progress.get(org_id)

    def is_running(self, org_id: int) -> bool:
        """Check if a run is currently active for this org."""
        return org_id in self._active_runs

    def get_active_run_id(self, org_id: int) -> int | None:
        """Return the run_id of the active run, or None."""
        info = self._active_runs.get(org_id)
        return info["run_id"] if info else None

    def cleanup_stale_runs(self, org_id: int) -> None:
        """Mark any DB runs stuck in 'running'/'pending' as 'failed' (stale after restart)."""
        db = SessionLocal()
        try:
            stale = (
                db.query(WorkerRun)
                .filter(
                    WorkerRun.organization_id == org_id,
                    WorkerRun.status.in_(["pending", "running"]),
                )
                .all()
            )
            for run in stale:
                if org_id not in self._active_runs or self._active_runs[org_id]["run_id"] != run.id:
                    run.status = "failed"
                    run.error_message = "Server restarted during run"
                    run.finished_at = func.now()
            db.commit()
        finally:
            db.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_worker_thread(self, org_id: int, run_id: int, cancel_event: threading.Event) -> None:
        """Background thread: runs the pipeline for one org."""
        # Lazy import to avoid module-level side effects from worker
        from worker.worker import _process_org_isolated, CancelledError

        db = SessionLocal()
        try:
            # Mark as running
            run = db.query(WorkerRun).filter(WorkerRun.id == run_id).first()
            if run:
                run.status = "running"
                run.current_stage = "discovering_files"
                db.commit()
            self._update_progress(org_id, run_id, "discovering_files", "running", {})

            # Execute the pipeline
            stats = _process_org_isolated(
                org_id,
                progress_callback=lambda stage, data: self._on_progress(
                    org_id, run_id, stage, data
                ),
                cancel_event=cancel_event,
            )

            # Completed successfully
            run = db.query(WorkerRun).filter(WorkerRun.id == run_id).first()
            if run:
                run.status = "completed"
                run.current_stage = None
                if stats:
                    run.progress_data = asdict(stats)
                run.finished_at = func.now()
                db.commit()

            final_data = asdict(stats) if stats else {}
            self._update_progress(org_id, run_id, None, "completed", final_data)
            logger.info(f"Pipeline run {run_id} for org {org_id} completed")

        except CancelledError:
            run = db.query(WorkerRun).filter(WorkerRun.id == run_id).first()
            if run:
                run.status = "cancelled"
                run.current_stage = None
                run.finished_at = func.now()
                db.commit()
            self._update_progress(org_id, run_id, None, "cancelled", {})
            logger.info(f"Pipeline run {run_id} for org {org_id} was cancelled")

        except Exception as exc:
            logger.error(f"Pipeline run {run_id} for org {org_id} failed: {exc}", exc_info=True)
            try:
                run = db.query(WorkerRun).filter(WorkerRun.id == run_id).first()
                if run:
                    run.status = "failed"
                    run.current_stage = None
                    run.error_message = str(exc)[:2000]
                    run.finished_at = func.now()
                    db.commit()
            except Exception:
                logger.error("Failed to update run status after error", exc_info=True)
            self._update_progress(org_id, run_id, None, "failed", {"error": str(exc)[:500]})

        finally:
            db.close()
            with self._global_lock:
                self._active_runs.pop(org_id, None)

    def _on_progress(self, org_id: int, run_id: int, stage: str, data: dict) -> None:
        """Called by the worker at each stage boundary."""
        self._update_progress(org_id, run_id, stage, "running", data)

        # Persist to DB
        db = SessionLocal()
        try:
            run = db.query(WorkerRun).filter(WorkerRun.id == run_id).first()
            if run:
                run.current_stage = stage
                run.progress_data = data
                db.commit()
        except Exception:
            logger.warning(f"Failed to persist progress for run {run_id}", exc_info=True)
        finally:
            db.close()

    def _update_progress(
        self, org_id: int, run_id: int, stage: str | None, status: str, data: dict
    ) -> None:
        """Update the in-memory progress snapshot (read by SSE endpoint)."""
        self._progress[org_id] = {
            "run_id": run_id,
            "stage": stage,
            "status": status,
            "data": data,
        }


# Module-level singleton
worker_run_manager = WorkerRunManager()
