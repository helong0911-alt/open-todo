"""
Project API: list and create projects.
"""
from typing import List, Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.models.models import User, Project

router = APIRouter(prefix="/projects", tags=["Projects"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    projectName: str = Field(..., description="Human-readable project name.")
    projectDescription: Optional[str] = Field(
        None, description="Optional project description."
    )


class ProjectResponse(BaseModel):
    projectId: str
    userId: str
    projectName: str
    projectDescription: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[ProjectResponse],
    summary="List all projects",
    description="Returns all projects owned by the authenticated user.",
)
def list_projects(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    projects = session.exec(
        select(Project).where(Project.user_id == current_user.user_id)
    ).all()
    return [
        ProjectResponse(
            projectId=p.project_id,
            userId=p.user_id,
            projectName=p.project_name,
            projectDescription=p.project_description,
        )
        for p in projects
    ]


@router.post(
    "/create",
    response_model=ProjectResponse,
    summary="Create a new project",
    description="Creates a new project for the authenticated user.",
)
def create_project(
    body: CreateProjectRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        user_id=current_user.user_id,
        project_name=body.projectName,
        project_description=body.projectDescription,
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    return ProjectResponse(
        projectId=project.project_id,
        userId=project.user_id,
        projectName=project.project_name,
        projectDescription=project.project_description,
    )
