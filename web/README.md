# Open-Todo Web

> [中文文档](./README.zh-CN.md) | [Back to project root](../README.md)

Vue 3 web application for Open-Todo -- a dark-mode WBS tree-table interface with dynamic field rendering, schema editing, captcha-based login/registration, API key management, email verification, and webhook automation dashboard.

---

## Requirements

- Node.js 20+
- npm

## Installation

```bash
npm install
```

## Running

### Development Server

```bash
npm run dev
```

The dev server starts at `http://localhost:3030`. API requests to `/api/*` are proxied to `http://localhost:9000` (the API service must be running).

### Production Build

```bash
npm run build
```

This runs `vue-tsc` for type checking, then `vite build` for production bundling. Output goes to `dist/`.

### Type Check Only

```bash
npx vue-tsc -b
```

### Docker

From the project root:

```bash
docker compose up --build web
```

The `web` service builds the Vue app, then serves it via Nginx on port 3030. Nginx proxies `/api/*` requests to the `api` service.

---

## Module Structure

```
web/
├── src/
│   ├── main.ts                    # Vue app bootstrap (Pinia, Naive UI, Router)
│   ├── App.vue                    # Root component (auth overlay + navigation shell)
│   ├── style.css                  # Tailwind directives + base styles
│   ├── api/
│   │   └── index.ts               # Axios client, all API functions, X-API-KEY + X-SESSION-TOKEN interceptors
│   ├── components/
│   │   ├── TodoTreeRow.vue        # Single WBS tree-table row (expand, indent, actions)
│   │   └── DynamicFieldRenderer.vue  # Renders field values by type (tag, link, avatar, etc.)
│   ├── composables/
│   │   ├── useProject.ts          # Shared project + schema state (singleton ref pattern)
│   │   └── useTodos.ts            # Shared todo tree state + CRUD operations
│   ├── router/
│   │   └── index.ts               # Vue Router (5 routes, lazy-loaded views)
│   ├── types/
│   │   └── index.ts               # TypeScript interfaces mirroring API responses
│   ├── utils/
│   │   └── treeBuilder.ts         # Flat list <-> nested tree conversion
│   └── views/
│       ├── ProjectListView.vue    # Project listing + create form
│       ├── ProjectDetailView.vue  # WBS tree-table + schema editor modal + todo CRUD
│       ├── AutomationView.vue     # Webhook rules + delivery audit log + retry
│       ├── KeyManagementView.vue  # API key CRUD (create, rename, enable/disable, delete)
│       ├── UserCenterView.vue     # User profile, change password
│       └── EmailVerifyView.vue    # Email verification page (public, no login required)
├── index.html
├── vite.config.ts                 # Vite config (port 3030, /api proxy to :9000)
├── tsconfig.json                  # TypeScript strict mode, @/* path alias
├── tailwind.config.js             # Tailwind with class-based dark mode
├── postcss.config.js              # PostCSS with Tailwind + Autoprefixer
├── Dockerfile                     # Multi-stage: Node build + Nginx serve
└── package.json
```

## Routes

| Path | Name | View | Auth | Description |
|------|------|------|------|-------------|
| `/` | `projects` | `ProjectListView` | Session | Browse projects, create new project |
| `/project/:id` | `project-detail` | `ProjectDetailView` | Session | WBS tree-table, schema editor, todo CRUD |
| `/project/:id/automation` | `automation` | `AutomationView` | Session | Webhook rules, delivery logs, retry |
| `/keys` | `key-management` | `KeyManagementView` | Session | API key create, rename, enable/disable, delete |
| `/user-center` | `user-center` | `UserCenterView` | Session | Change user password |
| `/verify` | `email-verify` | `EmailVerifyView` | Public | Email verification via `?token=xxx` |

## Key Architecture

- **Composition API**: All components use `<script setup lang="ts">`.
- **Singleton state**: Composables use module-scope `ref()` for shared state (not Pinia stores, despite Pinia being installed).
- **Dual authentication**: The web client uses session tokens (`X-SESSION-TOKEN` header, stored in `localStorage`) for all API calls. API keys (`X-API-KEY` header) are also attached for programmatic endpoints. Both headers are injected via Axios request interceptor.
- **POST-only**: All mutations go through POST requests with camelCase JSON bodies.
- **Dynamic rendering**: `DynamicFieldRenderer` auto-selects UI for each field type (enum as `NTag`, link as hyperlink, assignee as `NAvatar`, date as formatted string, number in monospace).
- **Tree building**: Flat todo list from API is converted to nested tree client-side via `treeBuilder.ts`. Expanded state is preserved across data refreshes.
- **Polling**: `ProjectDetailView` auto-refreshes todo data every 10 seconds.
- **Dark mode**: Default dark theme (`<html class="dark">`), gray-950 background, gray-900 cards, blue-400 accents. Naive UI `darkTheme` applied globally.
- **Captcha**: Login and registration both require solving an image captcha before submission.

## Views Detail

### ProjectListView
Browse all user projects. Collapsible create form for new projects. Click to navigate into WBS tree. Shows project name, description, automation link, and truncated project ID.

### ProjectDetailView
Full WBS tree-table with dynamic column headers from schema fields. Supports expand/collapse, todo CRUD (create root/child, edit, delete with confirmation), completion toggle, schema editor modal with field type dropdowns and enum value management. 10-second auto-polling.

### AutomationView
Webhook rule management: create rules with event type, target field, and webhook URL. Audit log timeline with status tags, retry counts, error messages, and one-click retry for failed deliveries.

### KeyManagementView
Create, rename, enable/disable, and soft-delete API keys. Full key value shown only once at creation (with copy button and warning). Masked values displayed in list. First created key is auto-stored in localStorage for API access.

### UserCenterView
User profile page allowing the authenticated user to change their password securely.

### EmailVerifyView
Public page (no login required). Reads `?token=xxx` from URL, calls `GET /auth/verify`, shows success (green checkmark + email) or error state with "Go to Login" button.

## Dependencies

### Runtime
- `vue@^3.5.0`
- `vue-router@^4.4.0`
- `pinia@^2.2.0`
- `naive-ui@^2.39.0`
- `axios@^1.7.0`

### Dev
- `vite@^6.0.0`
- `vue-tsc@^2.1.0`
- `typescript@~5.6.0`
- `tailwindcss@^3.4.0`
- `@vitejs/plugin-vue@^5.1.0`
- `postcss@^8.4.47`
- `autoprefixer@^10.4.20`

---

> [Back to project root](../README.md)
