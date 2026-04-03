"""
Core configuration for Open-Todo (OTD).

Reads sensitive settings from environment variables (with `.env` file support
via python-dotenv). See `.env.example` for all available settings.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./otd.db")

# ---------------------------------------------------------------------------
# API metadata
# ---------------------------------------------------------------------------

API_TITLE = "Open-Todo (OTD) - AI-Native Task Infrastructure"
API_DESCRIPTION = """
Open-Todo (OTD) is an AI-native task infrastructure supporting infinite-level WBS decomposition,
dynamic data schemas, and industrial-grade transactional outbox webhook automation.

## Key Features
- **Infinite-level WBS**: Self-referencing tree structure for unlimited task decomposition.
- **Dynamic Schema Engine**: User/AI-customizable project schemas (text, number, date, enum, link, assignee).
- **Transactional Outbox**: Atomic task mutations + webhook dispatch with wildcard (`*`) field monitoring.
- **AI-Agent Friendly**: All-camelCase naming, POST-only actions, IDs in request body.
- **Zero-Config**: SQLite by default for lightweight deployment.

## Authentication
All endpoints (except `/auth/register`) require the `X-API-KEY` header with a valid `sk-otd-*` key.
"""
API_VERSION = "0.1.0"

API_KEY_PREFIX = "sk-otd-"

# ---------------------------------------------------------------------------
# SMTP Email
# ---------------------------------------------------------------------------

SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
MAIL_FROM_ADDRESS: str = os.getenv("MAIL_FROM_ADDRESS", "noreply@example.com")
MAIL_FROM_NAME: str = os.getenv("MAIL_FROM_NAME", "Open-Todo")
MAIL_ENABLED: bool = os.getenv("MAIL_ENABLED", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:9000")
WEB_BASE_URL: str = os.getenv("WEB_BASE_URL", "http://localhost:3030")
