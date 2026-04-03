"""
Authentication dependencies for Open-Todo (OTD).

Two auth strategies:
- ``get_current_user``: validates ``X-API-KEY`` header against the ``api_key``
  table.  Used by all resource routes (projects, todos, schemas, webhooks,
  automation, mcp, notifications).
- ``get_session_user``: validates ``X-SESSION-TOKEN`` header against the
  ``session_token`` table.  Used by web-only routes (key management,
  user profile, etc.).
"""
from typing import Optional

from fastapi import Header, HTTPException, Depends
from sqlmodel import Session, select

from api.app.core.database import get_session
from api.app.models.models import User, ApiKey, SessionToken


# ---------------------------------------------------------------------------
# API-key auth (programmatic access)
# ---------------------------------------------------------------------------

async def get_current_user(
    x_api_key: str = Header(
        ...,
        alias="X-API-KEY",
        description="API key with `sk-otd-` prefix.",
    ),
    session: Session = Depends(get_session),
) -> User:
    """
    Resolve the current user from the ``X-API-KEY`` header by looking up
    the ``api_key`` table.  The key must exist, be enabled, and not be
    soft-deleted.  Raises 401 if the key is missing, malformed, disabled,
    or does not exist.
    """
    if not x_api_key or not x_api_key.startswith("sk-otd-"):
        raise HTTPException(status_code=401, detail="Invalid API key format.")

    api_key_row = session.exec(
        select(ApiKey).where(
            ApiKey.key_value == x_api_key,
            ApiKey.is_enabled == True,   # noqa: E712
            ApiKey.is_deleted == False,  # noqa: E712
        )
    ).first()

    if api_key_row is None:
        raise HTTPException(status_code=401, detail="Invalid or disabled API key.")

    user = session.get(User, api_key_row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="API key owner not found.")

    return user


# ---------------------------------------------------------------------------
# Session-token auth (web login sessions)
# ---------------------------------------------------------------------------

async def get_session_user(
    x_session_token: str = Header(
        ...,
        alias="X-SESSION-TOKEN",
        description="Session token issued on login (prefix `ses-`).",
    ),
    session: Session = Depends(get_session),
) -> User:
    """
    Resolve the current user from the ``X-SESSION-TOKEN`` header by looking
    up the ``session_token`` table.  Raises 401 if the token is missing,
    malformed, or does not exist.
    """
    if not x_session_token or not x_session_token.startswith("ses-"):
        raise HTTPException(status_code=401, detail="Invalid session token format.")

    token_row = session.exec(
        select(SessionToken).where(SessionToken.token_value == x_session_token)
    ).first()

    if token_row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")

    user = session.get(User, token_row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session token owner not found.")

    return user
