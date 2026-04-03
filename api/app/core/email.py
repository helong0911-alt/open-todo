"""
Email service for Open-Todo (OTD).

Two-layer architecture:
- **Enqueue layer** (used by business code): inserts ``EmailTask`` records
  into the queue table within the caller's DB session/transaction.
- **SMTP layer** (used by the email worker): renders a Jinja2 template and
  delivers the message via ``aiosmtplib``.

All email operations are no-ops when ``MAIL_ENABLED`` is ``false``.
"""
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosmtplib
from jinja2 import Environment, FileSystemLoader
from sqlmodel import Session, select

from api.app.core.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_USE_TLS,
    MAIL_FROM_ADDRESS,
    MAIL_FROM_NAME,
    MAIL_ENABLED,
)
from api.app.models.models import EmailTask, NotificationRule

logger = logging.getLogger("otd.email")

# ---------------------------------------------------------------------------
# Template engine
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)

# ---------------------------------------------------------------------------
# Priority auto-assignment map
# ---------------------------------------------------------------------------

_EVENT_PRIORITY: Dict[str, str] = {
    "Verification": "high",
    "WebhookFailure": "high",
    "TaskCreate": "normal",
    "TaskUpdate": "normal",
    "TaskDelete": "normal",
}


# ---------------------------------------------------------------------------
# Enqueue layer (called inside business-code transactions)
# ---------------------------------------------------------------------------

def enqueue_email(
    session: Session,
    user_id: str,
    to_address: str,
    subject: str,
    template_name: str,
    template_context: Dict[str, Any],
    priority: str = "normal",
) -> EmailTask:
    """
    Insert an ``EmailTask`` into the email queue table.

    This function participates in the caller's transaction — call
    ``session.flush()`` afterwards if you need the ``task_id`` immediately,
    or let the caller ``session.commit()`` at the end.
    """
    task = EmailTask(
        user_id=user_id,
        to_address=to_address,
        subject=subject,
        template_name=template_name,
        template_context=template_context,
        priority=priority,
        status="pending",
    )
    session.add(task)
    return task


def check_and_enqueue(
    session: Session,
    user_id: str,
    to_address: str,
    event_type: str,
    subject: str,
    template_name: str,
    template_context: Dict[str, Any],
) -> Optional[EmailTask]:
    """
    Check whether the user has an enabled ``NotificationRule`` for
    *event_type*.  If yes, enqueue an email and return the task; otherwise
    return ``None``.

    Priority is determined automatically from ``_EVENT_PRIORITY``.
    """
    if not MAIL_ENABLED:
        return None

    rule = session.exec(
        select(NotificationRule).where(
            NotificationRule.user_id == user_id,
            NotificationRule.event_type == event_type,
            NotificationRule.enabled == True,  # noqa: E712
        )
    ).first()

    if rule is None:
        return None

    priority = _EVENT_PRIORITY.get(event_type, "normal")
    return enqueue_email(
        session=session,
        user_id=user_id,
        to_address=to_address,
        subject=subject,
        template_name=template_name,
        template_context=template_context,
        priority=priority,
    )


def enqueue_verification_email(
    session: Session,
    user_id: str,
    to_address: str,
    verification_url: str,
) -> EmailTask:
    """
    Enqueue a registration verification email.

    This is always enqueued (no rule check needed) because the user just
    registered and has no rules yet.
    """
    return enqueue_email(
        session=session,
        user_id=user_id,
        to_address=to_address,
        subject="Open-Todo - Verify your email",
        template_name="verification.html",
        template_context={
            "email": to_address,
            "verification_url": verification_url,
        },
        priority="high",
    )


def enqueue_task_notification(
    session: Session,
    user_id: str,
    to_address: str,
    event_type: str,
    project_name: str,
    todo_id: str,
    content_summary: str,
    changed_fields: List[str],
) -> Optional[EmailTask]:
    """
    Conditionally enqueue a task-change notification email.

    Returns ``None`` if the user has no matching enabled rule.
    """
    return check_and_enqueue(
        session=session,
        user_id=user_id,
        to_address=to_address,
        event_type=event_type,
        subject=f"Open-Todo - Task {event_type}: {project_name}",
        template_name="task_notification.html",
        template_context={
            "event_type": event_type,
            "project_name": project_name,
            "todo_id": todo_id,
            "content_summary": content_summary,
            "changed_fields": changed_fields,
        },
    )


def enqueue_webhook_failure_alert(
    session: Session,
    user_id: str,
    to_address: str,
    webhook_url: str,
    rule_id: str,
    task_id: str,
    retry_count: int,
    last_error: str,
) -> Optional[EmailTask]:
    """
    Conditionally enqueue a webhook-failure alert email.

    Returns ``None`` if the user has no matching enabled rule.
    """
    return check_and_enqueue(
        session=session,
        user_id=user_id,
        to_address=to_address,
        event_type="WebhookFailure",
        subject=f"Open-Todo - Webhook delivery failed: {webhook_url}",
        template_name="webhook_failure.html",
        template_context={
            "webhook_url": webhook_url,
            "rule_id": rule_id,
            "task_id": task_id,
            "retry_count": retry_count,
            "last_error": last_error,
        },
    )


# ---------------------------------------------------------------------------
# SMTP layer (called by email_worker only)
# ---------------------------------------------------------------------------

async def send_smtp(
    to_address: str,
    subject: str,
    template_name: str,
    template_context: Dict[str, Any],
) -> None:
    """
    Render a Jinja2 template and deliver the email via SMTP.

    Raises on any failure so the caller (email worker) can handle retries.
    """
    template = _jinja_env.get_template(template_name)
    html_body = template.render(**template_context)

    message = MIMEMultipart("alternative")
    message["From"] = f"{MAIL_FROM_NAME} <{MAIL_FROM_ADDRESS}>"
    message["To"] = to_address
    message["Subject"] = subject
    message.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        message,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USERNAME or None,
        password=SMTP_PASSWORD or None,
        use_tls=SMTP_USE_TLS,
    )

    logger.info("Email delivered: %s -> %s", subject, to_address)
