# AGENTS.md — Open-Todo (OTD)

AI-native task infrastructure: FastAPI API, Vue 3 web, SQLite, infinite-level WBS tree.

## Agent Core Directives
- **Self-Sufficiency**: You are operating in a full-stack environment (FastAPI + Vue 3). Use the specific test and build commands below to verify your work.
- **Context is Key**: Before modifying logic, always check existing code patterns. Do not invent new structures or libraries unless necessary.
- **No Path Params**: Ensure all API mutations use POST with body parameters (no PUT/PATCH/DELETE).
- **Run Tests**: If editing `api/`, you must run the relevant pytest command to ensure no regressions.

## Project Layout

```
api/                        # FastAPI API (Python 3.11+)
  app/main.py               # Entry point, lifespan workers
  app/models/models.py      # All 11 ORM models (CamelModel base)
  app/core/                  # Shared infra: auth, database, config, healer, validator, email, captcha
  app/api/                   # Route modules: auth, projects, schemas, todos, webhooks, automation, mcp, notifications, api_keys
  app/worker/                # Background workers: outbox (webhooks), email_worker
  app/templates/email/       # Jinja2 email templates
web/                        # Vue 3 + Vite web (TypeScript strict)
  src/views/                 # 5 views (PascalCase)
  src/components/            # 2 reusable components
  src/composables/           # Singleton-pattern state (useProject, useTodos, useTheme)
  src/api/index.ts           # Axios client + all API functions
  src/types/index.ts         # All TypeScript interfaces
skills/                     # MCP/AI skill documentation
```

## Build / Lint / Test Commands

```bash
pip install -r api/requirements.txt                       # install deps
uvicorn api.app.main:app --host 0.0.0.0 --port 9000 --reload  # dev server

python -m pytest api/ -v                                  # all tests (from repo root)
python -m pytest api/tests/test_todos.py -v               # single test file
python -m pytest api/tests/test_todos.py::test_create_todo -v  # single test function
python -c "from api.app.main import app; print('OK')"    # quick import check
```

```bash
cd web
npm install          # install deps
npm run dev          # dev server on :3030 (proxies /api -> api :9000)
npm run build        # type-check (vue-tsc) then vite build
npx vue-tsc -b       # type-check only (no emit)
```

```bash
docker compose up --build          # api :9000, web :3030
```

No linter/formatter config on either side. Follow existing code patterns.

## Code Style — API (Python)

### Imports

Always absolute, never relative. Three-block order separated by blank lines:

1. Standard library (`uuid`, `datetime`, `logging`, `asyncio`)
2. Third-party (`fastapi`, `pydantic`, `sqlmodel`, `sqlalchemy`, `httpx`)
3. Internal (`from api.app.core.database import get_session`)

**Never use `from __future__ import annotations`** — it breaks SQLModel relationship resolution at runtime.

### Naming

- **Python code**: `snake_case` everywhere (variables, functions, parameters, file names).
- **API boundary**: `camelCase` everywhere (JSON request/response fields, webhook payloads).
- **Private helpers**: underscore prefix (`_to_camel`, `_verify_project_access`).

### ORM Models

All models inherit from `CamelModel(SQLModel)` which applies `alias_generator=_to_camel` and `populate_by_name=True`. Every model must:

- Set `table=True` and explicit `__tablename__`
- Provide explicit `alias="camelCaseName"` on every `Field`
- Provide `description="..."` on every `Field`
- Use `default_factory=_generate_uuid` for PK fields (str UUID)
- Use `sa_column=Column(JSON, ...)` for JSON columns

### Request/Response Schemas

Use `pydantic.BaseModel` (NOT SQLModel). Field names are **native camelCase** (not snake_case + alias):

```python
class TodoCreateRequest(BaseModel):
    projectId: str = Field(..., description="Project ID.")
    parentId: Optional[str] = Field(None, description="Parent todo ID.")
    content: Dict[str, Any] = Field(default_factory=dict)
```

Construct responses by manually mapping ORM fields — never return ORM objects directly.

### Routers

