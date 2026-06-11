"""
Alembic Environment – Xenia CRM
Reads database URL from app config (not alembic.ini) so there's
a single source of truth for all environment variables.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Make app importable from alembic/ directory ───────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.database import Base

# Import all models so Alembic sees the metadata
import app.models  # noqa: F401

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Migration Helpers ─────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without a live connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
