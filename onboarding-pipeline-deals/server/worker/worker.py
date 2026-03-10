"""
Nightly document processing worker.

Pipeline (per user):
  1.  Fetch all users from the database
  2.  Skip users without Drive connected or folder configured
  3.  Identify new (unprocessed) files in the Drive folder (recursively)
  4.  For each new file: download content + extract text (parallel)
  5.  Batch LLM analysis — all docs in one pass (20 per call, parallel chunks)
      folder_path is passed as a context hint so LLM can factor in location
  6.  Persist all documents (with deal_id) to the database
  7.  Mark superseded versions within each deal
  8.  Send latest docs per type to the vectorizer pipeline

Run manually:
    python server/worker/worker.py   (from project root)
    python worker/worker.py          (from server/)

Scheduled via cron:
    0 2 * * * /path/to/venv/bin/python /path/to/server/worker/worker.py
"""

import fcntl
import logging
import os
import sys
import tempfile
import threading
import time as _time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import sqlalchemy

# ── Path setup ────────────────────────────────────────────────────────────────
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _SERVER_DIR)

from dotenv import load_dotenv  # type: ignore

_env_path = os.path.join(_SERVER_DIR, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)

# ── Internal imports ──────────────────────────────────────────────────────────
from app.config import settings as cfg
from app.constants import PIPELINE_TYPES as _PIPELINE_TYPES_CONST
from app.database import SessionLocal, engine
from app.models.organization import Organization
from app.models.user import User
from app.models.document import Document
from app.models.deal import Deal
from app.services.document_service import (
    update_document,
    get_latest_documents_per_type,
)

from worker.drive_ingestion import (
    get_unprocessed_files,
    fetch_file_content,
    get_user_drive_credentials,
    compute_checksum,
    parse_drive_created_time,
)
from worker.parser import extract_text, extract_page_images, PasswordProtectedError
from worker.batch_analyzer import analyze_batch, AnalysisResult
from worker.deal_resolver import get_or_create_deal
from worker.vectorizer import ingest_and_analyze_deal, rerun_analytical_and_fields

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s – %(message)s"

logger = logging.getLogger("worker")

_standalone_logging_initialized = False


def _setup_standalone_logging() -> None:
    """Configure file + console logging for standalone (CLI/cron) execution.

    Called only from run() and __main__ — NOT at module import time so that
    FastAPI can import worker functions without side effects.
    """
    global _standalone_logging_initialized
    if _standalone_logging_initialized:
        return
    _standalone_logging_initialized = True

    import datetime as _dt

    _LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(_LOG_DIR, exist_ok=True)
    _run_ts = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _log_file = os.path.join(_LOG_DIR, f"worker_{_run_ts}.log")

    _root = logging.getLogger()
    _root.setLevel(logging.INFO)

    _fmt = logging.Formatter(_LOG_FORMAT)

    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    _root.addHandler(_sh)

    _fh = logging.FileHandler(_log_file, encoding="utf-8")
    _fh.setFormatter(_fmt)
    _root.addHandler(_fh)

    logger.info(f"Logging to {_log_file}")

# ── Per-org run statistics ────────────────────────────────────────────────────

@dataclass
class _RunStats:
    org_id: int
    new_files_found: int = 0
    downloaded: int = 0          # successfully downloaded + extracted
    download_failed: int = 0     # download or extraction error
    password_protected: int = 0
    skipped_client: int = 0
    skipped_other: int = 0
    persisted: int = 0           # status=processed
    persist_failed: int = 0
    superseded: int = 0          # marked superseded by version management
    retired_deals: int = 0       # meeting-minutes-only deals retired
    deals_vectorized: int = 0    # deals sent to vectorizer this run
    docs_already_vectorized: int = 0
    dealless_skipped: int = 0
    elapsed_seconds: float = 0.0
    timed_out: bool = False


# ── Timeout helpers ──────────────────────────────────────────────────────────

class _OrgTimeoutError(Exception):
    """Raised when org processing exceeds its time budget."""
    pass


class CancelledError(Exception):
    """Raised when a UI-triggered run is cancelled."""
    pass


def _check_cancel(cancel_event: threading.Event | None, org_id: int, phase: str) -> None:
    """Raise CancelledError if the cancel event is set."""
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError(f"Run cancelled for org {org_id} during {phase}")


def _check_deadline(deadline: float, org_id: int, phase: str) -> None:
    """Raise _OrgTimeoutError if the deadline has passed."""
    if _time.monotonic() > deadline:
        raise _OrgTimeoutError(
            f"Org {org_id} exceeded {cfg.ORG_PROCESSING_TIMEOUT_HOURS}h timeout during {phase}"
        )


# ── Version management ────────────────────────────────────────────────────────

