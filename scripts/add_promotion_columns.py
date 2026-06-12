"""
Xenia CRM - Database Schema Alteration
Injects new promotions metadata columns for limits, caps, and Xenia auto-recommendation toggles.
"""
import sys
import os

# Add backend root to python search path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from sqlalchemy import text

def add_columns():
    with engine.connect() as conn:
        print("Checking promotions table columns...")
        # Check existing columns
        res = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='promotions'
        """))
        existing_cols = [r[0] for r in res.fetchall()]
        print(f"Existing columns: {existing_cols}")
        
        # New columns to inject
        new_cols = [
            ('max_discount_cap', 'NUMERIC(10, 2) NULL'),
            ('applicable_segments', "TEXT NOT NULL DEFAULT 'ALL'"),
            ('max_budget', 'NUMERIC(14, 2) NULL'),
            ('allow_xenia_recommendations', 'BOOLEAN NOT NULL DEFAULT TRUE'),
            ('per_shopper_limit', 'INTEGER NULL'),
            ('priority', "VARCHAR(50) NOT NULL DEFAULT 'Standard'")
        ]
        
        changed = False
        for col, type_sql in new_cols:
            if col not in existing_cols:
                print(f"Adding column '{col}'...")
                conn.execute(text(f"ALTER TABLE promotions ADD COLUMN {col} {type_sql};"))
                print(f"[OK] Column '{col}' added.")
                changed = True
            else:
                print(f"[INFO] Column '{col}' already exists.")
                
        if changed:
            conn.commit()
            print("[SUCCESS] Promotions table schema updated in PostgreSQL database!")
        else:
            print("[INFO] No schema changes needed. Promotions table already up-to-date.")

if __name__ == "__main__":
    add_columns()
