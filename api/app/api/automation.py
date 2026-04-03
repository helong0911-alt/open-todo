"""
Automation API: webhook log queries and manual retry.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.models.models import (
    User,
    Project,
    Todo,
    WebhookRule,
    WebhookTask,
)

router = APIRouter(prefix="/automation", tags=["Automation"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class WebhookLogsRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to query logs for.")
    todoId: Optional[str] = Field(
        None, description="Optional todo ID to filter logs by a specific task."
    )


class WebhookLogEntry(BaseModel):
    taskId: str
    ruleId: str
    todoId: str
    webhookUrl: str
    eventType: str
    payload: Dict[str, Any]
    status: str
    retryCount: int
    nextRetryAt: Optional[str] = None
    lastError: Optional[str] = None
    createdAt: str


class WebhookLogsResponse(BaseModel):
    total: int
    logs: List[WebhookLogEntry]


class WebhookRetryRequest(BaseModel):
    taskId: str = Field(
        ..., description="Outbox task ID to manually retry."
    )


class WebhookRetryResponse(BaseModel):
    detail: str
    taskId: str
    status: str
    retryCount: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_project_access(
    session: Session, project_id: str, user: User
) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return project


def _task_to_log(task: WebhookTask, url: str, event_type: str) -> WebhookLogEntry:
    return WebhookLogEntry(
        taskId=task.task_id,
        ruleId=task.rule_id,
        todoId=task.todo_id,
        webhookUrl=url,
        eventType=event_type,
        payload=task.payload,
        status=task.status,
        retryCount=task.retry_count,
        nextRetryAt=task.next_retry_at.isoformat() if task.next_retry_at else None,
        lastError=task.last_error,
        createdAt=task.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/logs",
    response_model=WebhookLogsResponse,
    summary="Query webhook delivery logs",
    description=(
        "Returns the delivery history (outbox tasks) for a project. "
        "Optionally filter by ``todoId`` to see logs for a specific task."
    ),
)
def webhook_logs(
    body: WebhookLogsRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_access(session, body.projectId, current_user)

    # Get all rules for the project -> build lookup
    rules = session.exec(
        select(WebhookRule).where(WebhookRule.project_id == body.projectId)
    ).all()
    rule_ids = [r.rule_id for r in rules]
    rule_map = {r.rule_id: r for r in rules}

    if not rule_ids:
        return WebhookLogsResponse(total=0, logs=[])

    stmt = select(WebhookTask).where(
        WebhookTask.rule_id.in_(rule_ids)  # type: ignore
    )
    if body.todoId:
        stmt = stmt.where(WebhookTask.todo_id == body.todoId)

    # Order by creation time descending
    stmt = stmt.order_by(WebhookTask.created_at.desc())  # type: ignore

    tasks = session.exec(stmt).all()

    logs = []
    for t in tasks:
        rule = rule_map.get(t.rule_id)
        url = rule.webhook_url if rule else "unknown"
        event_type = rule.event_type if rule else "unknown"
        logs.append(_task_to_log(t, url, event_type))

    return WebhookLogsResponse(total=len(logs), logs=logs)


@router.post(
    "/webhook/retry",
    response_model=WebhookRetryResponse,
    summary="Manually retry a failed webhook task",
    description=(
        "Resets a ``failed`` webhook task back to ``pending`` so the outbox "
        "worker will pick it up again.  The ``retryCount`` is preserved."
    ),
)
def webhook_retry(
    body: WebhookRetryRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    task = session.get(WebhookTask, body.taskId)
    if task is None:
        raise HTTPException(status_code=404, detail="Webhook task not found.")

    # Verify ownership through rule -> project -> user chain
    rule = session.get(WebhookRule, task.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Associated webhook rule not found.")

    project = session.get(Project, rule.project_id)
    if project is None or project.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    if task.status not in ("failed", "pending"):
        raise HTTPException(
            status_code=422,
            detail=f"Task status is '{task.status}'; only 'failed' or 'pending' tasks can be retried.",
        )

    # Reset to pending, clear next_retry_at so the worker picks it up
    task.status = "pending"
    task.next_retry_at = None
    task.last_error = None
    session.add(task)
    session.commit()
    session.refresh(task)

    return WebhookRetryResponse(
        detail="Task reset to pending for retry.",
        taskId=task.task_id,
        status=task.status,
        retryCount=task.retry_count,
    )
