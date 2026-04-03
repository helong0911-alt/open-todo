"""
Todo API with Transactional Outbox pattern.

Step 2 enhancements:
- Dynamic schema validation on create/update via ``validate_content``.
- Deep-diff snapshot comparison with ``before`` / ``after`` payload.
- Optimistic concurrency control: 409 Conflict on version mismatch.
- Recursive cascade delete with per-descendant webhook outbox entries.
- Wildcard ``*`` + specific-field webhook rule matching.
- Email notification enqueue on task create/update/delete.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.core.validator import validate_content
from api.app.core.email import enqueue_task_notification
from api.app.core.healer import heal_content, get_schema_for_project
from api.app.models.models import (
    User,
    Project,
    Todo,
    WebhookRule,
    WebhookTask,
    _utcnow,
)

router = APIRouter(prefix="/todos", tags=["Todos"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class TodoListRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to list todos for.")


class TodoCreateRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to create todo in.")
    parentId: Optional[str] = Field(
        None, description="Parent todo ID for nesting (null = root)."
    )
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic business data conforming to project schema.",
    )


class TodoUpdateRequest(BaseModel):
    todoId: str = Field(..., description="Todo ID to update.")
    content: Optional[Dict[str, Any]] = Field(
        None, description="Updated dynamic business data (null = no content change)."
    )
    isCompleted: Optional[bool] = Field(
        None, description="Set completion status."
    )
    version: Optional[int] = Field(
        None,
        description=(
            "Expected current version for optimistic concurrency control. "
            "If provided and mismatches the DB version, returns 409 Conflict."
        ),
    )


class TodoMoveRequest(BaseModel):
    todoId: str = Field(..., description="Todo ID to reparent.")
    newParentId: Optional[str] = Field(
        None,
        description="New parent todo ID (null = move to root).",
    )
    version: Optional[int] = Field(
        None,
        description=(
            "Expected current version for optimistic concurrency control. "
            "If provided and mismatches the DB version, returns 409 Conflict."
        ),
    )


class TodoDeleteRequest(BaseModel):
    todoId: str = Field(..., description="Todo ID to delete (cascade all descendants).")


class TodoResponse(BaseModel):
    todoId: str
    projectId: str
    parentId: Optional[str] = None
    content: Any
    isCompleted: bool
    updatedAt: str
    version: int
    schemaVersion: int


class TodoMoveResponse(BaseModel):
    detail: str
    todoId: str
    oldParentId: Optional[str] = None
    newParentId: Optional[str] = None
    version: int


class TodoDeleteResponse(BaseModel):
    detail: str
    todoId: str
    deletedCount: int = Field(
        ..., description="Total number of todos deleted (including descendants)."
    )


class BulkTodoItem(BaseModel):
    parentId: Optional[str] = Field(
        None, description="Parent todo ID (null = root)."
    )
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic business data conforming to project schema.",
    )


class TodoBulkCreateRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to create todos in.")
    items: List[BulkTodoItem] = Field(
        ..., description="Array of todos to create."
    )


class TodoBulkCreateResponse(BaseModel):
    detail: str
    projectId: str
    createdCount: int
    todos: List[TodoResponse]


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


def _verify_todo_ownership(
    session: Session, todo_id: str, user: User
) -> Todo:
    todo = session.get(Todo, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found.")
    project = session.get(Project, todo.project_id)
    if project is None or project.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return todo


def _to_response(todo: Todo, healed_content: Optional[Dict[str, Any]] = None) -> TodoResponse:
    return TodoResponse(
        todoId=todo.todo_id,
        projectId=todo.project_id,
        parentId=todo.parent_id,
        content=healed_content if healed_content is not None else todo.content,
        isCompleted=todo.is_completed,
        updatedAt=todo.updated_at.isoformat(),
        version=todo.version,
        schemaVersion=todo.schema_version or 0,
    )


# ---------------------------------------------------------------------------
# Deep diff engine
# ---------------------------------------------------------------------------

def _deep_diff(
    old_content: Dict[str, Any],
    new_content: Dict[str, Any],
    old_completed: bool,
    new_completed: Optional[bool],
) -> Set[str]:
    """
    Return the set of field names whose values actually changed.
    Performs recursive equality comparison for nested dicts/lists.
    """
    changed: Set[str] = set()

    all_keys = set(old_content.keys()) | set(new_content.keys())
    for key in all_keys:
        old_val = old_content.get(key)
        new_val = new_content.get(key)
        if old_val != new_val:
            changed.add(key)

    if new_completed is not None and new_completed != old_completed:
        changed.add("isCompleted")

    return changed


# ---------------------------------------------------------------------------
# Webhook rule matching & outbox enqueue
# ---------------------------------------------------------------------------

def _match_rules(
    session: Session,
    project_id: str,
    event_type: str,
    changed_fields: Set[str],
) -> List[WebhookRule]:
    """
    Match WebhookRule entries.  ``targetField='*'`` matches if *any* field
    changed.  Specific ``targetField`` matches only when that field changed.
    """
    rules = session.exec(
        select(WebhookRule).where(
            WebhookRule.project_id == project_id,
            WebhookRule.event_type == event_type,
        )
    ).all()

    matched: List[WebhookRule] = []
    for rule in rules:
        if rule.target_field == "*":
            # Wildcard: trigger if there is at least one changed field
            if changed_fields:
                matched.append(rule)
        elif rule.target_field in changed_fields:
            matched.append(rule)
    return matched


def _enqueue_webhooks(
    session: Session,
    rules: List[WebhookRule],
    todo: Todo,
    event_type: str,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    changed_fields: Optional[Set[str]] = None,
):
    """
    Insert WebhookTask outbox records.  Payload always contains ``before``
    and ``after`` snapshots plus the list of ``changedFields``.
    """
    for rule in rules:
        payload: Dict[str, Any] = {
            "eventType": event_type,
            "todoId": todo.todo_id,
            "projectId": todo.project_id,
            "webhookUrl": rule.webhook_url,
            "ruleId": rule.rule_id,
            "changedFields": sorted(changed_fields) if changed_fields else [],
            "before": before,
            "after": after,
        }

        task = WebhookTask(
            rule_id=rule.rule_id,
            todo_id=todo.todo_id,
            payload=payload,
            status="pending",
        )
        session.add(task)


def _snapshot(todo: Todo) -> Dict[str, Any]:
    """Capture a serialisable snapshot of a todo's mutable state."""
    return {
        "content": dict(todo.content) if isinstance(todo.content, dict) else todo.content,
        "isCompleted": todo.is_completed,
        "parentId": todo.parent_id,
        "version": todo.version,
    }


