"""
AI-Powered Multilingual Shopping Intelligence Platform
Pytest Configuration & Fixtures.
Provides isolated temporary SQLite test databases and HTTP test clients.
"""

from typing import AsyncGenerator, Generator
from pathlib import Path
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine
import httpx

from backend.app.main import app
from backend.app.core.database import get_db, Base
from backend.app.core.config import Settings, get_settings
from backend.app.core.seed import seed_database


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Fixture providing testing settings."""
    settings = get_settings()
    return settings


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provide a path to a temporary isolated SQLite database file."""
    return tmp_path / "test_shopping.db"


@pytest.fixture
def test_engine(temp_db_path: Path) -> Generator[Engine, None, None]:
    """
    Create an isolated SQLAlchemy engine for tests with identical SQLite PRAGMAs.
    Ensures development database is never modified during tests.
    """
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 15.0},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_test_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA busy_timeout = 5000;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
        finally:
            cursor.close()

    # Create tables in test database and seed test catalog
    Base.metadata.create_all(bind=engine)
    seed_database(bind=engine)

    yield engine
    engine.dispose()


@pytest.fixture
def test_session(test_engine: Engine) -> Generator[Session, None, None]:
    """Provide a transactional database session for tests."""
    testing_session_local = sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture
async def async_client(test_session: Session) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Provide an async HTTP test client using httpx.ASGITransport.
    Overrides database dependency with isolated test session.
    """
    def _override_get_db() -> Generator[Session, None, None]:
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
