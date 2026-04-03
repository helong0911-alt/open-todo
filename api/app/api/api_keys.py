"""
API Key management routes.

All endpoints require session authentication (``X-SESSION-TOKEN`` header).
Users can create, list, rename, enable/disable, and soft-delete their API keys.
"""
from typing import Optional, List

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.core.auth import get_session_user
from api.app.models.models import User, ApiKey, _generate_api_key

router = APIRouter(prefix="/keys", tags=["API Keys"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class KeyCreateRequest(BaseModel):
    keyName: str = Field(default="Default", description="Human-readable label for the key.")


class KeyCreateResponse(BaseModel):
    keyId: str = Field(..., description="Unique key identifier.")
    keyName: str = Field(..., description="Human-readable label.")
    keyValue: str = Field(..., description="Full API key value (only shown once).")
    isEnabled: bool = Field(..., description="Whether the key is enabled.")
    createdAt: str = Field(..., description="Key creation timestamp.")


class KeySummary(BaseModel):
    keyId: str = Field(..., description="Unique key identifier.")
    keyName: str = Field(..., description="Human-readable label.")
    keyValueMasked: str = Field(..., description="Masked API key (first 12 + last 4 chars).")
    isEnabled: bool = Field(..., description="Whether the key is enabled.")
    isSystem: bool = Field(False, description="Whether this is a system key.")
    createdAt: str = Field(..., description="Key creation timestamp.")


class KeyListResponse(BaseModel):
    keys: List[KeySummary] = Field(..., description="List of API keys owned by the user.")


class KeyUpdateRequest(BaseModel):
    keyId: str = Field(..., description="Key to update.")
    keyName: Optional[str] = Field(None, description="New label (if changing).")
    isEnabled: Optional[bool] = Field(None, description="New enabled state (if changing).")


class KeyUpdateResponse(BaseModel):
    keyId: str = Field(..., description="Updated key identifier.")
    keyName: str = Field(..., description="Current label.")
    isEnabled: bool = Field(..., description="Current enabled state.")


class KeyDeleteRequest(BaseModel):
    keyId: str = Field(..., description="Key to soft-delete.")


class KeyDeleteResponse(BaseModel):
    detail: str = Field(..., description="Deletion result message.")
    keyId: str = Field(..., description="Deleted key identifier.")


class KeyRefreshRequest(BaseModel):
    keyId: str = Field(..., description="Key to regenerate.")


class KeyRefreshResponse(BaseModel):
    keyId: str = Field(..., description="Key identifier.")
    keyName: str = Field(..., description="Key label.")
    keyValue: str = Field(..., description="New full API key value (only shown once).")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_key(key_value: str) -> str:
    """Mask an API key: show first 12 and last 4 characters."""
    if len(key_value) <= 16:
        return key_value[:4] + "****"
    return key_value[:12] + "..." + key_value[-4:]


def _verify_key_ownership(
    session: Session, key_id: str, user: User
) -> ApiKey:
    """Look up an ApiKey by ID and verify ownership. Raises 404 or 403."""
    api_key = session.get(ApiKey, key_id)
    if api_key is None or api_key.is_deleted:
        raise HTTPException(status_code=404, detail="API key not found.")
    if api_key.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this API key.")
    return api_key


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/create",
    response_model=KeyCreateResponse,
    summary="Create a new API key",
    description=(
        "Creates a new API key for the authenticated user. The full key value "
        "is returned **only once** in this response — subsequent list calls "
        "return a masked version."
    ),
)
def create_key(
    body: KeyCreateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_session_user),
):
    api_key = ApiKey(
        user_id=user.user_id,
        key_name=body.keyName,
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)

    return KeyCreateResponse(
        keyId=api_key.key_id,
        keyName=api_key.key_name,
        keyValue=api_key.key_value,
        isEnabled=api_key.is_enabled,
        createdAt=api_key.created_at.isoformat(),
    )


@router.post(
    "/list",
    response_model=KeyListResponse,
    summary="List all API keys",
    description=(
        "Returns all non-deleted API keys owned by the authenticated user. "
        "Key values are masked for security."
    ),
)
def list_keys(
    session: Session = Depends(get_session),
    user: User = Depends(get_session_user),
):
    keys = session.exec(
        select(ApiKey).where(
            ApiKey.user_id == user.user_id,
            ApiKey.is_deleted == False,  # noqa: E712
        )
    ).all()

    return KeyListResponse(
        keys=[
            KeySummary(
                keyId=k.key_id,
                keyName=k.key_name,
                keyValueMasked=_mask_key(k.key_value),
                isEnabled=k.is_enabled,
                isSystem=k.is_system,
                createdAt=k.created_at.isoformat(),
            )
            for k in keys
        ]
    )


@router.post(
    "/update",
    response_model=KeyUpdateResponse,
    summary="Update an API key",
    description=(
        "Rename or enable/disable an existing API key. At least one of "
        "``keyName`` or ``isEnabled`` must be provided."
    ),
)
def update_key(
    body: KeyUpdateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_session_user),
):
    api_key = _verify_key_ownership(session, body.keyId, user)

    # System keys cannot be renamed or disabled
    if api_key.is_system and body.keyName is not None:
        raise HTTPException(status_code=403, detail="System key cannot be renamed.")
    if api_key.is_system and body.isEnabled is not None and not body.isEnabled:
        raise HTTPException(status_code=403, detail="System key cannot be disabled.")

    if body.keyName is not None:
        api_key.key_name = body.keyName
    if body.isEnabled is not None:
        api_key.is_enabled = body.isEnabled

    session.add(api_key)
    session.commit()
    session.refresh(api_key)

    return KeyUpdateResponse(
        keyId=api_key.key_id,
        keyName=api_key.key_name,
        isEnabled=api_key.is_enabled,
    )


@router.post(
    "/delete",
    response_model=KeyDeleteResponse,
    summary="Soft-delete an API key",
    description=(
        "Marks the specified API key as deleted. The key can no longer be "
        "used for authentication and will not appear in list results."
    ),
)
def delete_key(
    body: KeyDeleteRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_session_user),
):
    api_key = _verify_key_ownership(session, body.keyId, user)

    if api_key.is_system:
        raise HTTPException(status_code=403, detail="System key cannot be deleted.")

    api_key.is_deleted = True
    api_key.is_enabled = False
    session.add(api_key)
    session.commit()

    return KeyDeleteResponse(
        detail="API key deleted.",
        keyId=api_key.key_id,
    )


@router.post(
    "/refresh",
    response_model=KeyRefreshResponse,
    summary="Regenerate an API key value",
    description=(
        "Generates a new random value for the specified API key. The old "
        "value is immediately invalidated. The new full key value is returned "
        "**only once** in this response."
    ),
)
def refresh_key(
    body: KeyRefreshRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_session_user),
):
    api_key = _verify_key_ownership(session, body.keyId, user)

    api_key.key_value = _generate_api_key()
    session.add(api_key)
    session.commit()
    session.refresh(api_key)

    return KeyRefreshResponse(
        keyId=api_key.key_id,
        keyName=api_key.key_name,
        keyValue=api_key.key_value,
    )