# ---------------------------------------------------------------------------
# Recursive descendant collection (for cascade delete)
# ---------------------------------------------------------------------------

def _collect_descendants(session: Session, todo_id: str) -> List[Todo]:
    """BFS collection of all descendants of a todo (exclusive of self)."""
    descendants: List[Todo] = []
    queue = [todo_id]
    while queue:
        current_id = queue.pop(0)
        children = session.exec(
            select(Todo).where(Todo.parent_id == current_id)
        ).all()
        for child in children:
            descendants.append(child)
            queue.append(child.todo_id)
    return descendants


def _is_descendant(session: Session, ancestor_id: str, target_id: str) -> bool:
    """Check if target_id is a descendant of ancestor_id (BFS)."""
    queue = [ancestor_id]
    while queue:
        current_id = queue.pop(0)
        children = session.exec(
            select(Todo).where(Todo.parent_id == current_id)
        ).all()
        for child in children:
            if child.todo_id == target_id:
                return True
            queue.append(child.todo_id)
    return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/list",
    response_model=List[TodoResponse],
    summary="List todos for a project",
    description="Returns all todos (flat list) for the specified project.",
)
def list_todos(
    body: TodoListRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_access(session, body.projectId, current_user)

    todos = session.exec(
        select(Todo).where(Todo.project_id == body.projectId)
    ).all()

    # --- JIT healing (in-memory only, no write-back) ---
    fields_def, current_sv = get_schema_for_project(session, body.projectId)

    results: List[TodoResponse] = []
    for t in todos:
        if fields_def and (t.schema_version or 0) < current_sv:
            raw = dict(t.content) if isinstance(t.content, dict) else {}
            healed, _ = heal_content(raw, fields_def)
            results.append(_to_response(t, healed_content=healed))
        else:
            results.append(_to_response(t))
    return results


@router.post(
    "/create",
    response_model=TodoResponse,
    summary="Create a new todo",
    description=(
        "Creates a new todo in the specified project. "
        "Content is validated against the project schema. "
        "Optionally set ``parentId`` for tree nesting. "
        "Atomically inserts matching webhook outbox records."
    ),
)
def create_todo(
    body: TodoCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_access(session, body.projectId, current_user)

    # --- Schema validation ---
    validate_content(session, body.projectId, body.content)

    # Validate parent
    if body.parentId is not None:
        parent = session.get(Todo, body.parentId)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent todo not found.")
        if parent.project_id != body.projectId:
            raise HTTPException(
                status_code=422,
                detail="Parent todo does not belong to the specified project.",
            )

    # --- Transactional Outbox ---
    _, current_sv = get_schema_for_project(session, body.projectId)
    todo = Todo(
        project_id=body.projectId,
        parent_id=body.parentId,
        content=body.content,
        schema_version=current_sv,
    )
    session.add(todo)
    session.flush()

    after = _snapshot(todo)
    changed_fields = set(body.content.keys()) | {"isCompleted"}
    rules = _match_rules(session, body.projectId, "Create", changed_fields)
    _enqueue_webhooks(
        session, rules, todo, "Create",
        before=None, after=after, changed_fields=changed_fields,
    )

    # --- Email notification ---
    project = session.get(Project, body.projectId)
    project_name = project.project_name if project else body.projectId
    content_str = json.dumps(body.content, ensure_ascii=False, default=str)[:200]
    enqueue_task_notification(
        session=session,
        user_id=current_user.user_id,
        to_address=current_user.email,
        event_type="TaskCreate",
        project_name=project_name,
        todo_id=todo.todo_id,
        content_summary=content_str,
        changed_fields=sorted(changed_fields),
    )

    session.commit()
    session.refresh(todo)
    return _to_response(todo)


@router.post(
    "/update",
    response_model=TodoResponse,
    summary="Update a todo",
    description=(
        "Updates the content and/or completion status of an existing todo. "
        "Content is validated against the project schema. "
        "Performs deep-diff snapshot comparison; webhook payloads include "
        "full ``before`` and ``after`` snapshots plus ``changedFields``. "
        "Supply ``version`` for optimistic concurrency control (409 on mismatch). "
        "Atomically inserts matching webhook outbox records."
    ),
)
def update_todo(
    body: TodoUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    todo = _verify_todo_ownership(session, body.todoId, current_user)

    # --- Optimistic concurrency control ---
    if body.version is not None and body.version != todo.version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Version conflict: expected version {body.version}, "
                f"but current version is {todo.version}. "
                f"Re-fetch the todo and retry."
            ),
        )

    # --- Schema validation (only when content is provided) ---
    if body.content is not None:
        validate_content(session, todo.project_id, body.content)

    # --- JIT healing: fill missing fields before applying user changes ---
    fields_def, current_sv = get_schema_for_project(session, todo.project_id)
    old_content = dict(todo.content) if isinstance(todo.content, dict) else {}

    if fields_def and (todo.schema_version or 0) < current_sv:
        old_content, _ = heal_content(old_content, fields_def)

    # --- Snapshot BEFORE mutation ---
    before = _snapshot(todo)

    old_content_for_diff = old_content
    new_content = body.content if body.content is not None else old_content_for_diff
    changed_fields = _deep_diff(
        old_content_for_diff, new_content, todo.is_completed, body.isCompleted
    )

    # Also treat healing itself as a change when schema_version is behind
    healing_needed = fields_def and (todo.schema_version or 0) < current_sv

    if not changed_fields and not healing_needed:
        return _to_response(todo)

    # --- Apply mutation ---
    if body.content is not None:
        # Merge user-provided content on top of healed base
        merged = dict(old_content)
        merged.update(body.content)
        todo.content = merged
    elif healing_needed:
        # No user content change, but healing fills missing fields
        todo.content = old_content
    if body.isCompleted is not None:
        todo.is_completed = body.isCompleted
    todo.updated_at = _utcnow()
    todo.version += 1

    # --- Write-back schema_version ---
    if current_sv > 0:
        todo.schema_version = current_sv

    session.add(todo)
    session.flush()

    after = _snapshot(todo)

    # --- Webhook outbox ---
    rules = _match_rules(session, todo.project_id, "Update", changed_fields)
    _enqueue_webhooks(
        session, rules, todo, "Update",
        before=before, after=after, changed_fields=changed_fields,
    )

    # --- Email notification ---
    project = session.get(Project, todo.project_id)
    project_name = project.project_name if project else todo.project_id
    content_str = json.dumps(
        body.content if body.content is not None else old_content,
        ensure_ascii=False, default=str,
    )[:200]
    enqueue_task_notification(
        session=session,
        user_id=current_user.user_id,
        to_address=current_user.email,
        event_type="TaskUpdate",
        project_name=project_name,
        todo_id=todo.todo_id,
        content_summary=content_str,
        changed_fields=sorted(changed_fields),
    )

    session.commit()
    session.refresh(todo)
    return _to_response(todo)


@router.post(
    "/move",
    response_model=TodoMoveResponse,
    summary="Move (reparent) a todo",
    description=(
        "Moves a todo to a new parent within the same project. "
        "Set ``newParentId`` to null to move to root level. "
        "Validates that the move does not create a circular reference "
        "(newParentId must not be a descendant of the todo). "
        "Supply ``version`` for optimistic concurrency control (409 on mismatch). "
        "Atomically inserts matching webhook outbox records."
    ),
)
def move_todo(
    body: TodoMoveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    todo = _verify_todo_ownership(session, body.todoId, current_user)

    # --- Optimistic concurrency control ---
    if body.version is not None and body.version != todo.version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Version conflict: expected version {body.version}, "
                f"but current version is {todo.version}. "
                f"Re-fetch the todo and retry."
            ),
        )

    # --- Validate new parent ---
    if body.newParentId is not None:
        if body.newParentId == body.todoId:
            raise HTTPException(
                status_code=422,
                detail="A todo cannot be its own parent.",
            )

        new_parent = session.get(Todo, body.newParentId)
        if new_parent is None:
            raise HTTPException(status_code=404, detail="New parent todo not found.")
        if new_parent.project_id != todo.project_id:
            raise HTTPException(
                status_code=422,
                detail="New parent todo does not belong to the same project.",
            )

        # Circular reference check: newParentId must not be a descendant
        if _is_descendant(session, body.todoId, body.newParentId):
            raise HTTPException(
                status_code=422,
                detail="Circular reference: new parent is a descendant of this todo.",
            )

    # No-op check
    old_parent_id = todo.parent_id
    if old_parent_id == body.newParentId:
        return TodoMoveResponse(
            detail="Todo is already under the specified parent.",
            todoId=todo.todo_id,
            oldParentId=old_parent_id,
            newParentId=body.newParentId,
            version=todo.version,
        )

    # --- Snapshot BEFORE mutation ---
    before = _snapshot(todo)

    # --- Apply mutation ---
    todo.parent_id = body.newParentId
    todo.updated_at = _utcnow()
    todo.version += 1

    session.add(todo)
    session.flush()

    after = _snapshot(todo)
    changed_fields = {"parentId"}

    # --- Webhook outbox ---
    rules = _match_rules(session, todo.project_id, "Update", changed_fields)
    _enqueue_webhooks(
        session, rules, todo, "Update",
        before=before, after=after, changed_fields=changed_fields,
    )

    # --- Email notification ---
    project = session.get(Project, todo.project_id)
    project_name = project.project_name if project else todo.project_id
    enqueue_task_notification(
        session=session,
        user_id=current_user.user_id,
        to_address=current_user.email,
        event_type="TaskUpdate",
        project_name=project_name,
        todo_id=todo.todo_id,
        content_summary=f"Moved from parent {old_parent_id} to {body.newParentId}",
        changed_fields=sorted(changed_fields),
    )

    session.commit()
    session.refresh(todo)

    return TodoMoveResponse(
        detail="Todo moved successfully.",
        todoId=todo.todo_id,
        oldParentId=old_parent_id,
        newParentId=todo.parent_id,
        version=todo.version,
    )


