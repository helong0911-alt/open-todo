"""
SQLModel ORM models for Open-Todo (OTD).

All models use camelCase aliases for JSON serialization and database columns.
"""
import uuid
import secrets
from datetime import datetime, timezone
from typing import Any, Optional, List, TYPE_CHECKING

from pydantic import ConfigDict
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import Text, JSON, UniqueConstraint

from api.app.core.config import API_KEY_PREFIX


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_camel(name: str) -> str:
    """snake_case -> camelCase"""
    parts = name.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


def _generate_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def _generate_verification_token() -> str:
    """Generate a URL-safe token for email verification."""
    return secrets.token_urlsafe(48)


def _generate_session_token() -> str:
    """Generate a URL-safe token for web login sessions."""
    return f"ses-{secrets.token_urlsafe(48)}"


# ---------------------------------------------------------------------------
# Base with camelCase config
# ---------------------------------------------------------------------------

class CamelModel(SQLModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(CamelModel, table=True):
    """Registered user with email + password authentication."""

    __tablename__ = "user"

    user_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="userId",
        description="Unique user identifier (UUID).",
    )
    email: str = Field(
        index=True,
        unique=True,
        alias="email",
        description="User email address.",
    )
    password_hash: str = Field(
        alias="passwordHash",
        description="Bcrypt-hashed password.",
    )
    is_active: bool = Field(
        default=False,
        alias="isActive",
        description="Whether the user has verified their email and is active.",
    )
    verification_token: Optional[str] = Field(
        default_factory=_generate_verification_token,
        alias="verificationToken",
        description="Token for email verification (null after verified).",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Account creation timestamp (UTC).",
    )

    # relationships
    projects: List["Project"] = Relationship(back_populates="user")
    notification_rules: List["NotificationRule"] = Relationship(
        back_populates="user",
    )
    api_keys: List["ApiKey"] = Relationship(back_populates="user")
    session_tokens: List["SessionToken"] = Relationship(back_populates="user")


# ---------------------------------------------------------------------------
# ApiKey (multi-key per user)
# ---------------------------------------------------------------------------

class ApiKey(CamelModel, table=True):
    """
    API key for programmatic access.  Each user can own multiple keys.
    Keys can be named, enabled/disabled, and soft-deleted.
    """

    __tablename__ = "api_key"

    key_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="keyId",
        description="Unique key identifier (UUID).",
    )
    user_id: str = Field(
        foreign_key="user.user_id",
        index=True,
        alias="userId",
        description="Owner user ID.",
    )
    key_value: str = Field(
        default_factory=_generate_api_key,
        unique=True,
        index=True,
        alias="keyValue",
        description="API key string (prefix sk-otd-).",
    )
    key_name: str = Field(
        default="Default",
        alias="keyName",
        description="Human-readable key label.",
    )
    is_enabled: bool = Field(
        default=True,
        alias="isEnabled",
        description="Whether this key is currently active.",
    )
    is_deleted: bool = Field(
        default=False,
        alias="isDeleted",
        description="Soft-delete flag.",
    )
    is_system: bool = Field(
        default=False,
        alias="isSystem",
        description="System key flag. System keys cannot be renamed or deleted.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Key creation timestamp (UTC).",
    )

    # relationships
    user: Optional["User"] = Relationship(back_populates="api_keys")


# ---------------------------------------------------------------------------
# SessionToken (web login session)
# ---------------------------------------------------------------------------

class SessionToken(CamelModel, table=True):
    """
    Session token issued upon email + password login.  Used by the
    web client for authenticated requests (via ``X-SESSION-TOKEN`` header).
    Separate from API keys which are for programmatic / external access.
    """

    __tablename__ = "session_token"

    token_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="tokenId",
        description="Unique token identifier (UUID).",
    )
    user_id: str = Field(
        foreign_key="user.user_id",
        index=True,
        alias="userId",
        description="Owner user ID.",
    )
    token_value: str = Field(
        default_factory=_generate_session_token,
        unique=True,
        index=True,
        alias="tokenValue",
        description="Session token string (prefix ses-).",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Token creation timestamp (UTC).",
    )

    # relationships
    user: Optional["User"] = Relationship(back_populates="session_tokens")


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(CamelModel, table=True):
    """A project owned by a user."""

    __tablename__ = "project"

    project_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="projectId",
        description="Unique project identifier (UUID).",
    )
    user_id: str = Field(
        foreign_key="user.user_id",
        index=True,
        alias="userId",
        description="Owner user ID.",
    )
    project_name: str = Field(
        alias="projectName",
        description="Human-readable project name.",
    )
    project_description: Optional[str] = Field(
        default=None,
        alias="projectDescription",
        description="Optional project description.",
    )
    project_directory: Optional[str] = Field(
        default=None,
        alias="projectDirectory",
        description="Local filesystem directory path for the project.",
    )
    git_url: Optional[str] = Field(
        default=None,
        alias="gitUrl",
        description="Git repository URL for the project.",
    )

    # relationships
    user: Optional["User"] = Relationship(back_populates="projects")
    schema_def: Optional["ProjectSchema"] = Relationship(back_populates="project")
    todos: List["Todo"] = Relationship(back_populates="project")
    webhook_rules: List["WebhookRule"] = Relationship(back_populates="project")
    members: List["ProjectMember"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


# ---------------------------------------------------------------------------
# ProjectSchema (dynamic field definitions)
# ---------------------------------------------------------------------------

class ProjectSchema(CamelModel, table=True):
    """
    Dynamic field definitions for a project.
    `fieldsDefinition` stores a JSON array of field descriptors:
    [{ fieldName, fieldType, fieldDescription, enumValues }]
    Supported fieldType values: text, number, date, enum, link, assignee.
    """

    __tablename__ = "project_schema"

    schema_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="schemaId",
        description="Unique schema identifier.",
    )
    project_id: str = Field(
        foreign_key="project.project_id",
        unique=True,
        index=True,
        alias="projectId",
        description="Associated project ID.",
    )
    fields_definition: Any = Field(
        default=[],
        sa_column=Column(JSON, nullable=False, default=[]),
        alias="fieldsDefinition",
        description=(
            "JSON array of field descriptors. Each descriptor: "
            "{ fieldName: str, fieldType: text|number|date|enum|link|assignee, "
            "fieldDescription?: str, enumValues?: [str] }"
        ),
    )
    schema_version: int = Field(
        default=0,
        alias="schemaVersion",
        description="Monotonically increasing version; incremented on each schema update.",
    )

    # relationships
    project: Optional["Project"] = Relationship(back_populates="schema_def")


