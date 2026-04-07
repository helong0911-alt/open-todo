---
name: open-todo-projects
description: Manage projects in Open-Todo using the MCP service or REST API.
triggers:
  - list projects
  - create project
  - update project
  - open-todo projects
---

# Open-Todo Project Manager

## Context

Open-Todo manages tasks within isolated Projects. Each project has a unique `projectId` which is required as a prerequisite for all schema and task (todo) operations. Projects can optionally store a local filesystem directory path (`projectDirectory`) and a Git repository URL (`gitUrl`).

## MCP Tools

If your environment has the Open-Todo MCP server connected, use the following tools:

### `list_projects`
- **Description**: Lists all projects owned by the authenticated user.
- **Arguments**: None
- **Returns**: Array of project objects containing `projectId`, `projectName`, `projectDescription`, `projectDirectory`, and `gitUrl`.

### `create_project`
- **Description**: Creates a new project.
- **Arguments**:
  - `projectName` (string, required): Human-readable project name.
  - `projectDescription` (string, optional): Optional project description.
  - `projectDirectory` (string, optional): Local filesystem directory path for the project.
  - `gitUrl` (string, optional): Git repository URL for the project.
- **Returns**: The created project object.

### `update_project`
- **Description**: Updates project metadata. Only provided fields are updated; omitted fields remain unchanged.
- **Arguments**:
  - `projectId` (string, required): UUID of the project to update.
  - `projectName` (string, optional): Updated project name.
  - `projectDescription` (string, optional): Updated project description.
  - `projectDirectory` (string, optional): Updated local filesystem directory path.
  - `gitUrl` (string, optional): Updated Git repository URL.
- **Returns**: The updated project object.

## REST API Fallback

If MCP is not available, you can use the REST API. Ensure you have an `X-API-KEY` (prefixed `sk-otd-`).

- **List Projects**: `GET /projects`
- **Create Project**: `POST /projects/create` 
  - Body: `{ "projectName": "My Project", "projectDescription": "Optional", "projectDirectory": "/path/to/project", "gitUrl": "https://github.com/user/repo.git" }`
- **Update Project**: `POST /projects/update`
  - Body: `{ "projectId": "uuid", "projectDirectory": "/new/path", "gitUrl": "https://github.com/user/repo.git" }`