@router.post(
    "/delete",
    response_model=TodoDeleteResponse,
    summary="Delete a todo (recursive cascade)",
    description=(
        "Deletes a todo and **all** its descendants recursively. "
        "For each deleted todo, matching webhook outbox records are inserted "
        "atomically within the same transaction."
    ),
)
def delete_todo(
    body: TodoDeleteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    todo = _verify_todo_ownership(session, body.todoId, current_user)

    # --- Collect all descendants (BFS) ---
    descendants = _collect_descendants(session, todo.todo_id)
    all_todos = descendants + [todo]  # process children first, root last

    # --- Transactional Outbox: enqueue webhooks for every node ---
    for t in all_todos:
        before = _snapshot(t)
        all_fields = set()
        if isinstance(t.content, dict):
            all_fields = set(t.content.keys())
        all_fields.add("isCompleted")

        rules = _match_rules(session, t.project_id, "Delete", all_fields)
        _enqueue_webhooks(
            session, rules, t, "Delete",
            before=before, after=None, changed_fields=all_fields,
        )

    # --- Delete leaves-first to respect FK constraints ---
    for t in reversed(all_todos):
        session.delete(t)

    # --- Email notification (one email for the root delete) ---
    project = session.get(Project, todo.project_id)
    project_name = project.project_name if project else todo.project_id
    content_str = json.dumps(
        todo.content if isinstance(todo.content, dict) else {},
        ensure_ascii=False, default=str,
    )[:200]
    enqueue_task_notification(
        session=session,
        user_id=current_user.user_id,
        to_address=current_user.email,
        event_type="TaskDelete",
        project_name=project_name,
        todo_id=todo.todo_id,
        content_summary=content_str,
        changed_fields=[],
    )

    session.commit()

    return TodoDeleteResponse(
        detail="Todo and all descendants deleted.",
        todoId=body.todoId,
        deletedCount=len(all_todos),
    )


@router.post(
    "/bulk-create",
    response_model=TodoBulkCreateResponse,
    summary="Bulk-create todos",
    description=(
        "Creates multiple todos in a single transaction within the same project. "
        "Useful for batch WBS decomposition. Each item can specify its own "
        "``parentId`` and ``content``. All content is validated against the "
        "project schema. Webhook outbox records are inserted atomically."
    ),
)
def bulk_create_todos(
    body: TodoBulkCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _verify_project_access(session, body.projectId, current_user)

    if not body.items:
        raise HTTPException(
            status_code=422, detail="Items array must not be empty."
        )

    project = session.get(Project, body.projectId)
    project_name = project.project_name if project else body.projectId

    _, current_sv = get_schema_for_project(session, body.projectId)
    created_todos: List[Todo] = []

    for idx, item in enumerate(body.items):
        # --- Schema validation ---
        validate_content(session, body.projectId, item.content)

        # --- Validate parent ---
        if item.parentId is not None:
            parent = session.get(Todo, item.parentId)
            if parent is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Parent todo not found (item index {idx}).",
                )
            if parent.project_id != body.projectId:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Parent todo does not belong to the specified "
                        f"project (item index {idx})."
                    ),
                )

        todo = Todo(
            project_id=body.projectId,
            parent_id=item.parentId,
            content=item.content,
            schema_version=current_sv,
        )
        session.add(todo)
        session.flush()

        # --- Webhook outbox ---
        after = _snapshot(todo)
        changed_fields = set(item.content.keys()) | {"isCompleted"}
        rules = _match_rules(session, body.projectId, "Create", changed_fields)
        _enqueue_webhooks(
            session, rules, todo, "Create",
            before=None, after=after, changed_fields=changed_fields,
        )

        created_todos.append(todo)

    # --- Single email notification for the whole batch ---
    content_str = f"Bulk created {len(created_todos)} todo(s)."
    enqueue_task_notification(
        session=session,
        user_id=current_user.user_id,
        to_address=current_user.email,
        event_type="TaskCreate",
        project_name=project_name,
        todo_id=created_todos[0].todo_id if created_todos else "",
        content_summary=content_str,
        changed_fields=["bulk-create"],
    )

    session.commit()
    for t in created_todos:
        session.refresh(t)

    return TodoBulkCreateResponse(
        detail=f"Created {len(created_todos)} todo(s).",
        projectId=body.projectId,
        createdCount=len(created_todos),
        todos=[_to_response(t) for t in created_todos],
    )
