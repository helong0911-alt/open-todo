"""
Asynchronous Outbox Worker for Open-Todo (OTD).

Polls the ``webhook_task`` table for pending / retryable records and delivers
them via async HTTP POST using ``httpx``.  Implements exponential backoff
(2^n minutes) and marks tasks as ``failed`` after ``MAX_RETRIES`` attempts.

When a task permanently fails, an alert email is enqueued for the project
owner (if they have an enabled ``WebhookFailure`` notification rule).

This module exposes:
- ``start_outbox_worker()``: launches the background polling loop (to be
  called inside FastAPI's lifespan).
- ``stop_outbox_worker()``: signals the loop to stop gracefully.

The worker runs as an ``asyncio.Task`` — it never blocks the main API
event loop.
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from api.app.core.database import engine
from api.app.core.email import enqueue_webhook_failure_alert
from api.app.models.models import WebhookTask, WebhookRule, Project, User
from api.app.worker.base import BaseOutboxWorker

logger = logging.getLogger("otd.outbox_worker")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS: int = 5
"""How often the worker scans for pending tasks."""

HTTP_TIMEOUT_SECONDS: int = 15
"""Timeout for each outgoing webhook HTTP POST."""

MAX_RETRIES: int = 5
"""After this many failed attempts the task is marked ``failed``."""


# ---------------------------------------------------------------------------
# Failure alert helper
# ---------------------------------------------------------------------------

def _enqueue_failure_alert(
    session: Session, task: WebhookTask, webhook_url: str
) -> None:
    """
    Look up the project owner and enqueue a ``WebhookFailure`` alert email
    if the user has an enabled notification rule for that event type.
    """
    try:
        rule = session.get(WebhookRule, task.rule_id)
        if rule is None:
            return

        project = session.get(Project, rule.project_id)
        if project is None:
            return

        user = session.get(User, project.user_id)
        if user is None:
            return

        enqueue_webhook_failure_alert(
            session=session,
            user_id=user.user_id,
            to_address=user.email,
            webhook_url=webhook_url,
            rule_id=task.rule_id,
            task_id=task.task_id,
            retry_count=task.retry_count,
            last_error=task.last_error or "Unknown error.",
        )
        # Commit is handled by the caller after updating db_task status.
    except Exception:
        logger.exception(
            "Failed to enqueue webhook failure alert for task %s", task.task_id
        )


# ---------------------------------------------------------------------------
# Core delivery logic
# ---------------------------------------------------------------------------

async def _deliver_task(
    task: WebhookTask, webhook_url: str, max_retries: int
) -> None:
    """
    Attempt to POST the task payload to the webhook URL.
    Updates task status, retry_count, next_retry_at, and last_error
    within a synchronous session (SQLite doesn't support async drivers
    natively, so we keep the DB access synchronous).
    """
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                webhook_url,
                json=task.payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

        # --- Success ---
        with Session(engine) as session:
            db_task = session.get(WebhookTask, task.task_id)
            if db_task is not None:
                db_task.status = "success"
                db_task.last_error = None
                session.add(db_task)
                session.commit()
        logger.info("Delivered task %s -> %s (HTTP %s)", task.task_id, webhook_url, response.status_code)

    except Exception as exc:
        # --- Failure ---
        with Session(engine) as session:
            db_task = session.get(WebhookTask, task.task_id)
            if db_task is None:
                return

            db_task.retry_count += 1
            db_task.last_error = f"{type(exc).__name__}: {exc}"

            if db_task.retry_count >= max_retries:
                db_task.status = "failed"
                logger.warning(
                    "Task %s permanently failed after %d retries: %s",
                    task.task_id, db_task.retry_count, exc,
                )

                # --- Enqueue webhook failure alert email ---
                _enqueue_failure_alert(session, db_task, webhook_url)
            else:
                # Exponential backoff: 2^n minutes
                db_task.next_retry_at = BaseOutboxWorker.backoff_next_retry(
                    db_task.retry_count
                )
                db_task.status = "pending"
                logger.info(
                    "Task %s failed (attempt %d/%d), next retry: %s",
                    task.task_id, db_task.retry_count, max_retries,
                    db_task.next_retry_at,
                )

            session.add(db_task)
            session.commit()


# ---------------------------------------------------------------------------
# Worker implementation
# ---------------------------------------------------------------------------

class WebhookOutboxWorker(BaseOutboxWorker):
    """Polls ``webhook_task`` and delivers via HTTP POST."""

    def __init__(self) -> None:
        super().__init__(
            name="outbox_worker",
            poll_interval=POLL_INTERVAL_SECONDS,
            max_retries=MAX_RETRIES,
        )

    async def _poll_batch(self) -> None:
        now = datetime.now(timezone.utc)

        with Session(engine) as session:
            tasks = session.exec(
                select(WebhookTask).where(
                    WebhookTask.status == "pending",
                ).limit(100)
            ).all()

            deliverable = []
            for t in tasks:
                if t.next_retry_at is None or t.next_retry_at <= now:
                    deliverable.append(t)

            # Look up webhook URLs from rules
            rule_url_map = {}
            if deliverable:
                rule_ids = list({t.rule_id for t in deliverable})
                rules = session.exec(
                    select(WebhookRule).where(
                        WebhookRule.rule_id.in_(rule_ids)  # type: ignore
                    )
                ).all()
                rule_url_map = {r.rule_id: r.webhook_url for r in rules}

        # Deliver outside the session (async HTTP)
        if deliverable:
            self.logger.info("Found %d deliverable task(s)", len(deliverable))
            for task in deliverable:
                url = rule_url_map.get(task.rule_id, "")
                if url:
                    await _deliver_task(task, url, self.max_retries)
                else:
                    self.logger.warning(
                        "No webhook URL for rule %s (task %s), marking failed",
                        task.rule_id, task.task_id,
                    )
                    with Session(engine) as session:
                        db_task = session.get(WebhookTask, task.task_id)
                        if db_task:
                            db_task.status = "failed"
                            db_task.last_error = "Webhook rule or URL not found."
                            session.add(db_task)
                            session.commit()


# ---------------------------------------------------------------------------
# Module-level singleton + compat API
# ---------------------------------------------------------------------------

_worker = WebhookOutboxWorker()


async def start_outbox_worker() -> None:
    """Launch the outbox polling loop as a background asyncio task."""
    await _worker.start()


async def stop_outbox_worker() -> None:
    """Signal the worker to stop and wait for it to finish."""
    await _worker.stop()
