"""
Auth API: captcha generation, email + password registration, login, logout,
and email verification.

Login returns a session token (``X-SESSION-TOKEN``) for web use.
API keys for programmatic access are managed separately via ``/keys/*``.
"""
import bcrypt
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from api.app.core.config import WEB_BASE_URL
from api.app.core.database import get_session, create_default_project_for_user
from api.app.core.captcha import generate_captcha, verify_captcha
from api.app.core.email import enqueue_verification_email
from api.app.core.auth import get_session_user
from api.app.models.models import User, SessionToken, ApiKey

router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Check a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CaptchaResponse(BaseModel):
    captchaId: str = Field(..., description="Unique ID for this captcha challenge.")
    imageBase64: str = Field(..., description="Base64-encoded PNG image data.")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address.")
    password: str = Field(..., description="User password.")
    captchaId: str = Field(..., description="Captcha challenge ID.")
    captchaCode: str = Field(..., description="User answer to the captcha.")


class LoginResponse(BaseModel):
    userId: str = Field(..., description="Authenticated user ID.")
    email: str = Field(..., description="User email address.")
    isActive: bool = Field(..., description="Whether the account is active (email verified).")
    sessionToken: str = Field(..., description="Session token for subsequent authenticated requests.")
    apiKey: Optional[str] = Field(None, description="First active API key for resource requests.")


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address.")
    password: str = Field(..., description="User password (min 6 characters).")
    captchaId: str = Field(..., description="Captcha challenge ID.")
    captchaCode: str = Field(..., description="User answer to the captcha.")


class RegisterResponse(BaseModel):
    userId: str = Field(..., description="Generated user ID.")
    email: str = Field(..., description="Registered email.")
    isActive: bool = Field(..., description="Whether the account is active (email verified).")
    message: str = Field(..., description="Instruction message for the user.")


class VerifyRequest(BaseModel):
    token: str = Field(..., description="Email verification token.")


class VerifyResponse(BaseModel):
    userId: str = Field(..., description="Verified user ID.")
    email: str = Field(..., description="Verified email.")
    isActive: bool = Field(..., description="Account active status (true after verification).")


class MeResponse(BaseModel):
    userId: str = Field(..., description="Authenticated user ID.")
    email: str = Field(..., description="User email address.")
    isActive: bool = Field(..., description="Whether the account is active.")


class LogoutRequest(BaseModel):
    sessionToken: str = Field(..., description="Session token to invalidate.")


class LogoutResponse(BaseModel):
    detail: str = Field(..., description="Logout result message.")


class ChangePasswordRequest(BaseModel):
    oldPassword: str = Field(..., description="Current password.")
    newPassword: str = Field(..., description="New password (min 6 characters).")


