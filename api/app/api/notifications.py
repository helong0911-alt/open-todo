"""
Notification Rules API: manage per-user email notification rules.

Supported event types:
- ``Verification`` — email verification (always sent, no rule needed).
- ``TaskCreate`` — todo created.
- ``TaskUpdate`` — todo updated.
- ``TaskDelete`` — todo deleted.
- ``WebhookFailure`` — webhook delivery permanently failed.

Users opt-in by creating rules; by default no rules exist (no notifications).
"""
from typing import List

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.models.models import User, NotificationRule

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_EVENT_TYPES = {
    "TaskCreate",
    "TaskUpdate",
    "TaskDelete",
    "WebhookFailure",
}
"""Event types that users can create rules for.
``Verification`` is excluded because verification emails are always sent."""


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RuleCreateRequest(BaseModel):
    eventType: str = Field(
        ...,
        description="Event type: TaskCreate, TaskUpdate, TaskDelete, or WebhookFailure.",
    )


class RuleResponse(BaseModel):
    ruleId: str = Field(..., description="Unique rule identifier.")
    userId: str = Field(..., description="Owner user ID.")
    eventType: str = Field(..., description="Event type this rule monitors.")
    enabled: bool = Field(..., description="Whether this rule is active.")
    createdAt: str = Field(..., description="Rule creation timestamp.")


class RuleDeleteRequest(BaseModel):
    ruleId: str = Field(..., description="Rule ID to delete.")


class RuleDeleteResponse(BaseModel):
    detail: str
    ruleId: str


class RuleUpdateRequest(BaseModel):
    ruleId: str = Field(..., description="Rule ID to update.")
    enabled: bool = Field(..., description="New enabled state.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(rule: NotificationRule) -> RuleResponse:
    return RuleResponse(
        ruleId=rule.rule_id,
        userId=rule.user_id,
        eventType=rule.event_type,
        enabled=rule.enabled,
        createdAt=rule.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/rules/create",
    response_model=RuleResponse,
    summary="Create a notification rule",
    description=(
        "Creates a new notification rule for the authenticated user. "
        "The rule defines which event type triggers an email notification. "
        "Duplicate event types for the same user are rejected with 409."
    ),
)
def create_rule(
    body: RuleCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if body.eventType not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid event type: {body.eventType}. "
                f"Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}."
            ),
        )

    # Check duplicate
    existing = session.exec(
        select(NotificationRule).where(
            NotificationRule.user_id == current_user.user_id,
            NotificationRule.event_type == body.eventType,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Notification rule for event type '{body.eventType}' already exists.",
        )

    rule = NotificationRule(
        user_id=current_user.user_id,
        event_type=body.eventType,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)

    return _to_response(rule)


@router.post(
    "/rules/list",
    response_model=List[RuleResponse],
    summary="List notification rules",
    description="Returns all notification rules for the authenticated user.",
)
def list_rules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rules = session.exec(
        select(NotificationRule).where(
            NotificationRule.user_id == current_user.user_id,
        )
    ).all()

    return [_to_response(r) for r in rules]


@router.post(
    "/rules/update",
    response_model=RuleResponse,
    summary="Update a notification rule",
    description="Enable or disable an existing notification rule.",
)
def update_rule(
    body: RuleUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rule = session.get(NotificationRule, body.ruleId)
    if rule is None:
        raise HTTPException(status_code=404, detail="Notification rule not found.")
    if rule.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    rule.enabled = body.enabled
    session.add(rule)
    session.commit()
    session.refresh(rule)

    return _to_response(rule)


@router.post(
    "/rules/delete",
    response_model=RuleDeleteResponse,
    summary="Delete a notification rule",
    description="Permanently removes a notification rule.",
)
def delete_rule(
    body: RuleDeleteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rule = session.get(NotificationRule, body.ruleId)
    if rule is None:
        raise HTTPException(status_code=404, detail="Notification rule not found.")
    if rule.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    session.delete(rule)
    session.commit()

    return RuleDeleteResponse(
        detail="Notification rule deleted.",
        ruleId=body.ruleId,
    )