# ---------------------------------------------------------------------------
# Todo (self-referencing tree)
# ---------------------------------------------------------------------------

class Todo(CamelModel, table=True):
    """
    Task node with self-referencing tree structure for infinite-level WBS.
    `content` stores dynamic business data conforming to the project schema.
    """

    __tablename__ = "todo"

    todo_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="todoId",
        description="Unique todo identifier (UUID).",
    )
    project_id: str = Field(
        foreign_key="project.project_id",
        index=True,
        alias="projectId",
        description="Owning project ID.",
    )
    parent_id: Optional[str] = Field(
        default=None,
        foreign_key="todo.todo_id",
        index=True,
        alias="parentId",
        description="Parent todo ID for tree nesting (null = root node).",
    )
    content: Any = Field(
        default={},
        sa_column=Column(JSON, nullable=False, default={}),
        alias="content",
        description="Dynamic business data conforming to the project schema.",
    )
    is_completed: bool = Field(
        default=False,
        alias="isCompleted",
        description="Whether this task is completed.",
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        alias="updatedAt",
        description="Last update timestamp (UTC).",
    )
    version: int = Field(
        default=1,
        alias="version",
        description="Optimistic concurrency control version.",
    )
    schema_version: int = Field(
        default=0,
        alias="schemaVersion",
        description="Schema version this todo's content was last validated/healed against.",
    )

    # relationships
    project: Optional["Project"] = Relationship(back_populates="todos")
    children: List["Todo"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    parent: Optional["Todo"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Todo.todo_id"},
    )



# ---------------------------------------------------------------------------
# ProjectMember (Agent / Human registry per project)
# ---------------------------------------------------------------------------

class ProjectMember(CamelModel, table=True):
    """
    Project member registry.  Each record represents an agent (or future
    human member) that belongs to a project.  External systems query this
    table via MCP to discover available agents for task assignment.
    """

    __tablename__ = "project_member"
    __table_args__ = (
        UniqueConstraint("project_id", "agent_id", name="uq_project_member_project_agent"),
    )

    member_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="memberId",
        description="Unique member identifier (UUID, system-generated).",
    )
    project_id: str = Field(
        foreign_key="project.project_id",
        index=True,
        alias="projectId",
        description="Associated project ID.",
    )
    agent_id: str = Field(
        alias="agentId",
        description="External agent identifier defined by the caller.",
    )
    display_name: Optional[str] = Field(
        default=None,
        alias="displayName",
        description="Human-readable display name (optional).",
    )
    description: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        alias="description",
        description="Agent introduction or role description (optional).",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Member creation timestamp (UTC).",
    )

    # relationships
    project: Optional["Project"] = Relationship(back_populates="members")

# ---------------------------------------------------------------------------
# WebhookRule
# ---------------------------------------------------------------------------

class WebhookRule(CamelModel, table=True):
    """
    Defines which mutations trigger a webhook.
    `targetField` supports `*` (wildcard) to monitor all field changes.
    """

    __tablename__ = "webhook_rule"

    rule_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="ruleId",
        description="Unique rule identifier.",
    )
    project_id: str = Field(
        foreign_key="project.project_id",
        index=True,
        alias="projectId",
        description="Associated project ID.",
    )
    event_type: str = Field(
        alias="eventType",
        description="Event type: Create, Update, or Delete.",
    )
    target_field: str = Field(
        default="*",
        alias="targetField",
        description="Field name to monitor, or '*' for any field change.",
    )
    webhook_url: str = Field(
        alias="webhookUrl",
        description="URL to POST the webhook payload to.",
    )

    # relationships
    project: Optional["Project"] = Relationship(back_populates="webhook_rules")