class ChangePasswordResponse(BaseModel):
    success: bool = Field(..., description="True if the password was changed successfully.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/captcha",
    response_model=CaptchaResponse,
    summary="Generate a captcha image",
    description=(
        "Returns a new captcha challenge consisting of a ``captchaId`` and "
        "a base64-encoded PNG image. The captcha expires after 5 minutes and "
        "can only be verified once (single use)."
    ),
)
def get_captcha(session: Session = Depends(get_session)):
    captcha_id, image_b64 = generate_captcha(session)
    return CaptchaResponse(captchaId=captcha_id, imageBase64=image_b64)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login with email, password, and captcha",
    description=(
        "Validates the email + password credentials and captcha answer. "
        "On success, creates a session token and returns it. The client "
        "should store the session token and send it as ``X-SESSION-TOKEN`` "
        "header on subsequent requests."
    ),
)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    # Validate captcha first
    if not verify_captcha(session, body.captchaId, body.captchaCode):
        raise HTTPException(status_code=422, detail="Invalid or expired captcha.")

    # Look up user by email
    user = session.exec(
        select(User).where(User.email == body.email)
    ).first()

    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Verify password
    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Reject inactive (unverified) accounts
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account not activated. Please verify your email first.",
        )

    # Create session token
    token = SessionToken(user_id=user.user_id)
    session.add(token)
    session.commit()
    session.refresh(token)

    # Look up the user's System API key first, fall back to any enabled key
    api_key_row = session.exec(
        select(ApiKey).where(
            ApiKey.user_id == user.user_id,
            ApiKey.is_system == True,    # noqa: E712
            ApiKey.is_enabled == True,   # noqa: E712
            ApiKey.is_deleted == False,  # noqa: E712
        )
    ).first()
    if api_key_row is None:
        api_key_row = session.exec(
            select(ApiKey).where(
                ApiKey.user_id == user.user_id,
                ApiKey.is_enabled == True,   # noqa: E712
                ApiKey.is_deleted == False,  # noqa: E712
            )
        ).first()

    return LoginResponse(
        userId=user.user_id,
        email=user.email,
        isActive=user.is_active,
        sessionToken=token.token_value,
        apiKey=api_key_row.key_value if api_key_row else None,
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    summary="Register a new user with email and password",
    description=(
        "Creates a new user account with the given email and password after "
        "validating the captcha. A verification email is enqueued for delivery; "
        "the account remains inactive until the user verifies their email via "
        "``POST /auth/verify``."
    ),
)
def register(body: RegisterRequest, session: Session = Depends(get_session)):
    # Validate captcha first
    if not verify_captcha(session, body.captchaId, body.captchaCode):
        raise HTTPException(status_code=422, detail="Invalid or expired captcha.")

    # Validate password length
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")

    # Check duplicate email
    existing = session.exec(
        select(User).where(User.email == body.email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Create user with hashed password
    user = User(
        email=body.email,
        password_hash=_hash_password(body.password),
    )
    session.add(user)
    session.flush()

    # Enqueue verification email (within the same transaction)
    verification_url = f"{WEB_BASE_URL}/verify?token={user.verification_token}"
    enqueue_verification_email(
        session=session,
        user_id=user.user_id,
        to_address=user.email,
        verification_url=verification_url,
    )

    session.commit()
    session.refresh(user)

    return RegisterResponse(
        userId=user.user_id,
        email=user.email,
        isActive=user.is_active,
        message="Registration successful. Please check your email to verify your account.",
    )


@router.get(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify email address",
    description=(
        "Activates a user account by validating the verification token "
        "received via email. After verification, ``isActive`` becomes ``true`` "
        "and the token is cleared."
    ),
)
def verify_email(
    token: str = Query(..., description="Email verification token."),
    session: Session = Depends(get_session),
):
    if not token:
        raise HTTPException(status_code=422, detail="Verification token is required.")

    user = session.exec(
        select(User).where(User.verification_token == token)
    ).first()

    if user is None:
        raise HTTPException(status_code=404, detail="Invalid or expired verification token.")

    if user.is_active:
        raise HTTPException(status_code=409, detail="Account already verified.")

    user.is_active = True
    user.verification_token = None
    session.add(user)

    # Create default project, schema, and API key for the newly activated user
    create_default_project_for_user(session, user.user_id, create_api_key=True)

    session.commit()
    session.refresh(user)

    return VerifyResponse(
        userId=user.user_id,
        email=user.email,
        isActive=user.is_active,
    )


@router.post(
    "/me",
    response_model=MeResponse,
    summary="Get current user from session token",
    description=(
        "Validates the ``X-SESSION-TOKEN`` header and returns the "
        "authenticated user's basic profile.  Used by the web client on "
        "page load to verify the stored session token is still valid."
    ),
)
def me(user: User = Depends(get_session_user)):
    return MeResponse(
        userId=user.user_id,
        email=user.email,
        isActive=user.is_active,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Logout (invalidate session token)",
    description=(
        "Deletes the specified session token, effectively logging the user "
        "out of the web session."
    ),
)
def logout(body: LogoutRequest, session: Session = Depends(get_session)):
    token_row = session.exec(
        select(SessionToken).where(SessionToken.token_value == body.sessionToken)
    ).first()

    if token_row is None:
        # Token already gone or never existed — still return success
        return LogoutResponse(detail="Logged out.")

    session.delete(token_row)
    session.commit()

    return LogoutResponse(detail="Logged out.")


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    summary="Change user password",
    description="Updates the authenticated user's password.",
)
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_session_user),
    session: Session = Depends(get_session),
):
    # Verify current password
    if not _verify_password(body.oldPassword, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password.")

    # Validate new password length
    if len(body.newPassword) < 6:
        raise HTTPException(status_code=422, detail="New password must be at least 6 characters.")

    # Hash and update
    user.password_hash = _hash_password(body.newPassword)
    session.add(user)
    session.commit()

    return ChangePasswordResponse(success=True)
