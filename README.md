# Open-Todo (OTD)

> [中文文档](./README.zh-CN.md)

**AI-Native Task Infrastructure — Technical Whitepaper**

---

## 🚀 System Vision & Core Architecture

Open-Todo is not another task manager. It is **industrial-grade task infrastructure** designed from the ground up for programmatic consumption — by AI agents, automation pipelines, and human developers alike.

Three foundational pillars define the architecture:

### Infinite-Level WBS (Work Breakdown Structure)

Tasks form an **unbounded tree** via adjacency-list self-referencing (`Todo.parentId` -> `Todo.todoId`). There is no depth limit. A single project can model everything from a top-level epic down to atomic subtasks across arbitrary nesting levels.

- **Reparenting**: `move_todo` relocates a node (and its entire subtree) to a new parent. BFS-based circular reference detection prevents corrupt trees.
- **Cascade delete**: `delete_todo` performs BFS descendant collection and removes the entire subtree. Every deleted node gets its own outbox entry for webhook notification — no silent data loss.

### Dynamic Schema Engine

Each project defines its own data model at runtime via `fieldsDefinition` — an array of field descriptors supporting 6 types:

| Field Type | Storage | Default (JIT Healing) |
|------------|---------|----------------------|
| `text` | string | `""` |
| `number` | number | `0` |
| `date` | string (ISO) | `""` |
| `enum` | string | first `enumValues` entry |
| `link` | string (URL) | `""` |
| `assignee` | string | `""` |

Every `create_todo` and `update_todo` validates the submitted `content` against the project schema before persistence. Invalid field names or type mismatches are rejected with `422`.

This means a CRM pipeline, a sprint board, and a hiring tracker can all coexist in the same OTD instance with completely different field structures — no migrations, no code changes.

### POST-Only Mutation Contract

**No PATCH. No PUT. No DELETE.** All mutations use `POST`. All identifiers are passed in the JSON request body, never in URL path parameters. This eliminates HTTP verb ambiguity and makes payload construction fully deterministic for AI agents.

Even read-with-filter endpoints (e.g., `/todos/list`) use POST to accept structured query bodies. Only simple parameter-free reads use GET.

---

## 🛡️ Data Evolution Philosophy: JIT Healing (Just-In-Time Self-Healing)

Schema changes are inevitable. In traditional systems, adding or removing a field means running migrations, backfilling data, or accepting inconsistency. Open-Todo takes a different approach: **JIT Healing**.

### The Problem

When a project schema changes (e.g., a new `priority` enum field is added), existing todos have no value for that field. Reading them produces incomplete data. Traditional solutions:

- **Migration scripts**: Downtime, batch processing, fragile.
- **Nullable everywhere**: Pushes complexity to every consumer.
- **Schema versioning with converters**: Heavy infrastructure.

### The OTD Solution

Every todo stamps its `schemaVersion` at creation/update time. The project schema tracks a monotonically increasing `schemaVersion` that auto-increments on every schema update.

When a todo is read and its `schemaVersion` < the project's current `schemaVersion`, OTD applies **JIT Healing**:

1. **On Read (list/get)**: Missing fields are patched **in-memory** using type-appropriate defaults (see table above). The database is NOT touched. The todo appears complete to the consumer.

2. **On Write (update)**: The content is first healed, then the user's changes are merged on top, and the result is persisted with the current `schemaVersion`. The old data is **physically upgraded** as a side effect of the next write.

### Properties

- **Zero downtime**: No migration step. Schema changes are instant.
- **Transparent**: Consumers always see a complete, schema-conformant object.
- **Conservative**: Healing only fills MISSING fields. It never overwrites existing values.
- **Lazy physical upgrade**: Data is upgraded in-place only when it is next written, avoiding unnecessary I/O.

---

## 🤖 AI Integration & MCP Access Guide

Open-Todo implements the **MCP Streamable HTTP transport** ([2025-03-26 spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http)) — the standard JSON-RPC 2.0 protocol used by MCP clients like Claude Code, OpenCode, Cursor, and VS Code Copilot.

