"""
Xenia CRM – Database Creation Helper Script
Run this ONCE to create the xenia_db PostgreSQL database.
Then run Alembic migrations to create tables.

Usage:
    python scripts/create_db.py
"""

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def create_database():
    """Connect to postgres default DB and create xenia_db if it doesn't exist."""
    # Connect to the default 'postgres' database
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password=input("Enter PostgreSQL password for user 'postgres': "),
        database="postgres",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # Check if DB exists
    cursor.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", ("xenia_db",)
    )
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier("xenia_db"))
        )
        print("✅ Database 'xenia_db' created successfully.")
    else:
        print("ℹ️  Database 'xenia_db' already exists.")

    cursor.close()
    conn.close()

    print("\n📋 Next steps:")
    print("   1. Update .env: DATABASE_URL=postgresql://postgres:<password>@localhost:5432/xenia_db")
    print("   2. Run: alembic upgrade head")
    print("   3. Run: python scripts/seed_data.py")


if __name__ == "__main__":
    create_database()
