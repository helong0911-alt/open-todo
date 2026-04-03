---
name: open-todo-tasks
description: Manage todos (create, update, move, delete, bulk-create) in Open-Todo.
triggers:
  - manage todos
  - create task
  - update task
  - delete task
  - list tasks
  - complete task
  - move task
  - bulk create
---

# Open-Todo Task Manager

## Context

Open-Todo uses an infinite-level WBS (Work Breakdown Structure) tree. Nodes with a null `parentId` are root tasks. Every todo's `content` payload must strictly conform to the project's schema. 

## MCP Tools

If your environment has the Open-Todo MCP server connected, use the following tools:

### `list_todos`
- **Description**: Retrieves all tasks for a project.
- **Arguments**:
  - `projectId` (string, required): UUID of the project.
- **Returns**: A flat array of todos. Group by `parentId` to reconstruct the tree.

### `create_todo`
- **Description**: Creates a new task.
- **Arguments**:
  - `projectId` (string, required): UUID of the project.
  - `parentId` (string, optional): ID of the parent task (omit or send null for root tasks).
  - `content` (object, required): Dynamic field values matching the project schema.
- **Prerequisite**: Always fetch the schema via `get_project_schema` before creating to ensure `content` is valid.

### `update_todo`
- **Description**: Modifies a task's content or completion status. uses Optimistic Concurrency Control (OCC).
- **Arguments**:
  - `todoId` (string, required): Task ID to update.
  - `content` (object, optional): Partial or full updated dynamic field values.
  - `isCompleted` (boolean, optional): Set completion status.
  - `version` (integer, optional): Expected current version (for OCC).
- **Returns**: Fails with 409 Conflict if the version is outdated. Re-fetch and try again if needed.

### `move_todo`
- **Description**: Reparents a task to a new location in the tree.
- **Arguments**:
  - `todoId` (string, required): Task ID to move.
  - `newParentId` (string, required): New parent task ID (null for root).
  - `version` (integer, optional): Expected current version (for OCC).
- **Note**: Circular references are automatically blocked.

### `delete_todo`
- **Description**: Deletes a task.
- **Arguments**:
  - `todoId` (string, required): Task ID to delete.
- **Warning**: Deletion is recursive! All descendant subtasks will also be deleted.

### `bulk_create_todos`
- **Description**: Batch creates multiple tasks in a single transaction.
- **Arguments**:
  - `projectId` (string, required): UUID of the project.
  - `items` (array, required): Array of objects containing `parentId` and `content`.

## REST API Fallback

If MCP is not available, use the REST API (with `X-API-KEY` header):
- `POST /todos/list`
- `POST /todos/create`
- `POST /todos/update`
- `POST /todos/move`
- `POST /todos/delete`
- `POST /todos/bulk-create`
All IDs are passed in the JSON body, never in the URL path.