### Protocol Mechanics

**Primary endpoint** (standard MCP Streamable HTTP):

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/mcp` | POST | Varies | JSON-RPC 2.0 dispatch — `initialize`, `tools/list`, `tools/call`, `ping` |
| `/mcp` | GET | — | Returns 405 (no server-initiated SSE streams) |

- `initialize`, `ping`, and `tools/list` require **no authentication**.
- `tools/call` requires `X-API-KEY` header.
- Tool call errors are returned inside the JSON-RPC result with `isError: true`, not as HTTP error codes. This prevents AI clients from confusing HTTP-level errors with business-level errors.

**Legacy endpoints** (kept for backwards compatibility):

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/mcp/tools` | GET | None | Tool discovery |
| `/mcp/tools/call` | POST | `X-API-KEY` | Tool invocation |

### Available Tools (10)

| # | Tool | Description |
|---|------|-------------|
| 1 | `list_projects` | List all projects owned by the user |
| 2 | `create_project` | Create a new project |
| 3 | `get_project_schema` | Get a project's dynamic field schema |
| 4 | `update_project_schema` | Replace a project's field schema |
| 5 | `list_todos` | List all todos for a project (flat array, build tree via `parentId`) |
| 6 | `create_todo` | Create a todo with schema-validated content |
| 7 | `update_todo` | Update content/status with OCC and deep-diff |
| 8 | `move_todo` | Reparent a todo within its project |
| 9 | `delete_todo` | Delete a todo and all descendants recursively |
| 10 | `bulk_create_todos` | Batch-create multiple todos in a single transaction |

> **Note**: Webhook rules, webhook delivery logs, and email notification rules are managed exclusively through the web dashboard and are not exposed as MCP tools.

### Authentication for AI Agents

Open-Todo uses API keys with the prefix `sk-otd-` for all programmatic access. The key is passed via the `X-API-KEY` HTTP header.

**Obtaining a key**:
1. Register an account via the web UI or `POST /auth/register`.
2. Verify your email via the link sent to your inbox.
3. Log in and create an API key from the Key Management page. The full key is shown **only once**.

### MCP Client Configuration

#### Claude Code (CLI `claude`)

