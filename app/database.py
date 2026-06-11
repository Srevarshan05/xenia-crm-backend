"""
Xenia CRM – Database Engine & Session Management
Provides SQLAlchemy async-compatible sync engine and a dependency-injected
session factory for FastAPI route handlers.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, MappedColumn, Session, sessionmaker

from app.config import settings


# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,       # recycle stale connections
    echo=settings.debug,      # SQL logging in dev
)

# Enable UUID extension in PostgreSQL
@event.listens_for(engine, "connect")
def enable_uuid_extension(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    cursor.close()


# ── Session Factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── Declarative Base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ── FastAPI Dependency ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session to route handlers.
    Automatically closes the session after the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Context Manager (for scripts/scheduler) ───────────────────────────────────
@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager for use outside of FastAPI (scripts, scheduler jobs).

    Usage:
        with db_session() as db:
            db.query(Customer).all()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
