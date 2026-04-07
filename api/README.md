# Open-Todo API

> [中文文档](./README.zh-CN.md) | [Back to project root](../README.md)

FastAPI API service for Open-Todo -- AI-native task infrastructure with dynamic schemas, JIT self-healing, transactional outbox (webhooks + email), MCP Streamable HTTP transport, and dual authentication.

---

## Requirements

- Python 3.11+
- pip

## Installation

```bash
pip install -r requirements.txt
```

## Running

### Development Server

```bash
uvicorn api.app.main:app --host 0.0.0.0 --port 9000 --reload
```

The server starts at `http://localhost:9000`. Interactive API docs are available at `/docs` (Swagger) and `/redoc`.

### Docker

From the project root:

1. Create your environment file:
   ```bash
   cp .env.example .env
   # Edit .env with your SMTP_PASSWORD etc.
   nano .env
   ```
   > **Note:** The default initial admin account is `admin` / `admin123`. Please log in and change this immediately after your first deployment.

2. Start the service:
   ```bash
   docker compose up --build api
   ```

The `api` service listens on port 9000. The SQLite database is persisted in a Docker volume at `/app/data/otd.db`.

### Import Check

Quick sanity check that all modules resolve correctly:

```bash
python -c "from api.app.main import app; print('OK')"
```

## Running Tests

```bash
python -m pytest api/ -v                                  # all tests
python -m pytest api/tests/test_todos.py -v               # single file
python -m pytest api/tests/test_todos.py::test_create_todo -v  # single function
```

---

## Module Structure

```
api/
├── app/
│   ├── main.py               # FastAPI entry point, lifespan (DB init + workers)
│   ├── api/                   # Route modules
│   │   ├── auth.py            # POST /auth/captcha, /login, /register, /logout; GET /auth/verify
│   │   ├── api_keys.py        # POST /keys/create, /list, /update, /delete (session auth)
│   │   ├── projects.py        # GET /projects, POST /projects/create
│   │   ├── schemas.py         # POST /projects/schema/get, /projects/schema/update
│   │   ├── todos.py           # POST /todos/list, /create, /update, /move, /delete, /bulk-create
│   │   ├── webhooks.py        # POST /webhooks/create, /list, /tasks
│   │   ├── automation.py      # POST /automation/webhook/logs, /webhook/retry
│   │   ├── mcp.py             # POST /mcp (Streamable HTTP); legacy GET /mcp/tools, POST /mcp/tools/call
│   │   └── notifications.py   # POST /notifications/rules/create, /list, /update, /delete
│   ├── core/                  # Infrastructure
│   │   ├── config.py          # All env vars, constants (DB URL, SMTP, email, API metadata)
│   │   ├── database.py        # SQLite engine, session factory, PRAGMA foreign_keys=ON
│   │   ├── auth.py            # Dual auth: get_current_user (API key), get_session_user (session token)
│   │   ├── healer.py          # JIT Healing engine (schema evolution, type-default patching)
│   │   ├── validator.py       # Dynamic schema validation engine (6 field types)
│   │   ├── email.py           # Email enqueue layer + SMTP delivery (Jinja2 templates)
│   │   └── captcha.py         # DB-backed image captcha (generation + verification)
│   ├── models/
│   │   └── models.py          # All ORM models (11 tables)
│   ├── worker/
│   │   ├── base.py            # BaseOutboxWorker ABC (polling, backoff, lifecycle)
│   │   ├── outbox.py          # Webhook delivery worker (httpx, exponential backoff)
│   │   └── email_worker.py    # Email delivery worker (aiosmtplib, priority queue)
│   └── templates/email/       # Jinja2 HTML email templates
│       ├── verification.html      # Email verification link
│       ├── task_notification.html  # Todo CRUD notifications
│       └── webhook_failure.html   # Webhook delivery failure alert
├── Dockerfile
└── requirements.txt
```

## ORM Models (11 tables)

| Model | Table | Description |
|-------|-------|-------------|
| `User` | `user` | Email+password auth, `is_active` flag, verification token |
| `ApiKey` | `api_key` | `sk-otd-*` keys with enable/disable/soft-delete lifecycle |
| `SessionToken` | `session_token` | `ses-*` tokens for web login sessions |
| `Project` | `project` | User-owned projects with name and description |
| `ProjectSchema` | `project_schema` | Dynamic field definitions + monotonic `schemaVersion` |
| `Todo` | `todo` | Self-referencing tree (WBS), JSON content, OCC `version`, `schemaVersion` |
| `WebhookRule` | `webhook_rule` | Project-scoped event rules (Create/Update/Delete + target field) |
| `WebhookTask` | `webhook_task` | Transactional outbox for webhook delivery |
| `NotificationRule` | `notification_rule` | User-scoped email notification opt-in per event type |
| `EmailTask` | `email_task` | Transactional outbox for email delivery (priority queue) |
| `CaptchaChallenge` | `captcha_challenge` | Single-use image captchas (5-min TTL) |

