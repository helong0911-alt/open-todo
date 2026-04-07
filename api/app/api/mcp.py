"""
MCP (Model Context Protocol) tool definitions for Open-Todo.

Implements the MCP Streamable HTTP transport (2025-03-26 spec) alongside
legacy REST endpoints for backwards compatibility.

Standard MCP endpoints (JSON-RPC over HTTP):
  POST /mcp   — accepts JSON-RPC messages (initialize, tools/list, tools/call)
  GET  /mcp   — returns 405 (no server-initiated SSE streams)

Legacy endpoints (kept for backwards compatibility):
  GET  /mcp/tools      — tool discovery
  POST /mcp/tools/call — tool invocation

Human-only endpoints (auth, API key management, webhook rules, webhook retry,
email notification rules) are intentionally excluded to keep the MCP surface
compact and security-scoped.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_current_user
from api.app.core.config import API_VERSION
from api.app.models.models import User, ApiKey

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import REST route handler functions (delegate, don't reimplement)
# ---------------------------------------------------------------------------
from api.app.api.projects import (
    list_projects as _rest_list_projects,
    create_project as _rest_create_project,
    update_project as _rest_update_project,
    CreateProjectRequest,
    UpdateProjectRequest,
)
from api.app.api.schemas import (
    get_schema as _rest_get_schema,
    update_schema as _rest_update_schema,
    SchemaGetRequest,
    SchemaUpdateRequest,
    FieldDefinition,
)
from api.app.api.members import (
    list_members as _rest_list_members,
    add_member as _rest_add_member,
    remove_member as _rest_remove_member,
    MemberListRequest,
    MemberAddRequest,
    MemberRemoveRequest,
)
from api.app.api.todos import (
    list_todos as _rest_list_todos,
    create_todo as _rest_create_todo,
    update_todo as _rest_update_todo,
    move_todo as _rest_move_todo,
    delete_todo as _rest_delete_todo,
    bulk_create_todos as _rest_bulk_create_todos,
    TodoListRequest,
    TodoCreateRequest,
    TodoUpdateRequest,
    TodoMoveRequest,
    TodoDeleteRequest,
    TodoBulkCreateRequest,
    BulkTodoItem,
)


router = APIRouter(prefix="/mcp", tags=["MCP"])

# ---------------------------------------------------------------------------
# MCP protocol constants
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-03-26"

SERVER_INFO = {
    "name": "open-todo",
    "version": API_VERSION,
}

SERVER_CAPABILITIES = {
    "tools": {},
}


# ---------------------------------------------------------------------------
# MCP Tool Schema definitions (returned by tools/list)
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {
        "name": "list_projects",
        "description": (
            "List all projects owned by the authenticated user. "
            "Returns an array of project objects with projectId, projectName, "
            "projectDescription, projectDirectory, and gitUrl."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "create_project",
        "description": (
            "Create a new project for the authenticated user. "
            "Returns the created project with projectId."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectName": {
                    "type": "string",
                    "description": "Human-readable project name.",
                },
                "projectDescription": {
                    "type": "string",
                    "description": "Optional project description.",
                },
                "projectDirectory": {
                    "type": "string",
                    "description": "Optional local filesystem directory path for the project.",
                },
                "gitUrl": {
                    "type": "string",
                    "description": "Optional Git repository URL.",
                },
            },
            "required": ["projectName"],
        },
    },
    {
        "name": "update_project",
        "description": (
            "Update project metadata (name, description, directory, git URL). "
            "Only provided fields are updated; omitted fields remain unchanged."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "UUID of the project to update.",
                },
                "projectName": {
                    "type": "string",
                    "description": "Updated project name.",
                },
                "projectDescription": {
                    "type": "string",
                    "description": "Updated project description.",
                },
                "projectDirectory": {
                    "type": "string",
                    "description": "Updated local filesystem directory path.",
                },
                "gitUrl": {
                    "type": "string",
                    "description": "Updated Git repository URL.",
                },
            },
            "required": ["projectId"],
        },
    },
    {
        "name": "get_project_schema",
        "description": (
            "Get the dynamic field schema for a project. Returns the fieldsDefinition array "
            "describing each field's name, type (text/number/date/enum/link/assignee), "
            "description, and enum values."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "UUID of the project.",
                },
            },
            "required": ["projectId"],
        },
    },
    {
        "name": "update_project_schema",
        "description": (
            "Replace the dynamic field schema for a project. "
            "Provide the full fieldsDefinition array (this is a full replacement, not a merge). "
            "Supported field types: text, number, date, enum, link, assignee."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "UUID of the project.",
                },
                "fieldsDefinition": {
                    "type": "array",
                    "description": "Array of field descriptors.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fieldName": {"type": "string"},
                            "fieldType": {"type": "string"},
                            "fieldDescription": {"type": "string"},
                            "enumValues": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["fieldName", "fieldType"],
                    },
                },
            },
            "required": ["projectId", "fieldsDefinition"],
        },
    },
    {
        "name": "list_todos",
        "description": (
            "List all todos (flat array) for a project. "
            "Build a tree by grouping on parentId (null = root)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "UUID of the project.",
                },
            },
            "required": ["projectId"],
        },
    },
    {
        "name": "create_todo",
        "description": (
            "Create a new todo in a project. Content is validated against the project schema. "
            "Optionally set parentId for tree nesting. "
            "Atomically inserts matching webhook outbox records."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "Project ID to create todo in.",
                },
                "parentId": {
                    "type": "string",
                    "description": "Parent todo ID for nesting (omit or null for root).",
                },
                "content": {
                    "type": "object",
                    "description": "Dynamic field values matching the project schema.",
                },
            },
            "required": ["projectId"],
        },
    },
    {
        "name": "update_todo",
        "description": (
            "Update a todo's content and/or completion status. "
            "Content is optional (omit for status-only changes). "
            "Supply version for optimistic concurrency control (409 on mismatch). "
            "Performs deep-diff; webhook payloads include before/after snapshots."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "todoId": {
                    "type": "string",
                    "description": "Todo ID to update.",
                },
                "content": {
                    "type": "object",
                    "description": "Updated dynamic field values (optional).",
                },
                "isCompleted": {
                    "type": "boolean",
                    "description": "Set completion status (optional).",
                },
                "version": {
                    "type": "integer",
                    "description": "Expected version for OCC (optional).",
                },
            },
            "required": ["todoId"],
        },
    },
    {
        "name": "move_todo",
        "description": (
            "Move (reparent) a todo within the same project. "
            "Set newParentId to null to move to root level. "
            "Validates no circular reference. Supply version for OCC."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "todoId": {
                    "type": "string",
                    "description": "Todo ID to reparent.",
                },
                "newParentId": {
                    "type": "string",
                    "description": "New parent todo ID (null = root).",
                },
                "version": {
                    "type": "integer",
                    "description": "Expected version for OCC (optional).",
                },
            },
            "required": ["todoId"],
        },
    },
    {
        "name": "delete_todo",
        "description": (
            "Delete a todo and all its descendants recursively. "
            "Webhook outbox records are inserted for each deleted node."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "todoId": {
                    "type": "string",
                    "description": "Todo ID to delete.",
                },
            },
            "required": ["todoId"],
        },
    },
    {
        "name": "list_members",
        "description": (
            "List all members (agents) registered in a project. "
            "Returns an array of member objects with memberId, agentId, "
            "displayName, description, and createdAt."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "UUID of the project.",
                },
            },
            "required": ["projectId"],
        },
    },
    {
        "name": "add_member",
        "description": (
            "Add an agent as a member of a project. "
            "The agentId must be unique within the project. "
            "displayName and description are optional."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "Project ID to add the member to.",
                },
                "agentId": {
                    "type": "string",
                    "description": "External agent identifier (must be unique within the project).",
                },
                "displayName": {
                    "type": "string",
                    "description": "Human-readable display name (optional).",
                },
                "description": {
                    "type": "string",
                    "description": "Agent introduction or role description (optional).",
                },
            },
            "required": ["projectId", "agentId"],
        },
    },
    {
        "name": "remove_member",
        "description": (
            "Remove a member (agent) from a project."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "memberId": {
                    "type": "string",
                    "description": "Member ID to remove.",
                },
            },
            "required": ["memberId"],
        },
    },
    {
        "name": "bulk_create_todos",
        "description": (
            "Create multiple todos in a single transaction within the same project. "
            "Useful for batch WBS decomposition. Each item can have its own parentId and content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {
                    "type": "string",
                    "description": "Project ID to create todos in.",
                },
                "items": {
                    "type": "array",
                    "description": "Array of todos to create.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "parentId": {
                                "type": "string",
                                "description": "Parent todo ID (null = root).",
                            },
                            "content": {
                                "type": "object",
                                "description": "Dynamic field values.",
                            },
                        },
                    },
                },
            },
            "required": ["projectId", "items"],
        },
    },
]


# ---------------------------------------------------------------------------
# Legacy request / response models (for /mcp/tools/call backwards compat)
# ---------------------------------------------------------------------------

class McpToolCallRequest(BaseModel):
    """Simplified MCP tools/call request."""
    name: str = Field(..., description="Tool name to invoke.")
    arguments: dict = Field(default_factory=dict, description="Tool arguments.")


class McpToolCallResponse(BaseModel):
    """Simplified MCP tools/call response."""
    content: list = Field(..., description="Array of content blocks.")
    isError: bool = Field(default=False, description="Whether the call resulted in an error.")


# ---------------------------------------------------------------------------
# Standard MCP Streamable HTTP transport (JSON-RPC 2.0)
# ---------------------------------------------------------------------------

def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict:
    """Build a JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "error": {"code": code, "message": message},
    }


