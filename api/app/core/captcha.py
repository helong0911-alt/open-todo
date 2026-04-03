"""
Captcha generation and database-backed verification for Open-Todo (OTD).

Uses the ``captcha`` library to render image captchas. Each captcha is
stored in the ``captcha_challenge`` table so that process restarts
(e.g. ``uvicorn --reload``) do not invalidate pending challenges.
Entries expire after ``CAPTCHA_TTL_SECONDS``.
"""
import base64
import secrets
from datetime import datetime, timezone, timedelta
from io import BytesIO

from captcha.image import ImageCaptcha
from sqlmodel import Session, select

from api.app.models.models import CaptchaChallenge

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CAPTCHA_TTL_SECONDS: int = 300
"""How long a captcha remains valid (5 minutes)."""

CAPTCHA_LENGTH: int = 4
"""Number of characters in each captcha."""

CAPTCHA_CHARS: str = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
"""Character set (excludes I/O to avoid confusion with 1/0)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_expired(session: Session) -> None:
    """Delete expired captcha challenges."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=CAPTCHA_TTL_SECONDS)
    expired = session.exec(
        select(CaptchaChallenge).where(CaptchaChallenge.created_at < cutoff)
    ).all()
    for row in expired:
        session.delete(row)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_captcha(session: Session) -> tuple[str, str]:
    """
    Generate a new captcha image and persist the challenge in the database.

    Returns ``(captcha_id, base64_image_data)`` where the image is a
    PNG encoded as a base64 string (no ``data:`` prefix).
    """
    answer = "".join(secrets.choice(CAPTCHA_CHARS) for _ in range(CAPTCHA_LENGTH))
    captcha_id = secrets.token_urlsafe(16)

    image_gen = ImageCaptcha(width=160, height=60)
    buf = BytesIO()
    image_gen.write(answer, buf)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # Clean up expired entries opportunistically
    _cleanup_expired(session)

    challenge = CaptchaChallenge(
        captcha_id=captcha_id,
        answer=answer.upper(),
    )
    session.add(challenge)
    session.commit()

    return captcha_id, b64


def verify_captcha(session: Session, captcha_id: str, user_input: str) -> bool:
    """
    Verify a captcha answer.  Each captcha can only be verified once
    (consumed on check, regardless of result).

    Returns ``True`` if the answer matches (case-insensitive).
    """
    challenge = session.exec(
        select(CaptchaChallenge).where(CaptchaChallenge.captcha_id == captcha_id)
    ).first()

    if challenge is None:
        return False

    # Always delete (single-use)
    session.delete(challenge)
    session.commit()

    # Check expiry (SQLite returns naive datetimes, so compare without tz)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created = challenge.created_at.replace(tzinfo=None) if challenge.created_at.tzinfo else challenge.created_at
    elapsed = (now - created).total_seconds()
    if elapsed > CAPTCHA_TTL_SECONDS:
        return False

    return user_input.strip().upper() == challenge.answer