- `APIRouter(prefix="/resource", tags=["Resource"])`
- Route decorators include `response_model`, `summary`, `description`
- Every route handler receives `session: Session = Depends(get_session)` and
  `user: User = Depends(get_current_user)` (except `/auth/register` and `/` health)

### Authentication

Two auth strategies via FastAPI `Depends()`:

- **`get_current_user`** — validates `X-API-KEY` header (`sk-otd-*` prefix). Used by all resource routes.
- **`get_session_user`** — validates `X-SESSION-TOKEN` header (`ses-*` prefix). Used by web-only routes (key management, user profile).

### Method Constraint

**No PATCH, PUT, or DELETE.** All mutations use POST. IDs are always in the JSON request body, never in URL path parameters. Even read-with-body endpoints use POST (e.g., `/todos/list`). Only simple parameter-free reads use GET.

### Error Handling

Use `HTTPException` exclusively. Standard status codes:

| Code | When |
|------|------|
| 401  | Missing/invalid API key or session token |
| 403  | User doesn't own the resource |
| 404  | Entity not found |
| 409  | Duplicate email, version mismatch (OCC) |
| 422  | Schema validation failure |

Detail messages are human-readable and end with a period.

### Database Patterns

- `session.add()` → `session.commit()` → `session.refresh()` cycle.
- Use `session.flush()` when you need the ID before commit (e.g., outbox inserts).
- `PRAGMA foreign_keys=ON` is set on every SQLite connection via event listener.
- SQLite stores datetime as naive; use `.replace(tzinfo=None)` for comparisons.
- Transactional outbox: `WebhookTask` / `EmailTask` rows are inserted in the same transaction as data mutations, then processed by background workers.

### Code Organization

- Every `.py` file starts with a triple-quoted docstring.
- Sections separated by `# ---------------------------------------------------------------------------`
- Standard section order in API modules: Schemas → Helpers → Routes
- Workers inherit from `BaseOutboxWorker` (polling loop, batch processing, exponential backoff).

## Code Style — Web (TypeScript / Vue 3)

### Components

- Always `<script setup lang="ts">` (Composition API).
- No `<style>` blocks — all styling via Tailwind utility classes.
- File names: PascalCase (`TodoTreeRow.vue`, `ProjectDetailView.vue`).
- Views in `src/views/`, reusable components in `src/components/`.
- `strict: true` in tsconfig. Path alias `@/*` → `src/*`.
- All interfaces in `src/types/index.ts`, mirroring API response shapes in camelCase.
- Props: `defineProps<{...}>()`. Emits: typed `defineEmits<{...}>()`.

### State Management

Composables with module-scope `ref()` (singleton pattern), not Pinia stores:

```typescript
const items = ref<Item[]>([])        // module-scope = shared
export function useItems() {          // returns functions operating on shared state
  async function fetch() { ... }
  return { items, fetch }
}
```

### API Client (`src/api/index.ts`)

- Axios instance with `baseURL: '/api'`; interceptor attaches `X-API-KEY` or `X-SESSION-TOKEN` from `localStorage`.
- Functions named `<resource><Action>` (e.g., `todosList`, `todosCreate`).
- All mutations POST, all payloads camelCase, all return `.then(r => r.data)`.
- IDs always in request body, never in URL paths.

### Routing

- `createWebHistory()`, lazy-loaded views via `() => import(...)`.
- Route names: kebab-case (`project-detail`). Props: `props: true`.

### Error Handling & UI

- `try/catch` around API calls in views/composables.
- Error extraction: `err?.response?.data?.detail || 'Fallback message'`.
- Display: Naive UI `useMessage()` in views, `window.alert()` in App.vue.
- Naive UI components (NButton, NInput, NCard, NModal, NTag, etc.).
- Light/dark theme toggle via `useTheme` composable. Persists to `localStorage`, falls back to system `prefers-color-scheme`. Tailwind `darkMode: 'class'` with dual classes (`bg-white dark:bg-gray-900`). Naive UI theme switches reactively (`isDark ? darkTheme : undefined`). Color palette: dark = gray-950 bg, gray-900 cards, blue-400 accents; light = gray-50/white bg, white cards, blue-600 accents.
- Responsive containers: `max-w-3xl`/`max-w-4xl`/`max-w-6xl mx-auto`.