def _jsonrpc_result(req_id: Any, result: Any) -> dict:
    """Build a JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "result": result,
    }


def _resolve_user_from_api_key(api_key: Optional[str], session: Session) -> Optional[User]:
    """Resolve user from X-API-KEY header value. Returns None if invalid."""
    if not api_key or not api_key.startswith("sk-otd-"):
        return None
    api_key_row = session.exec(
        select(ApiKey).where(
            ApiKey.key_value == api_key,
            ApiKey.is_enabled == True,
            ApiKey.is_deleted == False,
        )
    ).first()
    if api_key_row is None:
        return None
    return session.get(User, api_key_row.user_id)


def _handle_initialize(req_id: Any, params: dict) -> dict:
    """Handle 'initialize' JSON-RPC request."""
    return _jsonrpc_result(req_id, {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": SERVER_CAPABILITIES,
        "serverInfo": SERVER_INFO,
    })


def _handle_ping(req_id: Any) -> dict:
    """Handle 'ping' JSON-RPC request."""
    return _jsonrpc_result(req_id, {})


def _handle_tools_list(req_id: Any) -> dict:
    """Handle 'tools/list' JSON-RPC request."""
    return _jsonrpc_result(req_id, {"tools": MCP_TOOLS})


def _handle_tools_call(
    req_id: Any, params: dict, user: Optional[User], session: Session
) -> dict:
    """Handle 'tools/call' JSON-RPC request."""
    if user is None:
        return _jsonrpc_error(req_id, -32600, "Authentication required. Provide X-API-KEY header.")

    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        return _jsonrpc_error(req_id, -32602, "Missing 'name' in params.")

    try:
        result = _dispatch(tool_name, arguments, user, session)
        return _jsonrpc_result(req_id, {
            "content": [{"type": "text", "text": _serialize(result)}],
            "isError": False,
        })
    except HTTPException as e:
        return _jsonrpc_result(req_id, {
            "content": [{"type": "text", "text": f"Error {e.status_code}: {e.detail}"}],
            "isError": True,
        })
    except Exception as e:
        return _jsonrpc_result(req_id, {
            "content": [{"type": "text", "text": f"Internal error: {str(e)}"}],
            "isError": True,
        })


def _handle_single_message(
    msg: dict, user: Optional[User], session: Session
) -> Optional[dict]:
    """
    Process a single JSON-RPC message. Returns a response dict for requests,
    or None for notifications.
    """
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params", {})

    # Notifications (no "id" field) — acknowledge silently.
    if req_id is None:
        return None

    # Requests (have "id" field) — must return a response.
    if method == "initialize":
        return _handle_initialize(req_id, params)
    elif method == "ping":
        return _handle_ping(req_id)
    elif method == "tools/list":
        return _handle_tools_list(req_id)
    elif method == "tools/call":
        return _handle_tools_call(req_id, params, user, session)
    else:
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")


@router.post(
    "",
    summary="MCP Streamable HTTP endpoint",
    description=(
        "Standard MCP Streamable HTTP transport. Accepts JSON-RPC 2.0 messages "
        "(initialize, tools/list, tools/call, ping, notifications). "
        "Returns application/json responses."
    ),
    include_in_schema=False,
)
async def mcp_endpoint(request: Request):
    """
    MCP Streamable HTTP transport endpoint (POST /mcp).

    Accepts JSON-RPC 2.0 messages and returns JSON responses.
    Supports both single messages and batch arrays.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content=_jsonrpc_error(None, -32700, "Parse error."),
        )

    # Resolve user from API key (optional — initialize and tools/list don't need it).
    api_key = request.headers.get("X-API-KEY") or request.headers.get("x-api-key")
    session = next(get_session())
    try:
        user = _resolve_user_from_api_key(api_key, session)

        # Batch request (array of messages).
        if isinstance(body, list):
            responses = []
            all_notifications = True
            for msg in body:
                resp = _handle_single_message(msg, user, session)
                if resp is not None:
                    all_notifications = False
                    responses.append(resp)

            if all_notifications:
                return JSONResponse(status_code=202, content=None)

            if len(responses) == 1:
                return JSONResponse(
                    content=responses[0],
                    media_type="application/json",
                )
            return JSONResponse(
                content=responses,
                media_type="application/json",
            )

        # Single message.
        if isinstance(body, dict):
            resp = _handle_single_message(body, user, session)
            if resp is None:
                # Notification — return 202 Accepted.
                return JSONResponse(status_code=202, content=None)
            return JSONResponse(
                content=resp,
                media_type="application/json",
            )

        return JSONResponse(
            status_code=400,
            content=_jsonrpc_error(None, -32600, "Invalid request."),
        )
    finally:
        session.close()


