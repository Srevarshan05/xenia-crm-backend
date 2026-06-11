import os
import sys

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, Base
import app.models  # load all models to register with Base

def reinit():
    print("=" * 60)
    print("  Xenia CRM – Reinitializing Database Tables")
    print("=" * 60)
    
    print("\nDropping all existing tables...")
    try:
        Base.metadata.drop_all(bind=engine)
        print("[OK] Tables dropped.")
    except Exception as e:
        print(f"[ERROR] Error dropping tables: {e}")
        sys.exit(1)
        
    print("\nRecreating all tables from SQLAlchemy models...")
    try:
        Base.metadata.create_all(bind=engine)
        print("[OK] Tables recreated.")
    except Exception as e:
        print(f"[ERROR] Error creating tables: {e}")
        sys.exit(1)
        
    print("\nDatabase reinitialization complete!")
    print("Next: Run python scripts/seed_data.py to populate tables.")
    print("=" * 60)

if __name__ == "__main__":
    reinit()
