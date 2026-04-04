"""
Open-Todo (OTD) - FastAPI application entry point.

Registers all API routers and starts/stops the async outbox worker
and email worker within the application lifespan.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.app.core.config import API_TITLE, API_DESCRIPTION, API_VERSION
from api.app.core.database import create_db_and_tables
from api.app.api import auth, projects, schemas, todos, webhooks
from api.app.api import automation, mcp, notifications, api_keys, members
from api.app.worker.outbox import start_outbox_worker, stop_outbox_worker
from api.app.worker.email_worker import start_email_worker, stop_email_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    await start_outbox_worker()
    await start_email_worker()
    yield
    await stop_email_worker()
    await stop_outbox_worker()


app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(schemas.router)
app.include_router(todos.router)
app.include_router(webhooks.router)
app.include_router(automation.router)
app.include_router(mcp.router)
app.include_router(notifications.router)
app.include_router(members.router)
app.include_router(api_keys.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"], summary="Health check")
def health():
    return {"status": "ok", "service": "Open-Todo (OTD)", "version": API_VERSION}
