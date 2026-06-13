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
# Neon PostgreSQL optimized settings:
# - pool_size=5: Neon free tier has a 100 connection limit; keep pool small
# - max_overflow=10: allow bursts up to 15 total connections
# - pool_recycle=300: recycle connections every 5 min (Neon idle timeout is 5 min)
# - pool_pre_ping=True: test connections before use to avoid stale conn errors
# - pool_timeout=30: wait up to 30s for a connection from pool before raising
engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=30,
    echo=False,            # disable per-query SQL logging (reduces latency overhead)
    connect_args={
        "connect_timeout": 10,
        "application_name": "xenia_crm",
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
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