def _bulk_mark_superseded(db, processed_docs: list) -> int:
    """
    Mark older documents as superseded in bulk — one UPDATE per (org_id, doc_type, group)
    instead of one SELECT + commit per document.

    Two-pass strategy:
      Pass A (deal-scoped)   — docs with deal_id: group by (org_id, doc_type, deal_id).
      Pass B (folder-scoped) — docs without deal_id: group by (org_id, doc_type, folder_path).

    Both passes require doc_created_date to determine which is newer.
    """
    # Split into two buckets
    deal_docs: list = []
    folder_docs: list = []
    for doc in processed_docs:
        if not doc.doc_created_date:
            continue
        if doc.deal_id:
            deal_docs.append(doc)
        elif doc.folder_path:
            folder_docs.append(doc)

    total_superseded = 0

    # Pass A: deal-scoped — group by (org_id, doc_type, deal_id), keep newest per group
    a_groups: dict[tuple, list] = {}
    for doc in deal_docs:
        key = (doc.organization_id, doc.doc_type, doc.deal_id)
        a_groups.setdefault(key, []).append(doc)

    for (org_id, doc_type, deal_id), docs in a_groups.items():
        newest = max(docs, key=lambda d: d.doc_created_date)
        exclude_ids = [d.id for d in docs]
        n = (
            db.query(Document)
            .filter(
                Document.organization_id == org_id,
                Document.doc_type == doc_type,
                Document.deal_id == deal_id,
                Document.id.notin_(exclude_ids),
                Document.doc_created_date < newest.doc_created_date,
                Document.version_status == "current",
            )
            .update({"version_status": "superseded"}, synchronize_session="fetch")
        )
        total_superseded += n

    # Pass B: folder-scoped — group by (org_id, doc_type, folder_path)
    b_groups: dict[tuple, list] = {}
    for doc in folder_docs:
        key = (doc.organization_id, doc.doc_type, doc.folder_path)
        b_groups.setdefault(key, []).append(doc)

    for (org_id, doc_type, folder_path), docs in b_groups.items():
        newest = max(docs, key=lambda d: d.doc_created_date)
        exclude_ids = [d.id for d in docs]
        n = (
            db.query(Document)
            .filter(
                Document.organization_id == org_id,
                Document.doc_type == doc_type,
                Document.deal_id.is_(None),
                Document.folder_path == folder_path,
                Document.id.notin_(exclude_ids),
                Document.doc_created_date < newest.doc_created_date,
                Document.version_status == "current",
            )
            .update({"version_status": "superseded"}, synchronize_session="fetch")
        )
        total_superseded += n

    if total_superseded:
        db.commit()
        logger.info(f"Bulk supersede: marked {total_superseded} document(s) as superseded")
    return total_superseded  # always int (0 when nothing was superseded)


# ── Per-org pipeline ──────────────────────────────────────────────────────────

