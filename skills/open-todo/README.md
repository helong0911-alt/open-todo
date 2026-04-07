# Open-Todo Skill Directory

This directory contains reusable AI skill definition files for Open-Todo (OTD).

Each `.md` file is a self-contained skill that can be loaded by an AI coding agent (such as Cursor, Windsurf, Claude Desktop, etc.) to perform structured operations against the Open-Todo API using the **MCP Tools** provided by the server.

## How to Use

1. Ensure your AI agent is connected to the Open-Todo MCP server (e.g. via `POST /mcp` Streamable HTTP or standard stdio wrappers).
2. Place these `.md` skill files in your agent's context/rules directory.
3. When the agent encounters a matching task, it will follow the instructions to select the correct MCP tools.

## Included Skills

| File | Name | Description |
|------|------|-------------|
| `open-todo-projects.md` | Open-Todo Project Manager | Create, list, and update projects |
| `open-todo-schemas.md` | Open-Todo Schema Designer | Design and update project field schemas |
| `open-todo-tasks.md` | Open-Todo Task Manager | Create, update, delete, and query todos |

> **Note**: Webhook rules, delivery logs, and email notification rules are managed exclusively through the web dashboard.
