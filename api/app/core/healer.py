"""
JIT (Just-In-Time) Content Healer for Open-Todo (OTD).

When a project schema evolves (new fields added), existing todos may lack
the newly-defined fields.  The healer fills in type-appropriate defaults
for any missing fields so that downstream consumers (UI, AI agents) always
see a complete record.

Default values by field type:
    text     -> ""
    number   -> 0
    date     -> ""
    enum     -> first enumValues entry, or ""
    link     -> ""
    assignee -> ""

The healer is called:
  - On ``POST /todos/list``: heal in-memory only (no DB write-back).
  - On ``POST /todos/update``: heal then persist (write-back strategy).
"""
from typing import Any, Dict, List, Tuple

from sqlmodel import Session, select

from api.app.models.models import ProjectSchema


# ---------------------------------------------------------------------------
# Type-specific default factories
# ---------------------------------------------------------------------------

_TYPE_DEFAULTS = {
    "text": lambda fd: "",
    "number": lambda fd: 0,
    "date": lambda fd: "",
    "enum": lambda fd: (fd.get("enumValues") or [""])[0],
    "link": lambda fd: "",
    "assignee": lambda fd: "",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def heal_content(
    content: Dict[str, Any],
    fields_definition: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], bool]:
    """
    Fill missing fields in ``content`` with type-appropriate defaults.

    Parameters
    ----------
    content : dict
        The todo's current content dict (may be missing fields).
    fields_definition : list[dict]
        The project schema's ``fieldsDefinition`` array.

    Returns
    -------
    (healed_content, needs_healing) : tuple
        ``healed_content`` is a new dict with defaults filled in.
        ``needs_healing`` is True when at least one field was added.
    """
    healed = dict(content)
    needs_healing = False

    for fd in fields_definition:
        field_name = fd.get("fieldName")
        if field_name is None:
            continue
        if field_name not in healed:
            field_type = fd.get("fieldType", "text")
            default_fn = _TYPE_DEFAULTS.get(field_type, lambda _fd: "")
            healed[field_name] = default_fn(fd)
            needs_healing = True

    return healed, needs_healing


def get_schema_for_project(
    session: Session,
    project_id: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Fetch the current schema definition and version for a project.

    Returns
    -------
    (fields_definition, schema_version) : tuple
        Empty list and version 0 if no schema exists.
    """
    schema = session.exec(
        select(ProjectSchema).where(ProjectSchema.project_id == project_id)
    ).first()

    if schema is None:
        return [], 0

    return schema.fields_definition or [], schema.schema_version or 0