# ---------------------------------------------------------------------------
# WebhookTask (Transactional Outbox)
# ---------------------------------------------------------------------------

class WebhookTask(CamelModel, table=True):
    """
    Outbox message table for reliable webhook delivery.
    Records are inserted atomically with the Todo mutation inside the same transaction.
    """

    __tablename__ = "webhook_task"

    task_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="taskId",
        description="Unique outbox task identifier.",
    )
    rule_id: str = Field(
        foreign_key="webhook_rule.rule_id",
        index=True,
        alias="ruleId",
        description="The webhook rule that triggered this task.",
    )
    todo_id: str = Field(
        index=True,
        alias="todoId",
        description="The todo that was mutated.",
    )
    payload: Any = Field(
        default={},
        sa_column=Column(JSON, nullable=False, default={}),
        alias="payload",
        description="JSON payload to deliver to the webhook URL.",
    )
    status: str = Field(
        default="pending",
        alias="status",
        description="Delivery status: pending, success, or failed.",
    )
    retry_count: int = Field(
        default=0,
        alias="retryCount",
        description="Number of delivery attempts made.",
    )
    next_retry_at: Optional[datetime] = Field(
        default=None,
        alias="nextRetryAt",
        description="Next scheduled retry time (UTC).",
    )
    last_error: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        alias="lastError",
        description="Error message from the last failed delivery attempt.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Outbox record creation timestamp.",
    )


# ---------------------------------------------------------------------------
# NotificationRule
# ---------------------------------------------------------------------------

class NotificationRule(CamelModel, table=True):
    """
    Per-user notification rule.  Each record declares that the user wants
    email notifications for a specific event type.  Supported event types:
    ``Verification``, ``TaskCreate``, ``TaskUpdate``, ``TaskDelete``,
    ``WebhookFailure``.
    """

    __tablename__ = "notification_rule"

    rule_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="ruleId",
        description="Unique notification rule identifier.",
    )
    user_id: str = Field(
        foreign_key="user.user_id",
        index=True,
        alias="userId",
        description="Owner user ID.",
    )
    event_type: str = Field(
        alias="eventType",
        description=(
            "Event type this rule monitors: "
            "Verification, TaskCreate, TaskUpdate, TaskDelete, WebhookFailure."
        ),
    )
    enabled: bool = Field(
        default=True,
        alias="enabled",
        description="Whether this rule is active.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Rule creation timestamp (UTC).",
    )

    # relationships
    user: Optional["User"] = Relationship(back_populates="notification_rules")


# ---------------------------------------------------------------------------
# EmailTask (Email Outbox Queue)
# ---------------------------------------------------------------------------

class EmailTask(CamelModel, table=True):
    """
    Email outbox queue.  Business code inserts records here; a background
    email worker polls the table, renders templates, and delivers via SMTP.
    Priority order: ``high`` > ``normal`` > ``low``.
    """

    __tablename__ = "email_task"

    task_id: str = Field(
        default_factory=_generate_uuid,
        primary_key=True,
        alias="taskId",
        description="Unique email task identifier.",
    )
    user_id: str = Field(
        foreign_key="user.user_id",
        index=True,
        alias="userId",
        description="Recipient user ID.",
    )
    to_address: str = Field(
        alias="toAddress",
        description="Recipient email address.",
    )
    subject: str = Field(
        alias="subject",
        description="Email subject line.",
    )
    template_name: str = Field(
        alias="templateName",
        description="Jinja2 template filename (e.g. verification.html).",
    )
    template_context: Any = Field(
        default={},
        sa_column=Column(JSON, nullable=False, default={}),
        alias="templateContext",
        description="JSON dict of template rendering variables.",
    )
    priority: str = Field(
        default="normal",
        index=True,
        alias="priority",
        description="Delivery priority: high, normal, or low.",
    )
    status: str = Field(
        default="pending",
        index=True,
        alias="status",
        description="Delivery status: pending, success, or failed.",
    )
    retry_count: int = Field(
        default=0,
        alias="retryCount",
        description="Number of delivery attempts made.",
    )
    next_retry_at: Optional[datetime] = Field(
        default=None,
        alias="nextRetryAt",
        description="Next scheduled retry time (UTC).",
    )
    last_error: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        alias="lastError",
        description="Error message from the last failed delivery attempt.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Queue insertion timestamp (UTC).",
    )


# ---------------------------------------------------------------------------
# CaptchaChallenge (DB-persisted captcha store)
# ---------------------------------------------------------------------------

class CaptchaChallenge(CamelModel, table=True):
    """
    Server-generated image captcha challenge.  Stored in the database so
    that ``uvicorn --reload`` or process restarts do not invalidate pending
    captchas.  Each challenge is single-use and expires after a TTL.
    """

    __tablename__ = "captcha_challenge"

    captcha_id: str = Field(
        primary_key=True,
        alias="captchaId",
        description="Unique captcha challenge ID (URL-safe token).",
    )
    answer: str = Field(
        alias="answer",
        description="Expected answer (uppercase).",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        alias="createdAt",
        description="Challenge creation timestamp (UTC).",
    )