In your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "sk-otd-your-api-key-here"
      }
    }
  }
}
```

Or use environment variables for silent auth:

```json
{
  "mcpServers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "${OTD_API_KEY}"
      }
    }
  }
}
```

Then set `export OTD_API_KEY=sk-otd-...` in your shell before launching.

#### VS Code (Claude Desktop / Copilot)

In `.vscode/mcp.json`:

```json
{
  "servers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "${OTD_API_KEY}"
      }
    }
  }
}
```

#### OpenCode

In your project's `opencode.json` or `~/.opencode/config.json`:

```json
{
  "mcp": {
    "open-todo": {
      "type": "remote",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "{env:OTD_API_KEY}"
      }
    }
  }
}
```

> **Note**: OpenCode uses `{env:VAR_NAME}` syntax for environment variable interpolation, not `${VAR_NAME}`.

#### Cursor / Continue

Add to your MCP configuration file (e.g., `.cursor/mcp.json` or the equivalent):

```json
{
  "mcpServers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "${OTD_API_KEY}"
      }
    }
  }
}
```

**Key points**:
- Environment variable syntax varies by client: OpenCode uses `{env:VAR_NAME}`, Claude Code / VS Code / Cursor use `${VAR_NAME}`.
- The actual key never appears in config files checked into version control.
- The `/mcp` endpoint handles the full MCP protocol — clients do NOT need to append `/tools` or `/tools/call`.
- Tool discovery (`tools/list`) requires no authentication, so clients can enumerate available tools before any key is configured.

### Human-Only vs. AI-Accessible Boundaries

OTD enforces a clear security boundary:

| Domain | Endpoints | Auth | Access |
|--------|-----------|------|--------|
| Auth & Registration | `/auth/*` | Session token | Human only |
| API Key Management | `/keys/*` | Session token | Human only |
| Webhook Rules & Logs | `/webhooks/*`, `/automation/*` | Session token | Human only |
| Email Notification Rules | `/notifications/*` | Session token | Human only |
| All 10 MCP Tools | `POST /mcp` | API key (`X-API-KEY`) | AI agents |
| REST API (CRUD) | `/projects/*`, `/todos/*`, etc. | API key (`X-API-KEY`) | AI + Human |

This means an AI agent **cannot** register accounts, create API keys, configure webhook destinations, or manage notification rules. These privileged operations require human login via session tokens.

---

## 📡 Reliability Model & Automation

### Transactional Outbox Pattern

Webhook delivery is **never fire-and-forget**. When a todo is created, updated, or deleted, the corresponding `WebhookTask` outbox record is inserted **in the same database transaction** as the data mutation. If the commit succeeds, the webhook task exists. If it fails, neither the data change nor the webhook task persists. This guarantees **exactly-once intent** for notifications.

**Worker mechanics**:
- Polls every **5 seconds**, batch limit **100 tasks** per cycle.
- HTTP delivery timeout: **15 seconds**.
- **5 retries** with exponential backoff: 2, 4, 8, 16 minutes between attempts.
- Task statuses: `pending` -> `success` | `failed`.
- On final failure (all 5 retries exhausted): enqueues a `WebhookFailure` email alert.

### Multi-Modal Notification

OTD supports two complementary notification channels:

**1. Passive Push — Webhooks**

Project-scoped rules define which events (`todo.created`, `todo.updated`, `todo.deleted`) trigger HTTP POST callbacks to external URLs. Payloads include full `before`/`after` deep-diff snapshots.

**2. Active Reports — Email Notifications**

User-scoped rules opt into email alerts for 4 event types:

| Event Type | Priority | Description |
|------------|----------|-------------|
| `TaskCreate` | Normal | A todo was created |
| `TaskUpdate` | Normal | A todo was updated |
| `TaskDelete` | Normal | A todo was deleted |
| `WebhookFailure` | High | A webhook delivery permanently failed |

Email delivery uses its own `EmailTask` outbox with the same transactional guarantees, priority queue (high > normal > low), and retry mechanics. Three Jinja2 HTML templates power the email rendering.

A 5th event type, `Verification`, is always sent during registration at high priority and cannot be controlled by notification rules.

**Gating**: Email delivery is disabled by default. Set `MAIL_ENABLED=true` and configure SMTP credentials in `.env` to activate.

---

## 🔐 Identity & Credential Management

### Two-Tier Authentication

OTD separates human and machine authentication:

| Tier | Header | Prefix | Use Case |
|------|--------|--------|----------|
| Session Token | `X-SESSION-TOKEN` | `ses-` | Web login, key management, webhook config |
| API Key | `X-API-KEY` | `sk-otd-` | Programmatic access, MCP tools, REST API |

### Multi-Key Architecture

Each user can create **multiple API keys** with independent lifecycles. This enables:

- **Per-agent isolation**: Give each AI agent (Claude, GPT, Cursor) its own key.
- **Key rotation**: Create a new key, update the agent config, disable the old key — zero downtime.
- **Audit trail**: Key-level access tracking.

**Key lifecycle**:

```
Create (sk-otd-... shown once)
  -> Active (is_enabled=true, is_deleted=false)
  -> Disabled (is_enabled=false, is_deleted=false)   [reversible]
  -> Soft-deleted (is_enabled=false, is_deleted=true) [irreversible]
```

When listing keys, the API returns **masked values**: first 12 characters + `...` + last 4 characters. The full key is shown only at creation time.

### Registration Flow

1. `POST /auth/register` with `email`, `password`, and `captchaId`/`captchaCode`.
2. A verification email is sent (if `MAIL_ENABLED=true`).
3. User clicks the link in the email -> `GET /auth/verify?token=xxx` activates the account.
4. Unverified users are blocked from login with `403`.

---

## 🏗️ Quick Start

### Docker Compose (Recommended)

```bash
git clone <repo-url> && cd open-todo
cp .env.example .env   # edit SMTP settings if you want email
docker compose up --build
```

- **API**: http://localhost:9000
- **Web**: http://localhost:3030
- **API Docs**: http://localhost:9000/docs

### Local Development

**API**:
```bash
pip install -r api/requirements.txt
uvicorn api.app.main:app --host 0.0.0.0 --port 9000 --reload
```

**Web**:
```bash
cd web
npm install
npm run dev   # proxies /api -> localhost:9000
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./otd.db` | Database connection string |
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP server port |
| `SMTP_USERNAME` | — | SMTP login username |
| `SMTP_PASSWORD` | — | SMTP login password |
| `SMTP_USE_TLS` | `true` | Enable STARTTLS |
| `MAIL_FROM_ADDRESS` | — | Sender email address |
| `MAIL_FROM_NAME` | — | Sender display name |
| `MAIL_ENABLED` | `false` | Enable email delivery |
| `APP_BASE_URL` | `http://localhost:9000` | API base URL |
| `WEB_BASE_URL` | `http://localhost:3030` | Web base URL (for email links) |

---

## 🔄 CI/CD

Open-Todo uses GitHub Actions for continuous integration and deployment. The workflow is defined in `.github/workflows/deploy.yml`.

### Pipeline Overview

```
Pull Request (any branch)          Push to main
        │                                │
        ▼                                ▼
  ┌───────────┐                    ┌───────────┐
  │ api-test  │                    │ api-test  │
  │ web-test  │                    │ web-test  │
  └───────────┘                    └─────┬─────┘
        │                                │
     (done)                              ▼
                                   ┌───────────┐
                                   │  deploy   │
                                   └───────────┘
```

- **Pull Request** — triggers lint & test only (no deploy).
- **Push to main** — triggers lint & test, then SSH deploy to server.

### What Each Job Does

| Job | Directory | Steps |
|-----|-----------|-------|
| `api-test` | `api/` | Install Python 3.11 deps, import check, `pytest` |
| `web-test` | `web/` | Install Node 20 deps, `vue-tsc` type check, `npm run build` |
| `deploy` | — | SSH into server, automatic `git clone`/`pull`, configure `.env` via secrets, `docker compose up -d --build` |

### Required GitHub Secrets

Before the deploy job can run, configure these secrets in **Settings > Secrets and variables > Actions**:

| Secret | Description | Required |
|--------|-------------|----------|
| `DEPLOY_HOST` | Server IP or hostname | Yes |
| `DEPLOY_USER` | SSH username (must be in `docker` group) | Yes |
| `DEPLOY_SSH_KEY` | SSH private key (full PEM content) | Yes |
| `DEPLOY_PATH` | Absolute path to project on server | Yes |
| `DEPLOY_PORT` | SSH port (defaults to 22) | No |
| `DATABASE_URL` | Production Database URL | No |
| `MAIL_ENABLED` | Set to "true" to enable SMTP | No |
| `SMTP_*` | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | No |
| `PIP_INDEX_URL`| Custom pip mirror (e.g. `https://pypi.tuna.tsinghua.edu.cn/simple/`) to speed up docker builds | No |

### Server Setup

On the target server, ensure:

1. **Docker** and **Docker Compose** are installed.
2. The user configured in `DEPLOY_USER` is added to the docker group:
   ```bash
   sudo usermod -aG docker <your-deploy-user>
   ```

> **Note:** The deployment script automatically handles cloning the repository into `DEPLOY_PATH` if it doesn't exist, and securely injects your secrets into the `.env` file before executing Docker. The default admin account initialized on first run is `admin` / `admin123`. Please log in and change this immediately after your first deployment!

#### Alternative: Non-Docker Deployment
If you prefer not to use Docker, ensure Python 3.11+ and Node 20+ are installed on your server. You will need to modify `.github/workflows/deploy.yml` to remove the Docker commands and restore the manual build steps (e.g. `pip install`, `npm run build`, and restarting via `pm2` or `systemd`).

### Running CI Locally

You can replicate the CI checks locally before pushing:

```bash
# API
pip install -r api/requirements.txt
python -c "from api.app.main import app; print('OK')"
python -m pytest api/ -v

# Web
cd web
npm install
npx vue-tsc -b
npm run build
```

---

## 🧩 Tech Stack

| Layer | Technology |
|-------|-----------|
| API | Python 3.11+, FastAPI, SQLModel, Pydantic v2, httpx |
| Web | Vue 3, TypeScript (strict), Vite, Tailwind CSS, Naive UI |
| Database | SQLite (default), JSON columns for dynamic content |
| Deploy | Docker Compose (api `:9000`, web `:3030`) |

---

## 📁 Project Structure

```
open-todo/
├── api/                      # API service
│   ├── app/
│   │   ├── main.py           # FastAPI entry + lifespan (workers)
│   │   ├── api/              # Route modules
│   │   │   ├── auth.py       # Register, login, verify, captcha
│   │   │   ├── api_keys.py   # Multi-key CRUD (session auth)
│   │   │   ├── projects.py   # Project CRUD
│   │   │   ├── schemas.py    # Dynamic schema get/update
│   │   │   ├── todos.py      # Todo CRUD + JIT healing + outbox
│   │   │   ├── webhooks.py   # Webhook rule CRUD
│   │   │   ├── automation.py # Webhook logs + retry
│   │   │   ├── mcp.py        # MCP tool definitions (10 tools)
│   │   │   └── notifications.py  # Email notification rules
│   │   ├── core/             # Infrastructure
│   │   │   ├── config.py     # Env vars, constants
│   │   │   ├── database.py   # Engine, sessions, FK pragma
│   │   │   ├── auth.py       # get_current_user / get_session_user
│   │   │   ├── healer.py     # JIT Healing engine
│   │   │   ├── validator.py  # Schema validation
│   │   │   ├── email.py      # Email enqueue + SMTP send
│   │   │   └── captcha.py    # DB-based captcha
│   │   ├── models/
│   │   │   └── models.py     # All SQLModel ORM definitions
│   │   ├── worker/
│   │   │   ├── base.py       # BaseOutboxWorker ABC
│   │   │   ├── outbox.py     # Webhook delivery worker
│   │   │   └── email_worker.py  # Email delivery worker
│   │   └── templates/email/  # Jinja2 email templates
│   ├── Dockerfile
│   └── requirements.txt
├── web/                      # Web application
│   ├── src/
│   │   ├── api/              # Axios HTTP client
│   │   ├── components/       # TodoTreeRow, DynamicFieldRenderer
│   │   ├── composables/      # Singleton state (useProject, useTodos)
│   │   ├── views/            # All page views (Projects, Tree, Automations, User Center, etc.)
│   │   ├── types/            # TypeScript interfaces
│   │   └── router/           # Vue Router config
│   ├── nginx.conf        # Nginx configuration for proxy and SPA routing
│   ├── Dockerfile
│   └── package.json
├── skills/                   # AI skill definitions
│   └── open-todo/            # Open-Todo specific skills
│       ├── open-todo-projects.md # Project Manager skill
│       ├── open-todo-schemas.md  # Schema Designer skill
│       ├── open-todo-tasks.md    # Task Manager skill
│       ├── SKILL.md              # Skill directory and integration guide
│       └── README.md             # Skill authoring guide
├── docker-compose.yml
├── AGENTS.md                 # AI agent coding conventions
└── .env.example              # Environment variable template
```

> **API details**: see [api/README.md](./api/README.md)
> **Web details**: see [web/README.md](./web/README.md)

---

## 📜 License

[Apache License 2.0](./LICENSE)
