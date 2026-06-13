"""
Reset all 'failed' communications back to 'sent' so simulation buttons work.
Run: python scripts/reset_failed_comms.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import engine
from sqlalchemy import text
from datetime import datetime, timezone

def main():
    now = datetime.now(timezone.utc).isoformat()
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM communications WHERE status = 'failed'"
        ))
        count = result.scalar()
        print(f"Found {count} failed communications — resetting to 'sent'...")

        conn.execute(text(
            "UPDATE communications SET status = 'sent', sent_at = :now WHERE status = 'failed'"
        ), {"now": now})
        conn.commit()
        print(f"Done. {count} communications reset to 'sent'.")

if __name__ == "__main__":
    main()