## API Endpoints

### Authentication & Session Management

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/captcha` | No | Generate a captcha image (single-use, 5-min TTL) |
| `POST` | `/auth/register` | No | Register with email+password+captcha; enqueues verification email |
| `POST` | `/auth/login` | No | Login with email+password+captcha; returns session token |
| `GET` | `/auth/verify` | No | Verify email via `?token=xxx` query param |
| `POST` | `/auth/logout` | No | Invalidate a session token |
| `POST` | `/auth/change-password` | Session | Change the authenticated user's password |

### API Key Management (session-token auth)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/keys/create` | Session | Create a new API key (full value shown once) |
| `POST` | `/keys/list` | Session | List all keys (masked values) |
| `POST` | `/keys/update` | Session | Rename or enable/disable a key |
| `POST` | `/keys/delete` | Session | Soft-delete a key (irreversible) |

### Projects

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/projects` | API key | List user's projects |
| `POST` | `/projects/create` | API key | Create a project |

### Schemas

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/projects/schema/get` | API key | Get project field schema (auto-creates if none) |
| `POST` | `/projects/schema/update` | API key | Replace project field schema (increments `schemaVersion`) |

### Todos

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/todos/list` | API key | List todos for a project or all projects (flat array, JIT healed) |
| `POST` | `/todos/create` | API key | Create a todo (schema-validated, webhook outbox, email notify) |
| `POST` | `/todos/update` | API key | Update todo (OCC, deep diff, JIT heal write-back, webhooks) |
| `POST` | `/todos/move` | API key | Reparent a todo (circular-ref check, OCC) |
| `POST` | `/todos/delete` | API key | Recursive cascade delete (per-node webhook outbox) |
| `POST` | `/todos/bulk-create` | API key | Batch-create multiple todos in one transaction |

### Webhooks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/webhooks/create` | API key | Create a webhook rule |
| `POST` | `/webhooks/list` | API key | List webhook rules for a project |
| `POST` | `/webhooks/tasks` | API key | List outbox tasks for a project |

### Automation

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/automation/webhook/logs` | API key | Query delivery history (optional `todoId` filter) |
| `POST` | `/automation/webhook/retry` | API key | Retry a failed/pending delivery |

### Email Notifications

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/notifications/rules/create` | API key | Create notification rule (TaskCreate/TaskUpdate/TaskDelete/WebhookFailure) |
| `POST` | `/notifications/rules/list` | API key | List all rules for the user |
| `POST` | `/notifications/rules/update` | API key | Enable/disable a rule |
| `POST` | `/notifications/rules/delete` | API key | Hard-delete a rule |

### MCP (Model Context Protocol)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/mcp` | Varies | Standard MCP Streamable HTTP (JSON-RPC 2.0: initialize, tools/list, tools/call, ping) |
| `GET` | `/mcp` | — | Returns 405 (no server-initiated SSE) |
| `GET` | `/mcp/tools` | No | Legacy tool discovery |
| `POST` | `/mcp/tools/call` | API key | Legacy tool invocation |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | No | Health check (returns service name + version) |

## Key Design Decisions

- **POST-only mutations**: No PATCH, PUT, or DELETE. IDs always in request body, never in URL paths.
- **camelCase everywhere**: JSON fields, webhook payloads, database aliases.
- **Dual authentication**: API keys (`sk-otd-*`, `X-API-KEY` header) for programmatic access; session tokens (`ses-*`, `X-SESSION-TOKEN` header) for web sessions.
- **Transactional outbox**: Webhook tasks and email tasks are inserted atomically with data mutations.
- **JIT Healing**: Schema evolution without migrations -- missing fields are patched on read (in-memory) and persisted on write.
- **Optimistic concurrency**: Supply `version` on update; mismatch returns 409 Conflict.
- **Dynamic validation**: Content is checked against the project schema; error messages reference `fieldDescription` for AI self-correction.
- **MCP Streamable HTTP**: Standard JSON-RPC 2.0 transport at `POST /mcp` with 10 AI-accessible tools.
- **SQLite default**: Zero-config, `PRAGMA foreign_keys=ON` enforced on every connection.

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | `>=0.104.0` | Web framework |
| `uvicorn[standard]` | `>=0.24.0` | ASGI server |
| `sqlmodel` | `>=0.0.14` | ORM (SQLAlchemy + Pydantic) |
| `pydantic` | `>=2.5.0` | Data validation |
| `httpx` | `>=0.25.0` | Async HTTP client (webhook delivery) |
| `python-dotenv` | `>=1.0.0` | Environment variable loading |
| `aiosmtplib` | `>=3.0.0` | Async SMTP client (email delivery) |
| `jinja2` | `>=3.1.0` | Email template rendering |
| `captcha` | `>=0.6.0` | Image captcha generation |
| `bcrypt` | `>=4.0.0` | Password hashing |

---

> [Back to project root](../README.md)