@router.get(
    "",
    summary="MCP SSE stream (not supported)",
    description="Returns 405 — this server does not offer server-initiated SSE streams.",
    include_in_schema=False,
)
async def mcp_sse_not_supported():
    """GET /mcp — return 405 per the MCP spec (no server-initiated SSE)."""
    return JSONResponse(
        status_code=405,
        content={"detail": "Server does not offer SSE streams at this endpoint."},
    )


# ---------------------------------------------------------------------------
# Legacy routes (backwards compatibility)
# ---------------------------------------------------------------------------

@router.get(
    "/tools",
    summary="List available MCP tools (legacy)",
    description="Returns the MCP tool definitions that an AI agent can invoke.",
)
def list_tools():
    return {"tools": MCP_TOOLS}


@router.post(
    "/tools/call",
    response_model=McpToolCallResponse,
    summary="Invoke an MCP tool (legacy)",
    description="Execute one of the defined MCP tools with the given arguments.",
)
def call_tool(
    body: McpToolCallRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        result = _dispatch(body.name, body.arguments, user, session)
        return McpToolCallResponse(
            content=[{"type": "text", "text": _serialize(result)}],
            isError=False,
        )
    except HTTPException as e:
        return McpToolCallResponse(
            content=[{"type": "text", "text": f"Error {e.status_code}: {e.detail}"}],
            isError=True,
        )
    except Exception as e:
        return McpToolCallResponse(
            content=[{"type": "text", "text": f"Internal error: {str(e)}"}],
            isError=True,
        )


# ---------------------------------------------------------------------------
# Dispatch logic — delegates to REST route handler functions
# ---------------------------------------------------------------------------

def _dispatch(name: str, args: dict, user: User, session: Session) -> Any:
    """Route MCP tool call to the corresponding REST handler."""
    if name == "list_projects":
        return _do_list_projects(user, session)
    elif name == "create_project":
        return _do_create_project(args, user, session)
    elif name == "update_project":
        return _do_update_project(args, user, session)
    elif name == "get_project_schema":
        return _do_get_project_schema(args, user, session)
    elif name == "update_project_schema":
        return _do_update_project_schema(args, user, session)
    elif name == "list_todos":
        return _do_list_todos(args, user, session)
    elif name == "create_todo":
        return _do_create_todo(args, user, session)
    elif name == "update_todo":
        return _do_update_todo(args, user, session)
    elif name == "move_todo":
        return _do_move_todo(args, user, session)
    elif name == "delete_todo":
        return _do_delete_todo(args, user, session)
    elif name == "list_members":
        return _do_list_members(args, user, session)
    elif name == "add_member":
        return _do_add_member(args, user, session)
    elif name == "remove_member":
        return _do_remove_member(args, user, session)
    elif name == "bulk_create_todos":
        return _do_bulk_create_todos(args, user, session)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {name}.")


# ---------------------------------------------------------------------------
# Delegate functions — each constructs the request model and calls the
# REST handler directly, reusing all validation, outbox, and email logic.
# ---------------------------------------------------------------------------

def _do_list_projects(user: User, session: Session) -> Any:
    result = _rest_list_projects(session=session, current_user=user)
    return [r.model_dump() if hasattr(r, "model_dump") else r for r in result]


def _do_create_project(args: dict, user: User, session: Session) -> Any:
    body = CreateProjectRequest(
        projectName=args.get("projectName", ""),
        projectDescription=args.get("projectDescription"),
        projectDirectory=args.get("projectDirectory"),
        gitUrl=args.get("gitUrl"),
    )
    result = _rest_create_project(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_update_project(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    body = UpdateProjectRequest(
        projectId=project_id,
        projectName=args.get("projectName"),
        projectDescription=args.get("projectDescription"),
        projectDirectory=args.get("projectDirectory"),
        gitUrl=args.get("gitUrl"),
    )
    result = _rest_update_project(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_get_project_schema(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    body = SchemaGetRequest(projectId=project_id)
    result = _rest_get_schema(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_update_project_schema(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    raw_fields = args.get("fieldsDefinition", [])
    fields = [
        FieldDefinition(
            fieldName=fd.get("fieldName", ""),
            fieldType=fd.get("fieldType", "text"),
            fieldDescription=fd.get("fieldDescription"),
            enumValues=fd.get("enumValues"),
        )
        for fd in raw_fields
    ]
    body = SchemaUpdateRequest(projectId=project_id, fieldsDefinition=fields)
    result = _rest_update_schema(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_list_todos(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    body = TodoListRequest(projectId=project_id)
    result = _rest_list_todos(body=body, session=session, current_user=user)
    return [r.model_dump() if hasattr(r, "model_dump") else r for r in result]


def _do_create_todo(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    body = TodoCreateRequest(
        projectId=project_id,
        parentId=args.get("parentId"),
        content=args.get("content", {}),
    )
    result = _rest_create_todo(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_update_todo(args: dict, user: User, session: Session) -> Any:
    todo_id = args.get("todoId")
    if not todo_id:
        raise HTTPException(status_code=400, detail="todoId is required.")
    body = TodoUpdateRequest(
        todoId=todo_id,
        content=args.get("content"),
        isCompleted=args.get("isCompleted"),
        version=args.get("version"),
    )
    result = _rest_update_todo(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_move_todo(args: dict, user: User, session: Session) -> Any:
    todo_id = args.get("todoId")
    if not todo_id:
        raise HTTPException(status_code=400, detail="todoId is required.")
    body = TodoMoveRequest(
        todoId=todo_id,
        newParentId=args.get("newParentId"),
        version=args.get("version"),
    )
    result = _rest_move_todo(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_delete_todo(args: dict, user: User, session: Session) -> Any:
    todo_id = args.get("todoId")
    if not todo_id:
        raise HTTPException(status_code=400, detail="todoId is required.")
    body = TodoDeleteRequest(todoId=todo_id)
    result = _rest_delete_todo(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_bulk_create_todos(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    raw_items = args.get("items", [])
    items = [
        BulkTodoItem(
            parentId=item.get("parentId"),
            content=item.get("content", {}),
        )
        for item in raw_items
    ]
    body = TodoBulkCreateRequest(projectId=project_id, items=items)
    result = _rest_bulk_create_todos(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


# ---------------------------------------------------------------------------
# Member delegate functions
# ---------------------------------------------------------------------------

def _do_list_members(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    body = MemberListRequest(projectId=project_id)
    result = _rest_list_members(body=body, session=session, current_user=user)
    return [r.model_dump() if hasattr(r, "model_dump") else r for r in result]


def _do_add_member(args: dict, user: User, session: Session) -> Any:
    project_id = args.get("projectId")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required.")
    agent_id = args.get("agentId")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required.")
    body = MemberAddRequest(
        projectId=project_id,
        agentId=agent_id,
        displayName=args.get("displayName"),
        description=args.get("description"),
    )
    result = _rest_add_member(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


def _do_remove_member(args: dict, user: User, session: Session) -> Any:
    member_id = args.get("memberId")
    if not member_id:
        raise HTTPException(status_code=400, detail="memberId is required.")
    body = MemberRemoveRequest(memberId=member_id)
    result = _rest_remove_member(body=body, session=session, current_user=user)
    return result.model_dump() if hasattr(result, "model_dump") else result


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> str:
    """Convert result to JSON string for MCP response."""
    return json.dumps(obj, ensure_ascii=False, default=str)
