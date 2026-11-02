"""
AI-Powered Multilingual Shopping Intelligence Platform
Database Engine & SQLite PRAGMA Configuration Tests.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.core.database import ping_database, get_db


def test_sqlite_pragmas_enabled(test_engine: Engine):
    """
    Verify that SQLite connections strictly enforce WAL mode, foreign keys, and busy timeout.
    """
    with test_engine.connect() as conn:
        wal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
        foreign_keys = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        busy_timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()

    assert wal_mode is not None
    assert wal_mode.lower() == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5000


def test_ping_database(test_session: Session):
    """Verify ping_database successfully executes SELECT 1."""
    assert ping_database(test_session) is True


def test_get_db_session_lifecycle():
    """Verify get_db generator properly yields and closes sessions."""
    gen = get_db()
    db = next(gen)
    assert isinstance(db, Session)
    assert db.is_active is True
    # Verify ping on yielded session
    assert ping_database(db) is True
    # Close session via generator termination
    try:
        next(gen)
    except StopIteration:
        pass
