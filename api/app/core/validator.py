"""
Dynamic Schema Validation Engine for Open-Todo (OTD).

Validates todo `content` against the project's `ProjectSchema.fieldsDefinition`.
Each field type has dedicated validation logic. Error messages reference the
field's `fieldDescription` to assist AI agents and human users.

Designed for extensibility: add a new `_validate_<type>` function and register
it in `_TYPE_VALIDATORS` to support additional field types.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlmodel import Session, select

from api.app.models.models import ProjectSchema


# ---------------------------------------------------------------------------
# Individual type validators
# ---------------------------------------------------------------------------
# Each returns None on success, or an error string on failure.

def _validate_text(value: Any, fd: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, str):
        return f"must be a text string"
    return None


def _validate_number(value: Any, fd: Dict[str, Any]) -> Optional[str]:
    if isinstance(value, bool):
        # bool is subclass of int in Python; reject it explicitly
        return f"must be a number (integer or float), got boolean"
    if not isinstance(value, (int, float)):
        return f"must be a number (integer or float), got {type(value).__name__}"
    return None


def _validate_date(value: Any, fd: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, str):
        return f"must be an ISO 8601 date string, got {type(value).__name__}"
    # Accept: 2024-01-15, 2024-01-15T10:30:00, 2024-01-15T10:30:00Z,
    #         2024-01-15T10:30:00+08:00
    iso_patterns = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]
    for fmt in iso_patterns:
        try:
            datetime.strptime(value, fmt)
            return None
        except ValueError:
            continue
    return f"must be a valid ISO 8601 date string (e.g. 2024-01-15 or 2024-01-15T10:30:00Z)"


def _validate_enum(value: Any, fd: Dict[str, Any]) -> Optional[str]:
    enum_values = fd.get("enumValues", [])
    if not isinstance(value, str):
        return f"must be a string matching one of: {enum_values}"
    if value not in enum_values:
        return f"must be one of {enum_values}, got '{value}'"
    return None


_URL_REGEX = re.compile(
    r"^https?://"
    r"(?:[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+)$"
)


def _validate_link(value: Any, fd: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, str):
        return f"must be a URL string, got {type(value).__name__}"
    if not _URL_REGEX.match(value):
        return f"must be a valid URL starting with http:// or https://"
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return f"must be a valid URL with scheme and host"
    return None


def _validate_assignee(value: Any, fd: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, str):
        return f"must be a string (user ID or identifier), got {type(value).__name__}"
    if not value.strip():
        return f"must not be empty"
    return None


# ---------------------------------------------------------------------------
# Type validator registry (extensible)
# ---------------------------------------------------------------------------

_TYPE_VALIDATORS = {
    "text": _validate_text,
    "number": _validate_number,
    "date": _validate_date,
    "enum": _validate_enum,
    "link": _validate_link,
    "assignee": _validate_assignee,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_content(
    session: Session,
    project_id: str,
    content: Dict[str, Any],
) -> None:
    """
    Validate ``content`` against the project's schema definition.

    Raises ``HTTPException(422)`` with detailed error messages if validation
    fails.  Does nothing if the project has no schema defined (schema-less
    mode is permitted).

    Parameters
    ----------
    session : Session
        Active database session.
    project_id : str
        The project whose schema to validate against.
    content : dict
        The todo content payload to validate.
    """
    schema = session.exec(
        select(ProjectSchema).where(ProjectSchema.project_id == project_id)
    ).first()

    # No schema defined -> skip validation (schema-less mode)
    if schema is None:
        return

    fields_def: List[Dict[str, Any]] = schema.fields_definition or []
    if not fields_def:
        return

    # Build lookup: fieldName -> definition
    field_map: Dict[str, Dict[str, Any]] = {
        fd["fieldName"]: fd for fd in fields_def
    }

    errors: List[Dict[str, str]] = []

    for key, value in content.items():
        if key not in field_map:
            # Allow extra fields not defined in schema (flexible mode)
            continue

        fd = field_map[key]
        field_type = fd.get("fieldType", "text")
        description = fd.get("fieldDescription", "")
        validator_fn = _TYPE_VALIDATORS.get(field_type)

        if validator_fn is None:
            # Unknown type in schema definition — skip
            continue

        err = validator_fn(value, fd)
        if err is not None:
            hint = f" ({description})" if description else ""
            errors.append({
                "field": key,
                "fieldType": field_type,
                "message": f"Field '{key}'{hint}: {err}.",
            })

    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "validationErrors": errors,
                "message": (
                    f"Content validation failed: {len(errors)} field(s) "
                    f"did not conform to the project schema."
                ),
            },
        )
