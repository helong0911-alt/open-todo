"""
Project Member Management API for Open-Todo (OTD).

Provides endpoints to list, add, and remove project members (agents).
External systems use this registry (via MCP or REST) to discover which
agents belong to a project for task assignment.
"""
from typing import List, Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.models.models import User, Project, ProjectMember


router = APIRouter(prefix="/members", tags=["Members"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MemberListRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to list members for.")


class MemberAddRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to add member to.")
    agentId: str = Field(..., description="External agent identifier.")
    displayName: Optional[str] = Field(None, description="Human-readable display name.")
    description: Optional[str] = Field(None, description="Agent introduction or role description.")


class MemberRemoveRequest(BaseModel):
    memberId: str = Field(..., description="Member ID to remove.")


class MemberResponse(BaseModel):
    memberId: str
    projectId: str
    agentId: str
    displayName: Optional[str] = None
    description: Optional[str] = None
    createdAt: str


class MemberRemoveResponse(BaseModel):
    detail: str
    memberId: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_project_ownership(
    session: Session, project_id: str, user: User
) -> Project:
    """Verify that the project exists and belongs to the user."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return project


def _to_response(member: ProjectMember) -> MemberResponse:
    """Convert ORM model to response schema."""
    return MemberResponse(
        memberId=member.member_id,
        projectId=member.project_id,
        agentId=member.agent_id,
        displayName=member.display_name,
        description=member.description,
        createdAt=member.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/list",
    response_model=List[MemberResponse],
    summary="List project members",
    description="Returns all members (agents) registered in the specified project.",
)
def list_members(
    body: MemberListRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_ownership(session, body.projectId, current_user)

    members = session.exec(
        select(ProjectMember).where(ProjectMember.project_id == body.projectId)
    ).all()

    return [_to_response(m) for m in members]


@router.post(
    "/add",
    response_model=MemberResponse,
    summary="Add a member to a project",
    description=(
        "Registers an agent as a project member. "
        "The agentId must be unique within the project (409 on duplicate). "
        "displayName and description are optional."
    ),
)
def add_member(
    body: MemberAddRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_ownership(session, body.projectId, current_user)

    # Validate agentId is not empty
    if not body.agentId or not body.agentId.strip():
        raise HTTPException(
            status_code=422,
            detail="agentId must not be empty.",
        )

    # Check for duplicate agentId within the project
    existing = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == body.projectId,
            ProjectMember.agent_id == body.agentId,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{body.agentId}' already exists in this project.",
        )

    member = ProjectMember(
        project_id=body.projectId,
        agent_id=body.agentId,
        display_name=body.displayName,
        description=body.description,
    )
    session.add(member)
    session.commit()
    session.refresh(member)

    return _to_response(member)


@router.post(
    "/remove",
    response_model=MemberRemoveResponse,
    summary="Remove a member from a project",
    description="Removes an agent from the project member registry.",
)
def remove_member(
    body: MemberRemoveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    member = session.get(ProjectMember, body.memberId)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")

    # Verify project ownership
    project = session.get(Project, member.project_id)
    if project is None or project.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    session.delete(member)
    session.commit()

    return MemberRemoveResponse(
        detail="Member removed successfully.",
        memberId=body.memberId,
    )
