---
name: open-todo-schemas
description: Design and update dynamic field schemas for Open-Todo projects.
triggers:
  - design schema
  - update schema
  - project schema
  - field definition
---

# Open-Todo Schema Designer

## Context

Each Open-Todo project has a dynamic field schema that defines which fields appear in todos. The schema controls validation: when a todo is created or updated, its `content` is validated against the active schema. Schemas are fully mutable at runtime.

### JIT Healing (Schema Evolution)

When you update a schema (e.g., adding a new field), existing todos are NOT migrated. Instead, Open-Todo uses **JIT Healing**:
- **On read**: Missing fields are auto-filled with type-appropriate defaults in-memory.
- **On write**: Missing fields are healed before merging user changes.

| Field Type | Value Format | Default Value |
|------------|--------------|---------------|
| `text` | `string` | `""` |
| `number` | `int` or `float` | `0` |
| `date` | ISO 8601 string | `""` |
| `enum` | `string` (must match enumValues) | first `enumValues` entry |
| `link` | URL `string` | `""` |
| `assignee` | `string` | `""` |

## MCP Tools

If your environment has the Open-Todo MCP server connected, use the following tools:

### `get_project_schema`
- **Description**: Retrieves the current field schema for a project.
- **Arguments**:
  - `projectId` (string, required): UUID of the project.
- **Returns**: Contains `schemaVersion` and `fieldsDefinition` array.

### `update_project_schema`
- **Description**: Replaces the entire field schema for a project.
- **Arguments**:
  - `projectId` (string, required): UUID of the project.
  - `fieldsDefinition` (array, required): Array of field descriptors.
    - Each descriptor needs `fieldName`, `fieldType`, `fieldDescription`, and (if enum) `enumValues`.
- **Warning**: This is a FULL replacement. Always include ALL fields you want to keep.

## REST API Fallback

If MCP is not available:
- **Get Schema**: `POST /projects/schema/get` (Body: `{ "projectId": "<id>" }`)
- **Update Schema**: `POST /projects/schema/update` (Body: `{ "projectId": "<id>", "fieldsDefinition": [...] }`)
