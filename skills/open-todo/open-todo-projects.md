---
name: open-todo-projects
description: Manage projects in Open-Todo using the MCP service or REST API.
triggers:
  - list projects
  - create project
  - open-todo projects
---

# Open-Todo Project Manager

## Context

Open-Todo manages tasks within isolated Projects. Each project has a unique `projectId` which is required as a prerequisite for all schema and task (todo) operations.

## MCP Tools

If your environment has the Open-Todo MCP server connected, use the following tools:

### `list_projects`
- **Description**: Lists all projects owned by the authenticated user.
- **Arguments**: None
- **Returns**: Array of project objects containing `projectId`, `projectName`, and `projectDescription`.

### `create_project`
- **Description**: Creates a new project.
- **Arguments**:
  - `projectName` (string, required): Human-readable project name.
  - `projectDescription` (string, optional): Optional project description.
- **Returns**: The created project object.

## REST API Fallback

If MCP is not available, you can use the REST API. Ensure you have an `X-API-KEY` (prefixed `sk-otd-`).

- **List Projects**: `GET /projects`
- **Create Project**: `POST /projects/create` 
  - Body: `{ "projectName": "My Project", "projectDescription": "Optional" }`
