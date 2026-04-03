"""
Webhook management API: create and list webhook rules.
"""
from typing import List, Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.models.models import User, Project, WebhookRule, WebhookTask

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class WebhookRuleCreateRequest(BaseModel):
    projectId: str = Field(..., description="Project to attach the rule to.")
    eventType: str = Field(
        ..., description="Event type to listen for: Create, Update, or Delete."
    )
    targetField: str = Field(
        default="*",
        description="Field name to monitor, or '*' for any field change.",
    )
    webhookUrl: str = Field(
        ..., description="URL to POST the webhook payload to."
    )


class WebhookRuleResponse(BaseModel):
    ruleId: str
    projectId: str
    eventType: str
    targetField: str
    webhookUrl: str


class WebhookRuleListRequest(BaseModel):
    projectId: str = Field(
        ..., description="Project ID to list webhook rules for."
    )


class WebhookTaskResponse(BaseModel):
    taskId: str
    ruleId: str
    todoId: str
    payload: dict
    status: str
    retryCount: int
    nextRetryAt: Optional[str] = None
    lastError: Optional[str] = None
    createdAt: str


class WebhookTaskListRequest(BaseModel):
    projectId: str = Field(
        ..., description="Project ID to list outbox tasks for."
    )
    status: Optional[str] = Field(
        None, description="Filter by status: pending, success, or failed."
    )


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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/create",
    response_model=WebhookRuleResponse,
    summary="Create a webhook rule",
    description=(
        "Creates a new webhook rule for the specified project. "
        "Use `targetField: '*'` to monitor all field changes. "
        "Supported event types: Create, Update, Delete."
    ),
)
def create_webhook_rule(
    body: WebhookRuleCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_access(session, body.projectId, current_user)

    valid_events = {"Create", "Update", "Delete"}
    if body.eventType not in valid_events:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid eventType '{body.eventType}'. Must be one of: {', '.join(sorted(valid_events))}.",
        )

    rule = WebhookRule(
        project_id=body.projectId,
        event_type=body.eventType,
        target_field=body.targetField,
        webhook_url=body.webhookUrl,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)

    return WebhookRuleResponse(
        ruleId=rule.rule_id,
        projectId=rule.project_id,
        eventType=rule.event_type,
        targetField=rule.target_field,
        webhookUrl=rule.webhook_url,
    )


@router.post(
    "/list",
    response_model=List[WebhookRuleResponse],
    summary="List webhook rules",
    description="Returns all webhook rules for the specified project.",
)
def list_webhook_rules(
    body: WebhookRuleListRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_access(session, body.projectId, current_user)

    rules = session.exec(
        select(WebhookRule).where(WebhookRule.project_id == body.projectId)
    ).all()

    return [
        WebhookRuleResponse(
            ruleId=r.rule_id,
            projectId=r.project_id,
            eventType=r.event_type,
            targetField=r.target_field,
            webhookUrl=r.webhook_url,
        )
        for r in rules
    ]


@router.post(
    "/tasks",
    response_model=List[WebhookTaskResponse],
    summary="List outbox tasks",
    description=(
        "Returns webhook outbox tasks for the specified project. "
        "Optionally filter by status (pending, success, failed)."
    ),
)
def list_webhook_tasks(
    body: WebhookTaskListRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_access(session, body.projectId, current_user)

    # Get rule IDs for this project
    rules = session.exec(
        select(WebhookRule).where(WebhookRule.project_id == body.projectId)
    ).all()
    rule_ids = [r.rule_id for r in rules]

    if not rule_ids:
        return []

    stmt = select(WebhookTask).where(WebhookTask.rule_id.in_(rule_ids))  # type: ignore
    if body.status:
        stmt = stmt.where(WebhookTask.status == body.status)

    tasks = session.exec(stmt).all()

    return [
        WebhookTaskResponse(
            taskId=t.task_id,
            ruleId=t.rule_id,
            todoId=t.todo_id,
            payload=t.payload,
            status=t.status,
            retryCount=t.retry_count,
            nextRetryAt=t.next_retry_at.isoformat() if t.next_retry_at else None,
            lastError=t.last_error,
            createdAt=t.created_at.isoformat(),
        )
        for t in tasks
    ]
