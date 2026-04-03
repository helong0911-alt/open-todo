"""
Asynchronous Email Worker for Open-Todo (OTD).

Polls the ``email_task`` table for pending / retryable records and delivers
them via SMTP using :func:`api.app.core.email.send_smtp`.

Processing order: ``high`` > ``normal`` > ``low``, then by ``created_at`` ASC.
Implements exponential backoff (2^n minutes) and marks tasks as ``failed``
after ``MAX_RETRIES`` attempts.

This module exposes:
- ``start_email_worker()``: launches the background polling loop.
- ``stop_email_worker()``: signals the loop to stop gracefully.
"""
import logging
from datetime import datetime, timezone

from sqlmodel import Session, select
from sqlalchemy import case

from api.app.core.config import MAIL_ENABLED
from api.app.core.database import engine
from api.app.core.email import send_smtp
from api.app.models.models import EmailTask
from api.app.worker.base import BaseOutboxWorker

logger = logging.getLogger("otd.email_worker")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS: int = 5
"""How often the worker scans for pending email tasks."""

MAX_RETRIES: int = 5
"""After this many failed attempts the task is marked ``failed``."""

# Priority sort mapping: lower number = higher priority
_PRIORITY_ORDER = case(
    (EmailTask.priority == "high", 0),
    (EmailTask.priority == "normal", 1),
    (EmailTask.priority == "low", 2),
    else_=3,
)


# ---------------------------------------------------------------------------
# Core delivery logic
# ---------------------------------------------------------------------------

async def _deliver_email_task(task: EmailTask, max_retries: int) -> None:
    """
    Attempt to render and send an email task via SMTP, then update the
    task status in the database.
    """
    try:
        await send_smtp(
            to_address=task.to_address,
            subject=task.subject,
            template_name=task.template_name,
            template_context=task.template_context if isinstance(task.template_context, dict) else {},
        )

        # --- Success ---
        with Session(engine) as session:
            db_task = session.get(EmailTask, task.task_id)
            if db_task is not None:
                db_task.status = "success"
                db_task.last_error = None
                session.add(db_task)
                session.commit()
        logger.info("Email task %s delivered -> %s", task.task_id, task.to_address)

    except Exception as exc:
        # --- Failure ---
        with Session(engine) as session:
            db_task = session.get(EmailTask, task.task_id)
            if db_task is None:
                return

            db_task.retry_count += 1
            db_task.last_error = f"{type(exc).__name__}: {exc}"

            if db_task.retry_count >= max_retries:
                db_task.status = "failed"
                logger.warning(
                    "Email task %s permanently failed after %d retries: %s",
                    task.task_id, db_task.retry_count, exc,
                )
            else:
                # Exponential backoff: 2^n minutes
                db_task.next_retry_at = BaseOutboxWorker.backoff_next_retry(
                    db_task.retry_count
                )
                db_task.status = "pending"
                logger.info(
                    "Email task %s failed (attempt %d/%d), next retry: %s",
                    task.task_id, db_task.retry_count, max_retries,
                    db_task.next_retry_at,
                )

            session.add(db_task)
            session.commit()


# ---------------------------------------------------------------------------
# Worker implementation
# ---------------------------------------------------------------------------

class EmailOutboxWorker(BaseOutboxWorker):
    """Polls ``email_task`` and delivers via SMTP."""

    def __init__(self) -> None:
        super().__init__(
            name="email_worker",
            poll_interval=POLL_INTERVAL_SECONDS,
            max_retries=MAX_RETRIES,
        )

    async def _poll_batch(self) -> None:
        now = datetime.now(timezone.utc)

        with Session(engine) as session:
            tasks = session.exec(
                select(EmailTask)
                .where(EmailTask.status == "pending")
                .order_by(_PRIORITY_ORDER, EmailTask.created_at)
                .limit(100)
            ).all()

            deliverable = []
            for t in tasks:
                if t.next_retry_at is None or t.next_retry_at <= now:
                    deliverable.append(t)

        # Deliver outside the session (async SMTP)
        if deliverable:
            self.logger.info("Found %d deliverable email task(s)", len(deliverable))
            for task in deliverable:
                await _deliver_email_task(task, self.max_retries)


# ---------------------------------------------------------------------------
# Module-level singleton + compat API
# ---------------------------------------------------------------------------

_worker = EmailOutboxWorker()


async def start_email_worker() -> None:
    """Launch the email polling loop as a background asyncio task."""
    if not MAIL_ENABLED:
        logger.info("Email worker not started (MAIL_ENABLED=false)")
        return
    await _worker.start()


async def stop_email_worker() -> None:
    """Signal the email worker to stop and wait for it to finish."""
    await _worker.stop()