def process_organization(
    db,
    org: Organization,
    users: list[User],
    progress_callback: Callable[[str, dict], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> _RunStats:
    """
    Run the full ingestion pipeline for an organization.

    Collects new files from all users' Drive folders, deduplicates at the org
    level, then processes through LLM classification, deal assignment,
    version management and vectorization.

    Files are processed in memory-bounded batches of cfg.INGEST_BATCH_SIZE to cap
    peak RAM.  Credentials are fetched once per user and reused across all
    downloads.  Version management and vectorization run once after all batches.

    Enforces per-org classification and vectorization quotas.

    Args:
        progress_callback: Optional callback(stage, data_dict) for reporting
            progress to the UI (used by WorkerRunManager).
        cancel_event: Optional threading.Event; if set, the pipeline aborts
            gracefully at the next stage boundary.

    Returns a _RunStats with per-org counters for the final summary.
    """
    stats = _RunStats(org_id=org.id)
    _t0 = _time.monotonic()
    deadline = _t0 + cfg.ORG_PROCESSING_TIMEOUT_HOURS * 3600
    logger.info(f"── Starting pipeline for org {org.id} ({org.name!r}) with {len(users)} user(s)")

    # ── Progress: discovering files ──────────────────────────────────────────
    if progress_callback:
        progress_callback("discovering_files", {})
    _check_cancel(cancel_event, org.id, "discovering_files")

    # ── Collect files from all users' Drive folders, dedup at org level ────────
    all_new_files: list[dict] = []
    user_credentials: dict[int, object] = {}  # user_id → Drive credentials
    seen_file_ids: set[str] = set()

    for user in users:
        user_files = get_unprocessed_files(db, user, organization_id=org.id)
        try:
            creds = get_user_drive_credentials(user)
            user_credentials[user.id] = creds
        except Exception as exc:
            logger.warning(f"Could not get credentials for user {user.id}: {exc}")
            user_credentials[user.id] = None

        for f in user_files:
            if f["id"] not in seen_file_ids:
                seen_file_ids.add(f["id"])
                f["_user_id"] = user.id  # track which user's creds to use
                all_new_files.append(f)

    if not all_new_files:
        logger.info(f"No new files for org {org.id}")
    else:
        # ── Classification quota check ─────────────────────────────────────────
        current_classified = (
            db.query(Document)
            .filter(Document.organization_id == org.id, Document.status != "pending")
            .count()
        )
        remaining_quota = org.classification_limit - current_classified
        if remaining_quota <= 0:
            logger.warning(
                f"Org {org.id} ({org.name!r}) has reached classification limit "
                f"({org.classification_limit}) — skipping all new files"
            )
            all_new_files = []
        elif len(all_new_files) > remaining_quota:
            logger.warning(
                f"Org {org.id}: truncating {len(all_new_files)} new files to "
                f"{remaining_quota} (classification limit={org.classification_limit}, "
                f"used={current_classified})"
            )
            all_new_files = all_new_files[:remaining_quota]

    new_files = all_new_files
    stats.new_files_found = len(new_files)

    # ── Progress: downloading ────────────────────────────────────────────────
    if progress_callback:
        progress_callback("downloading", {"files_found": stats.new_files_found})
    _check_cancel(cancel_event, org.id, "downloading")

    # Accumulate summaries across batches; applied only to current-slot docs
    # after supersede step to avoid summarizing archived/skipped files.
    summary_cache: dict[str, str] = {}

    # Accumulators across all batches
    all_processed_docs: list[Document] = []

    total = len(new_files)
    total_batches = (total + cfg.INGEST_BATCH_SIZE - 1) // cfg.INGEST_BATCH_SIZE

    # Build a user lookup for credential resolution
    users_by_id: dict[int, User] = {u.id: u for u in users}

    for batch_start in range(0, total, cfg.INGEST_BATCH_SIZE):
        batch = new_files[batch_start : batch_start + cfg.INGEST_BATCH_SIZE]
        batch_num = batch_start // cfg.INGEST_BATCH_SIZE + 1
        _check_deadline(deadline, org.id, f"batch {batch_num}/{total_batches}")
        logger.info(
            f"Org {org.id}: batch {batch_num}/{total_batches} — {len(batch)} file(s)"
        )

        # ── Step 1: Download + extract text (parallel) ───────────────────────
        prepared: list[dict] = []

        def _download_and_extract(file_meta: dict) -> dict | None:
            file_id = file_meta["id"]
            file_name = file_meta["name"]
            folder_path = file_meta.get("folder_path", "")
            file_user_id = file_meta.get("_user_id")
            file_user = users_by_id.get(file_user_id, users[0]) if file_user_id else users[0]
            file_creds = user_credentials.get(file_user.id)

            content = fetch_file_content(file_user, file_id, credentials=file_creds)
            if content is None:
                logger.error(f"Skipping '{file_name}' – download failed")
                return None

            try:
                text = extract_text(content, file_name)
            except PasswordProtectedError:
                logger.info(f"'{file_name}' is password-protected — flagging")
                return {
                    "file_meta": file_meta,
                    "content": content,
                    "text": "",
                    "checksum": compute_checksum(content),
                    "drive_created_time": parse_drive_created_time(file_meta),
                    "folder_path": folder_path,
                    "password_protected": True,
                }
            except Exception as exc:
                logger.error(f"Skipping '{file_name}' – text extraction failed: {exc}")
                return None

            page_images = extract_page_images(content, file_name, max_pages=2)

            return {
                "file_meta": file_meta,
                "content": content,
                "text": text,
                "page_images": page_images,
                "checksum": compute_checksum(content),
                "drive_created_time": parse_drive_created_time(file_meta),
                "folder_path": folder_path,
            }

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = {pool.submit(_download_and_extract, fm): fm for fm in batch}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    prepared.append(result)
                    stats.downloaded += 1
                else:
                    stats.download_failed += 1

        # Restore batch ordering (as_completed returns in completion order)
        order = {fm["id"]: idx for idx, fm in enumerate(batch)}
        prepared.sort(key=lambda x: order.get(x["file_meta"]["id"], 0))

        if not prepared:
            continue

        # ── Progress: analyzing ──────────────────────────────────────────────
        if progress_callback:
            progress_callback("analyzing", {
                "files_found": stats.new_files_found,
                "downloaded": stats.downloaded,
                "download_failed": stats.download_failed,
            })
        _check_cancel(cancel_event, org.id, "analyzing")

        # ── Step 2: Batch LLM analysis ───────────────────────────────────────
        llm_results: dict[str, AnalysisResult] = {}
        batch_items = [
            {
                "custom_id": item["file_meta"]["id"],
                "file_name": item["file_meta"]["name"],
                "text": item["text"],
                "folder_path": item["folder_path"],
                "page_images": item.get("page_images", []),
            }
            for item in prepared
            if not item.get("password_protected")
        ]
        analysis = analyze_batch(batch_items, custom_prompt=org.custom_prompt)
        heuristic_count = 0
        for result in analysis:
            llm_results[result.custom_id] = result
            if result.summary:
                summary_cache[result.custom_id] = result.summary
            if result.from_heuristic:
                heuristic_count += 1

        logger.info(
            f"Org {org.id}: {len(prepared)} file(s) through LLM batch "
            f"({heuristic_count} fallback/heuristic)"
        )
        if heuristic_count == len(analysis):
            logger.warning(f"Org {org.id}: ALL results are fallback — LLM batch likely failed entirely")

        # ── Progress: persisting ─────────────────────────────────────────────
        if progress_callback:
            progress_callback("persisting", {
                "files_found": stats.new_files_found,
                "downloaded": stats.downloaded,
                "analyzed": len(llm_results),
            })
        _check_cancel(cancel_event, org.id, "persisting")

        # ── Reconnect DB after potentially long LLM batch ─────────────────────
        # The LLM call can take minutes; Railway's Postgres proxy may drop the
        # idle SSL connection in the meantime.  Always close + reopen the
        # session's connection so SQLAlchemy grabs a fresh one from the pool
        # (pool_pre_ping will verify liveness) before persisting.
        try:
            db.execute(sqlalchemy.text("SELECT 1"))
            logger.debug("DB ping OK before persist step")
        except Exception as _ping_err:
            logger.warning("DB ping failed (%s) – reconnecting", _ping_err)
            try:
                db.rollback()
            except Exception:
                pass
            try:
                db.close()
            except Exception:
                pass
            engine.dispose()  # recycle all pooled connections

        # ── Step 3: Persist ───────────────────────────────────────────────────
        # Pre-fetch all deals for this org once — reused by get_or_create_deal
        # to avoid a DB round-trip per document during fuzzy matching.
        existing_deals = db.query(Deal).filter(Deal.organization_id == org.id).all()

        batch_persisted = 0
        for item in prepared:
            fid = item["file_meta"]["id"]
            fname = item["file_meta"]["name"]
            folder_path = item["folder_path"]

            # ── Password-protected: persist tombstone, infer deal from folder path ──
            file_user_id = item["file_meta"].get("_user_id") or users[0].id

            if item.get("password_protected"):
                try:
                    # Single atomic transaction: INSERT + classify in one commit
                    doc = Document(
                        organization_id=org.id,
                        user_id=file_user_id,
                        file_id=fid,
                        file_name=fname,
                        drive_created_time=item["drive_created_time"],
                        checksum=item["checksum"],
                        doc_type="password_protected",
                        folder_path=folder_path or None,
                        status="skipped",
                    )
                    # Infer deal from first folder component (e.g. "Acme Corp/Q1" → "Acme Corp")
                    locked_deal_id: Optional[int] = None
                    if folder_path:
                        hint = folder_path.split("/")[0].strip()
                        if hint:
                            d = get_or_create_deal(
                                db, org.id, hint, existing_deals, user_id=file_user_id
                            )
                            locked_deal_id = d.id if d else None
                    doc.deal_id = locked_deal_id
                    db.add(doc)
                    db.commit()
                    db.refresh(doc)
                    logger.info(
                        f"Flagged '{fname}' as password-protected — deal_id={locked_deal_id}"
                    )
                    stats.password_protected += 1
                except Exception as exc:
                    logger.error(f"Persist failed for locked '{fname}': {exc}", exc_info=True)
                    db.rollback()
                    stats.persist_failed += 1
                continue

            try:
                # ── Resolve classification fields before touching the DB ──────
                if fid in llm_results:
                    r = llm_results[fid]
                    doc_type = r.doc_type
                    raw_deal_name: Optional[str] = r.deal_name
                    doc_date = r.doc_date or item["drive_created_time"]
                    is_client = r.is_client
                else:
                    # LLM unavailable — store with safe defaults
                    doc_type = "pitch_deck"
                    raw_deal_name = None
                    doc_date = item["drive_created_time"]
                    is_client = False

                # Determine final status and deal_id before any DB write
                if is_client:
                    final_status = "skipped"
                    final_type = "client"
                    deal_id = None
                elif doc_type == "other":
                    final_status = "skipped"
                    final_type = "other"
                    deal_id = None
                else:
                    final_status = "processed"
                    final_type = doc_type
                    deal_id = None
                    if raw_deal_name:
                        deal = get_or_create_deal(
                            db, org.id, raw_deal_name, existing_deals, user_id=file_user_id
                        )
                        deal_id = deal.id if deal else None

                # Single atomic INSERT — create + classify in one commit
                doc = Document(
                    organization_id=org.id,
                    user_id=file_user_id,
                    file_id=fid,
                    file_name=fname,
                    drive_created_time=item["drive_created_time"],
                    checksum=item["checksum"],
                    doc_type=final_type,
                    doc_created_date=doc_date,
                    deal_id=deal_id,
                    folder_path=folder_path or None,
                    status=final_status,
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)

                if is_client:
                    logger.info(f"Skipped '{fname}' — identified as client/portfolio file")
                    stats.skipped_client += 1
                elif final_type == "other":
                    logger.info(f"Skipped '{fname}' — unrelated document (type=other)")
                    stats.skipped_other += 1
                else:
                    logger.info(
                        f"Persisted '{fname}' → type={final_type} deal_id={deal_id} "
                        f"folder='{folder_path}' date={doc_date}"
                    )
                    all_processed_docs.append(doc)
                    batch_persisted += 1
                    stats.persisted += 1

            except Exception as exc:
                logger.error(f"Persist failed for '{fname}': {exc}", exc_info=True)
                db.rollback()
                stats.persist_failed += 1

        logger.info(
            f"Org {org.id}: batch {batch_num}/{total_batches} complete "
            f"({batch_persisted}/{len(prepared)} persisted, "
            f"{len(all_processed_docs)} total so far)"
        )
        # Release batch content bytes — text_cache already holds what we need
        prepared.clear()

    # ── Progress: version management ───────────────────────────────────────
    if progress_callback:
        progress_callback("version_management", {
            "files_found": stats.new_files_found,
            "downloaded": stats.downloaded,
            "persisted": stats.persisted,
            "skipped_client": stats.skipped_client,
            "skipped_other": stats.skipped_other,
        })
    _check_cancel(cancel_event, org.id, "version_management")

    # ── Step 4: Version management (once, after all batches) ─────────────────
    # Running after all docs are persisted is more correct: the full date
    # picture is visible, so older duplicates across batch boundaries are caught.
    stats.superseded = _bulk_mark_superseded(db, all_processed_docs)

    # ── Step 4.5: Retire meeting-minutes-only deals ───────────────────────────
    # A deal whose only classified documents are meeting_minutes is a
    # client/portfolio deal, not a pipeline opportunity.
    # Single SELECT across all touched deals, then one bulk UPDATE — avoids
    # N individual queries + M individual commits that would slow at scale.
    all_deal_ids = list({doc.deal_id for doc in all_processed_docs if doc.deal_id is not None})

    if all_deal_ids:
        deal_docs_all = (
            db.query(Document)
            .filter(
                Document.deal_id.in_(all_deal_ids),
                Document.organization_id == org.id,
                Document.doc_type.in_(list(_PIPELINE_TYPES_CONST) + ["meeting_minutes"]),
                Document.status.in_(["processed", "vectorized"]),
            )
            .all()
        )

        # Group in Python — no extra queries
        by_deal: dict[int, list[Document]] = {}
        for d in deal_docs_all:
            by_deal.setdefault(d.deal_id, []).append(d)

        minutes_only_ids = {
            deal_id
            for deal_id, docs in by_deal.items()
            if not any(d.doc_type in _PIPELINE_TYPES_CONST for d in docs)
        }

        if minutes_only_ids:
            # One UPDATE statement for all affected docs
            db.query(Document).filter(
                Document.deal_id.in_(list(minutes_only_ids)),
                Document.organization_id == org.id,
                Document.status.in_(["processed", "vectorized"]),
            ).update(
                {"doc_type": "client", "status": "skipped"},
                synchronize_session="fetch",
            )
            db.commit()
            all_processed_docs = [
                d for d in all_processed_docs if d.deal_id not in minutes_only_ids
            ]
            stats.retired_deals += len(minutes_only_ids)
            logger.info(
                f"Org {org.id}: retired {len(minutes_only_ids)} "
                f"meeting-minutes-only deal(s) — {sum(len(by_deal[i]) for i in minutes_only_ids)} doc(s) marked client/skipped"
            )

    # ── Step 4.6: Summarize current-slot docs only ───────────────────────────
    # After supersede + retirement we know exactly which docs are "current".
    # Run summarizer only on those to avoid paying for archived/skipped files.
    current_doc_ids = {
        doc.id
        for doc in all_processed_docs
        if doc.version_status == "current"
    }
    if current_doc_ids and summary_cache:
        current_docs = db.query(Document).filter(Document.id.in_(current_doc_ids)).all()
        updated_count = 0
        for doc in current_docs:
            summary = summary_cache.get(doc.file_id)
            if summary and not doc.description:
                doc.description = summary
                updated_count += 1
        if updated_count:
            db.commit()
            logger.info(f"Org {org.id}: set description on {updated_count} current-slot doc(s)")

    # ── Step 5: Vectorize + analyze per deal (requires VECTORIZER_INGEST_URL) ────
    _check_deadline(deadline, org.id, "pre-vectorization")
    _check_cancel(cancel_event, org.id, "pre-vectorization")
    if not cfg.VECTORIZER_INGEST_URL:
        logger.info(
            f"Org {org.id}: VECTORIZER_INGEST_URL not configured — skipping vectorization"
        )
        stats.elapsed_seconds = _time.monotonic() - _t0
        return stats

    # ── Vectorization quota check ──────────────────────────────────────────────
    current_vectorized = (
        db.query(Document)
        .filter(
            Document.organization_id == org.id,
            Document.vectorizer_doc_id.isnot(None),
        )
        .count()
    )
    vec_remaining = org.vectorization_limit - current_vectorized
    if vec_remaining <= 0:
        logger.warning(
            f"Org {org.id} ({org.name!r}) has reached vectorization limit "
            f"({org.vectorization_limit}) — skipping vectorization"
        )
        stats.elapsed_seconds = _time.monotonic() - _t0
        return stats

    latest_docs = get_latest_documents_per_type(db, org.id)

    # Group by deal_id — only deal-associated documents get the full pipeline.
    # Dealless documents are skipped: without a deal they cannot receive an
    # investment_type / deal_status from the Analytical endpoint.
    # Documents that already have a vectorizer_doc_id are also skipped — they
    # were successfully ingested on a previous run.
    per_deal_docs: dict[int, list[Document]] = {}
    dealless_count = 0
    already_vectorized_count = 0
    for doc in latest_docs:
        if doc.deal_id is None:
            dealless_count += 1
        elif doc.vectorizer_doc_id is not None:
            already_vectorized_count += 1
        else:
            per_deal_docs.setdefault(doc.deal_id, []).append(doc)

    # Enforce vectorization quota: limit number of docs sent
    docs_to_vectorize_count = sum(len(docs) for docs in per_deal_docs.values())
    if docs_to_vectorize_count > vec_remaining:
        logger.warning(
            f"Org {org.id}: truncating vectorization to {vec_remaining} docs "
            f"(limit={org.vectorization_limit}, used={current_vectorized})"
        )
        # Truncate by removing deals from the end until within quota
        truncated: dict[int, list[Document]] = {}
        count = 0
        for did, doc_list in per_deal_docs.items():
            if count + len(doc_list) > vec_remaining:
                break
            truncated[did] = doc_list
            count += len(doc_list)
        per_deal_docs = truncated

    stats.deals_vectorized = len(per_deal_docs)
    stats.docs_already_vectorized = already_vectorized_count
    stats.dealless_skipped = dealless_count
    logger.info(
        f"Org {org.id}: {len(per_deal_docs)} deal(s) need vectorization "
        f"({already_vectorized_count} doc(s) already vectorized, "
        f"{dealless_count} dealless doc(s) skipped)"
    )

    # ── Progress: vectorizing ────────────────────────────────────────────────
    if progress_callback:
        progress_callback("vectorizing", {
            "files_found": stats.new_files_found,
            "downloaded": stats.downloaded,
            "persisted": stats.persisted,
            "superseded": stats.superseded,
            "deals_to_vectorize": len(per_deal_docs),
        })
    _check_cancel(cancel_event, org.id, "vectorizing")

    # Pick a user with Drive credentials for the vectorizer (uses first available)
    vec_user_id = users[0].id
    for u in users:
        if user_credentials.get(u.id) is not None:
            vec_user_id = u.id
            break

    # Run deals sequentially — each gets its own DB session via
    # _vectorize_deal_isolated so sessions are never shared across threads.
    # Deadline is checked before each deal to enforce per-org timeout.
    deal_tasks = sorted(
        [
            (vec_user_id, deal_id, [d.id for d in deal_doc_list])
            for deal_id, deal_doc_list in per_deal_docs.items()
        ],
        key=lambda t: len(t[2]),
        reverse=True,
    )
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="vec") as pool:
        for uid, did, doc_ids in deal_tasks:
            _check_deadline(deadline, org.id, f"vectorization deal {did}")
            _check_cancel(cancel_event, org.id, f"vectorization deal {did}")
            future = pool.submit(_vectorize_deal_isolated, uid, did, doc_ids)
            try:
                future.result()  # block until this deal finishes
            except Exception as exc:
                logger.error(
                    f"Deal {did} vectorization thread raised: {exc}",
                    exc_info=exc,
                )

    stats.elapsed_seconds = _time.monotonic() - _t0
    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

def _process_org_isolated(
    org_id: int,
    progress_callback: Callable[[str, dict], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Optional[_RunStats]:
    """Process a single organization in an isolated DB session (safe for threads)."""
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org is None:
            logger.warning(f"Org {org_id} not found — skipping")
            return None
        # Fetch all users in this org who have Drive connected
        org_users = (
            db.query(User)
            .filter(
                User.organization_id == org_id,
                User.refresh_token.isnot(None),
            )
            .all()
        )
        # Further filter to users with at least one configured folder
        org_users = [u for u in org_users if u.drive_folders]
        if not org_users:
            logger.info(f"Org {org_id} ({org.name!r}): no users with Drive connected — skipping")
            return None
        return process_organization(
            db, org, org_users,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
    except _OrgTimeoutError as exc:
        logger.warning(
            f"Org {org_id} TIMED OUT after {cfg.ORG_PROCESSING_TIMEOUT_HOURS}h: {exc}"
        )
        stats = _RunStats(org_id=org_id, timed_out=True)
        stats.elapsed_seconds = cfg.ORG_PROCESSING_TIMEOUT_HOURS * 3600
        return stats
    except Exception as exc:
        logger.error(
            f"Unhandled error for org {org_id}: {exc}",
            exc_info=True,
        )
    finally:
        db.close()

def _vectorize_deal_isolated(user_id: int, deal_id: int, doc_ids: list[int]) -> None:
    """
    Vectorize a single deal in its own DB session — safe to run in a thread.

    Opens a fresh SessionLocal, re-fetches user/deal/docs by primary key, runs
    the full ingest+analyze pipeline, then closes the session.  Each deal
    therefore has an independent connection so multiple deals can be processed
    in parallel without SQLAlchemy "concurrent operations" errors.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if user is None or deal is None:
            logger.warning(f"[vectorizer] user {user_id} or deal {deal_id} missing \u2014 skipping")
            return
        docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        if not docs:
            return
        try:
            ingest_and_analyze_deal(db, user, deal, docs)
        except Exception as exc:
            logger.error(
                f"Vectorization pipeline failed for deal {deal_id}: {exc}",
                exc_info=True,
            )
            # If the crash happened before any doc got a vectorizer_doc_id,
            # clear the job_id so the deal is not hidden from the API and will
            # be retried on the next run.
            db.rollback()
            fresh_deal = db.query(Deal).filter(Deal.id == deal_id).first()
            if fresh_deal and fresh_deal.vectorizer_job_id and fresh_deal.investment_type is None:
                has_any_doc_id = (
                    db.query(Document)
                    .filter(
                        Document.id.in_(doc_ids),
                        Document.vectorizer_doc_id.isnot(None),
                    )
                    .first()
                ) is not None
                if not has_any_doc_id:
                    fresh_deal.vectorizer_job_id = None
                    db.commit()
                    logger.info(
                        f"[vectorizer] Deal {deal_id}: cleared orphaned job_id "
                        "so deal remains visible and will retry next run"
                    )
            return

        # Re-query docs so we see the vectorizer_doc_id values committed by
        # ingest_and_analyze_deal.  Only mark a doc 'vectorized' when it
        # actually received an external doc ID — failed docs stay 'processed'
        # so they are retried on the next worker run.
        fresh_docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        for doc in fresh_docs:
            if doc.vectorizer_doc_id is not None:
                update_document(db, doc.id, status="vectorized")
            else:
                logger.warning(
                    f"[vectorizer] Deal {deal_id}: doc {doc.id} ('{doc.file_name}') "
                    f"has no vectorizer_doc_id — leaving status='{doc.status}' for retry"
                )
    except Exception as exc:
        logger.error(
            f"Vectorization failed for deal {deal_id}: {exc}",
            exc_info=True,
        )
    finally:
        db.close()

def run() -> None:
    """Main worker loop: process all users in parallel (one thread each, max 5)."""
    _setup_standalone_logging()
    _lock_path = os.path.join(tempfile.gettempdir(), "invictus_deals_onboarding_worker.lock")
    lock_file = open(_lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.warning(
            "Another worker instance is already running (lock held at %s) — exiting.",
            _lock_path,
        )
        lock_file.close()
        return

    try:
        _run()
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def _run() -> None:
    """Inner run — called only when the exclusive lock is held."""
    run_start = _time.monotonic()
    logger.info("═══ Invictus Deals Onboarding nightly worker started ═══")
    db = SessionLocal()
    try:
        org_ids = [o.id for o in db.query(Organization.id).all()]
    finally:
        db.close()

    if not org_ids:
        logger.info("No organizations found — nothing to do")
        logger.info("═══ Worker run complete ═══")
        return

    logger.info(f"Found {len(org_ids)} organization(s) — processing in parallel (max 5 threads)")
    max_workers = min(len(org_ids), 5)

    all_stats: list[_RunStats] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process_org_isolated, oid): oid for oid in org_ids}
        for future in as_completed(futures):
            oid = futures[future]
            exc = future.exception()
            if exc:
                logger.error(f"Thread for org {oid} raised: {exc}", exc_info=exc)
            else:
                result = future.result()
                if result is not None:
                    all_stats.append(result)
                logger.info(f"Org {oid} processed successfully")

    # ── Final run summary ─────────────────────────────────────────────────────
    total_elapsed = _time.monotonic() - run_start
    mins, secs = divmod(int(total_elapsed), 60)

    if all_stats:
        t_found       = sum(s.new_files_found for s in all_stats)
        t_downloaded  = sum(s.downloaded for s in all_stats)
        t_dl_failed   = sum(s.download_failed for s in all_stats)
        t_persisted   = sum(s.persisted for s in all_stats)
        t_p_failed    = sum(s.persist_failed for s in all_stats)
        t_locked      = sum(s.password_protected for s in all_stats)
        t_client      = sum(s.skipped_client for s in all_stats)
        t_other       = sum(s.skipped_other for s in all_stats)
        t_superseded  = sum(s.superseded for s in all_stats)
        t_retired     = sum(s.retired_deals for s in all_stats)
        t_vec         = sum(s.deals_vectorized for s in all_stats)
        t_already_vec = sum(s.docs_already_vectorized for s in all_stats)
        t_dealless    = sum(s.dealless_skipped for s in all_stats)
        t_timed_out   = sum(1 for s in all_stats if s.timed_out)

        logger.info(
            "\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║              WORKER RUN SUMMARY                     ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Orgs processed        : {len(all_stats):<27}║\n"
            f"║  Orgs timed out        : {t_timed_out:<27}║\n"
            f"║  Total elapsed         : {f'{mins}m {secs}s':<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  New files found       : {t_found:<27}║\n"
            f"║  Downloaded & parsed   : {t_downloaded:<27}║\n"
            f"║  Download failures     : {t_dl_failed:<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Persisted (processed) : {t_persisted:<27}║\n"
            f"║  Persist failures      : {t_p_failed:<27}║\n"
            f"║  Password-protected    : {t_locked:<27}║\n"
            f"║  Skipped (client)      : {t_client:<27}║\n"
            f"║  Skipped (other)       : {t_other:<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Versions superseded   : {t_superseded:<27}║\n"
            f"║  Deals retired (mins)  : {t_retired:<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Deals vectorized      : {t_vec:<27}║\n"
            f"║  Docs already vec'd    : {t_already_vec:<27}║\n"
            f"║  Dealless docs skipped : {t_dealless:<27}║\n"
            "╚══════════════════════════════════════════════════════╝"
        )
    else:
        logger.info(f"No stats collected (elapsed: {mins}m {secs}s)")

    logger.info("═══ Worker run complete ═══")


def run_vectorizer_only() -> None:
    """
    Skip Drive sync + LLM analysis.  Runs the full vectorizer pipeline
    (Stages 1–7) for all deals with incomplete pipeline state:

      Case A — Unvectorized docs (vectorizer_doc_id IS NULL)
                → full Stage 1–7 via ingest_and_analyze_deal

      Case B — All docs vectorized but investment_type IS NULL
                → Stage 6 (Analytical) + Stage 7 (ExtractFields)

      Case C — investment_type set but deal_fields table empty
                → Stage 7 (ExtractFields) only
    """
    _setup_standalone_logging()
    logger.info("═══ Vectorizer-only run started ═══")
    db = SessionLocal()
    try:
        org_ids = [o.id for o in db.query(Organization.id).all()]
    finally:
        db.close()

    for oid in org_ids:
        db = SessionLocal()
        try:
            org = db.query(Organization).filter(Organization.id == oid).first()
            if not org:
                continue

            # Find a user with Drive credentials for this org
            org_users = (
                db.query(User)
                .filter(
                    User.organization_id == oid,
                    User.refresh_token.isnot(None),
                )
                .all()
            )
            uid = org_users[0].id if org_users else 0

            latest_docs = get_latest_documents_per_type(db, oid)

            # Case A: deals with at least one unvectorized doc → full Stage 1-7
            per_deal_unvec: dict[int, list[int]] = {}
            # Deals fully vectorized — check if Stage 6/7 are incomplete
            fully_vec_deal_ids: set[int] = set()
            per_deal_all: dict[int, list] = {}
            for doc in latest_docs:
                if doc.deal_id is None:
                    continue
                per_deal_all.setdefault(doc.deal_id, []).append(doc)

            for deal_id, docs in per_deal_all.items():
                unvec = [d for d in docs if d.vectorizer_doc_id is None]
                if unvec:
                    per_deal_unvec[deal_id] = [d.id for d in docs]
                else:
                    fully_vec_deal_ids.add(deal_id)

            # Case B/C: fully vectorized deals missing Stage 6 or 7
            partial_deals: list[Deal] = []
            if fully_vec_deal_ids:
                from app.models.deal_field import DealField
                candidate_deals = (
                    db.query(Deal)
                    .filter(Deal.id.in_(fully_vec_deal_ids))
                    .all()
                )
                field_counts: dict[int, int] = {
                    row.deal_id: row.cnt
                    for row in db.query(
                        DealField.deal_id,
                        sqlalchemy.func.count(DealField.id).label("cnt"),
                    )
                    .filter(DealField.deal_id.in_(fully_vec_deal_ids))
                    .group_by(DealField.deal_id)
                    .all()
                }
                for deal in candidate_deals:
                    missing_type = deal.investment_type is None
                    missing_fields = field_counts.get(deal.id, 0) == 0
                    if missing_type or missing_fields:
                        partial_deals.append(deal)

            logger.info(
                f"Org {oid}: {len(per_deal_unvec)} deal(s) need full vectorization (Case A), "
                f"{len(partial_deals)} deal(s) need Stage 6/7 only (Cases B/C)"
            )
        finally:
            db.close()

        # Case A — full Stage 1-7 (most docs first)
        if per_deal_unvec:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="vec") as pool:
                futures = {
                    pool.submit(_vectorize_deal_isolated, uid, did, doc_ids): did
                    for did, doc_ids in sorted(
                        per_deal_unvec.items(), key=lambda kv: len(kv[1]), reverse=True
                    )
                }
                for future in as_completed(futures):
                    deal_id = futures[future]
                    exc = future.exception()
                    if exc:
                        logger.error(
                            f"Deal {deal_id} vectorization thread raised: {exc}",
                            exc_info=exc,
                        )

        # Cases B/C — re-run Stage 6 and/or Stage 7 only
        for deal in partial_deals:
            db = SessionLocal()
            try:
                fresh_deal = db.query(Deal).filter(Deal.id == deal.id).first()
                if fresh_deal:
                    rerun_analytical_and_fields(db, fresh_deal)
            except Exception as exc:
                logger.error(
                    f"[vectorizer] Deal {deal.id} Stage 6/7 re-run failed: {exc}",
                    exc_info=True,
                )
            finally:
                db.close()

    logger.info("═══ Vectorizer-only run complete ═══")


if __name__ == "__main__":
    import sys
    if "--vectorize-only" in sys.argv:
        run_vectorizer_only()
    else:
        run()
