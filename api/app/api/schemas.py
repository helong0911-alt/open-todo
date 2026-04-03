"""
Schema API: get and update project dynamic field definitions.
"""
from typing import Any, List, Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.models.models import User, Project, ProjectSchema

router = APIRouter(prefix="/projects/schema", tags=["Schema"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SchemaGetRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to fetch schema for.")


class FieldDefinition(BaseModel):
    fieldName: str = Field(..., description="Field name (camelCase).")
    fieldType: str = Field(
        ...,
        description="Field type: text, number, date, enum, link, or assignee.",
    )
    fieldDescription: Optional[str] = Field(
        None, description="Human-readable field description."
    )
    enumValues: Optional[List[str]] = Field(
        None, description="Allowed values (only for enum type)."
    )


class SchemaUpdateRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to update schema for.")
    fieldsDefinition: List[FieldDefinition] = Field(
        ..., description="Array of field descriptors."
    )


class SchemaResponse(BaseModel):
    schemaId: str
    projectId: str
    fieldsDefinition: Any
    schemaVersion: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_project_ownership(
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
    "/get",
    response_model=SchemaResponse,
    summary="Get project schema",
    description=(
        "Returns the dynamic field definitions for the specified project. "
        "If no schema has been set yet, returns an empty definition."
    ),
)
def get_schema(
    body: SchemaGetRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_ownership(session, body.projectId, current_user)

    schema = session.exec(
        select(ProjectSchema).where(
            ProjectSchema.project_id == body.projectId
        )
    ).first()

    if schema is None:
        # Auto-create empty schema
        schema = ProjectSchema(
            project_id=body.projectId,
            fields_definition=[],
        )
        session.add(schema)
        session.commit()
        session.refresh(schema)

    return SchemaResponse(
        schemaId=schema.schema_id,
        projectId=schema.project_id,
        fieldsDefinition=schema.fields_definition,
        schemaVersion=schema.schema_version,
    )


@router.post(
    "/update",
    response_model=SchemaResponse,
    summary="Update project schema",
    description=(
        "Replaces the dynamic field definitions for the specified project. "
        "Supported field types: text, number, date, enum, link, assignee."
    ),
)
def update_schema(
    body: SchemaUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_ownership(session, body.projectId, current_user)

    # Validate field types
    valid_types = {"text", "number", "date", "enum", "link", "assignee"}
    for fd in body.fieldsDefinition:
        if fd.fieldType not in valid_types:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid fieldType '{fd.fieldType}'. Must be one of: {', '.join(sorted(valid_types))}.",
            )
        if fd.fieldType == "enum" and not fd.enumValues:
            raise HTTPException(
                status_code=422,
                detail=f"Field '{fd.fieldName}' of type 'enum' must provide enumValues.",
            )

    schema = session.exec(
        select(ProjectSchema).where(
            ProjectSchema.project_id == body.projectId
        )
    ).first()

    fields_data = [fd.model_dump() for fd in body.fieldsDefinition]

    if schema is None:
        schema = ProjectSchema(
            project_id=body.projectId,
            fields_definition=fields_data,
            schema_version=1,
        )
        session.add(schema)
    else:
        schema.fields_definition = fields_data
        schema.schema_version = (schema.schema_version or 0) + 1

    session.commit()
    session.refresh(schema)

    return SchemaResponse(
        schemaId=schema.schema_id,
        projectId=schema.project_id,
        fieldsDefinition=schema.fields_definition,
        schemaVersion=schema.schema_version,
    )
