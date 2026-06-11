"""
Xenia CRM – Database Initialization Script
Creates the xenia_db database and runs all Alembic migrations.

Usage:
    # With venv activated:
    python scripts/init_db.py

    # Then seed data:
    python scripts/seed_data.py
"""

import os
import sys
import subprocess

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


def parse_connection_params(database_url: str) -> dict:
    """Parse DATABASE_URL into connection params for psycopg2."""
    # postgresql://user:password@host:port/dbname
    from urllib.parse import urlparse, unquote
    parsed = urlparse(database_url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "dbname": parsed.path.lstrip("/"),
    }


def create_database_if_not_exists():
    """Create xenia_db PostgreSQL database if it doesn't exist."""
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    params = parse_connection_params(settings.database_url)
    db_name = params.pop("dbname")

    # Connect to postgres default database
    conn = psycopg2.connect(**params, database="postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    if not cursor.fetchone():
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
        )
        print(f"[OK] Created database '{db_name}'")
    else:
        print(f"[INFO] Database '{db_name}' already exists — skipping creation")

    # Enable uuid-ossp extension
    conn2 = psycopg2.connect(**params, database=db_name)
    conn2.autocommit = True
    cur2 = conn2.cursor()
    cur2.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    conn2.close()
    print("[OK] uuid-ossp extension enabled")

    cursor.close()
    conn.close()


def run_alembic_migrations():
    """Run alembic upgrade head."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] Alembic migration failed:\n{result.stderr}")
        sys.exit(1)
    print("[OK] Alembic migrations applied successfully")
    if result.stdout:
        print(result.stdout)


if __name__ == "__main__":
    print("=" * 60)
    print("  Xenia CRM – Database Initialization")
    print("=" * 60)

    print("\nStep 1: Creating database...")
    create_database_if_not_exists()

    print("\nStep 2: Running Alembic migrations...")
    run_alembic_migrations()

    print("\n" + "=" * 60)
    print("  Database ready!")
    print("  Next: python scripts/seed_data.py")
    print("=" * 60)
