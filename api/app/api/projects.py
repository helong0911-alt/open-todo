"""
Project API: list, create, and update projects.
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
    projectDirectory: Optional[str] = Field(
        None, description="Local filesystem directory path for the project."
    )
    gitUrl: Optional[str] = Field(
        None, description="Git repository URL for the project."
    )


class UpdateProjectRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to update.")
    projectName: Optional[str] = Field(
        None, description="Updated project name."
    )
    projectDescription: Optional[str] = Field(
        None, description="Updated project description."
    )
    projectDirectory: Optional[str] = Field(
        None, description="Updated local filesystem directory path."
    )
    gitUrl: Optional[str] = Field(
        None, description="Updated Git repository URL."
    )


class ProjectResponse(BaseModel):
    projectId: str
    userId: str
    projectName: str
    projectDescription: Optional[str] = None
    projectDirectory: Optional[str] = None
    gitUrl: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_to_response(p: Project) -> ProjectResponse:
    """Convert a Project ORM instance to a ProjectResponse."""
    return ProjectResponse(
        projectId=p.project_id,
        userId=p.user_id,
        projectName=p.project_name,
        projectDescription=p.project_description,
        projectDirectory=p.project_directory,
        gitUrl=p.git_url,
    )


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
    return [_project_to_response(p) for p in projects]


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
        project_directory=body.projectDirectory,
        git_url=body.gitUrl,
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    return _project_to_response(project)


@router.post(
    "/update",
    response_model=ProjectResponse,
    summary="Update a project",
    description="Update project metadata (name, description, directory, git URL).",
)
def update_project(
    body: UpdateProjectRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    project = session.get(Project, body.projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    if body.projectName is not None:
        project.project_name = body.projectName
    if body.projectDescription is not None:
        project.project_description = body.projectDescription
    if body.projectDirectory is not None:
        project.project_directory = body.projectDirectory
    if body.gitUrl is not None:
        project.git_url = body.gitUrl

    session.add(project)
    session.commit()
    session.refresh(project)

    return _project_to_response(project)
