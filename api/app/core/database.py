"""
Database engine and session management.
Ensures PRAGMA foreign_keys=ON for SQLite.
Seeds a default admin user, project, schema, and API key on first run.
"""
import logging

import bcrypt
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import event

from api.app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """Enable foreign key enforcement on every new SQLite connection."""
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ---------------------------------------------------------------------------
# Default data seeding
# ---------------------------------------------------------------------------

DEFAULT_ADMIN_EMAIL = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


def _hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_default_project_for_user(session: Session, user_id: str, create_api_key: bool = False):
    """
    Create a default project with schema for the given user.
    Optionally creates a default API key when ``create_api_key`` is True
    (used only for the initial admin seed).
    The caller is responsible for committing the transaction.
    """
    from api.app.models.models import Project, ProjectSchema, ApiKey

    project = Project(
        user_id=user_id,
        project_name="MyProject",
        project_description="Default project created on initialization.",
    )
    session.add(project)
    session.flush()

    schema = ProjectSchema(
        project_id=project.project_id,
        fields_definition=[
            {
                "fieldName": "待办事项",
                "fieldType": "text",
                "fieldDescription": "待办事项内容",
            },
            {
                "fieldName": "状态",
                "fieldType": "enum",
                "fieldDescription": "任务状态",
                "enumValues": ["待处理", "处理中", "已完成"],
            },
            {
                "fieldName": "优先级",
                "fieldType": "enum",
                "fieldDescription": "任务优先级",
                "enumValues": ["高", "中", "低"],
            },
            {
                "fieldName": "创建时间",
                "fieldType": "date",
                "fieldDescription": "任务创建时间",
            },
        ],
    )
    session.add(schema)

    api_key = None
    if create_api_key:
        api_key = ApiKey(
            user_id=user_id,
            key_name="System",
            is_enabled=True,
            is_system=True,
        )
        session.add(api_key)

    return project, api_key


def _seed_default_data():
    """
    Seed the database with a default admin user, project, schema, and API key
    if the admin user does not already exist.  All default data is created in
    an active/usable state.
    """
    from api.app.models.models import User

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
        ).first()
        if existing:
            logger.info("Default admin user already exists, skipping seed.")
            return

        # Create default admin user (active, no verification needed)
        admin_user = User(
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=_hash_password(DEFAULT_ADMIN_PASSWORD),
            is_active=True,
            verification_token=None,
        )
        session.add(admin_user)
        session.flush()

        # Create default project, schema, and API key
        project, api_key = create_default_project_for_user(session, admin_user.user_id, create_api_key=True)

        session.commit()
        logger.info(
            "Default data seeded: admin user '%s', project '%s', API key '%s'.",
            DEFAULT_ADMIN_EMAIL,
            project.project_name,
            api_key.key_name,
        )


def create_db_and_tables():
    """Create all tables defined by SQLModel metadata, then seed default data."""
    SQLModel.metadata.create_all(engine)
    _seed_default_data()


def get_session():
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session
