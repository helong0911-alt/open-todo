# Open-Todo Skills

This directory provides standardized skills for AI agents (Cursor, Windsurf, OpenCode, Claude Desktop, etc.) to securely interact with the Open-Todo (OTD) platform. These skills leverage the native **MCP (Model Context Protocol)** toolset exposed by the `api` service.

| Skill Name | File | Triggers | Description |
|------------|------|----------|-------------|
| **Open-Todo Project Manager** | [open-todo-projects.md](./open-todo-projects.md) | `list projects`, `create project`, `open-todo projects` | List existing projects or create new isolated projects. |
| **Open-Todo Schema Designer** | [open-todo-schemas.md](./open-todo-schemas.md) | `design schema`, `update schema`, `project schema`, `field definition` | Design, fetch, and update the dynamic validation schema and fields for a specific project. |
| **Open-Todo Task Manager** | [open-todo-tasks.md](./open-todo-tasks.md) | `manage todos`, `create task`, `update task`, `delete task`, `list tasks`, `complete task`, `move task`, `bulk create` | Perform complex task scheduling: create, update (OCC), move (reparent/prevent circular-refs), and recursive delete. |

## Quick Setup for AI Agents

To equip your AI agent with these skills:
1. Ensure the Open-Todo backend (`api`) is running (e.g., `docker compose up api`).
2. Add the Open-Todo MCP server to your agent's configuration.
3. Import the `.md` files in this directory into your agent's knowledge base or prompt rules.

> **Why 3 separate skills?**
> Breaking down the domains (Projects, Schemas, Tasks) allows the AI context window to remain focused on the specific operation you are asking for, reducing token usage and improving the reliability of the generated MCP arguments.
