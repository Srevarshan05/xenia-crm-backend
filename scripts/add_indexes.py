"""
Add missing performance indexes to Neon PostgreSQL.
Run once: python scripts/add_indexes.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import engine
from sqlalchemy import text

INDEXES = [
    # customer_metrics — columns used in audience cohort filters and summaries
    ("ix_customer_metrics_top_category",
     "CREATE INDEX IF NOT EXISTS ix_customer_metrics_top_category ON customer_metrics(top_category)"),
    ("ix_customer_metrics_preferred_channel",
     "CREATE INDEX IF NOT EXISTS ix_customer_metrics_preferred_channel ON customer_metrics(preferred_channel)"),
    ("ix_customer_metrics_days_since",
     "CREATE INDEX IF NOT EXISTS ix_customer_metrics_days_since ON customer_metrics(days_since_last_order)"),
    ("ix_customer_metrics_total_spend2",
     "CREATE INDEX IF NOT EXISTS ix_customer_metrics_total_spend2 ON customer_metrics(total_spend)"),
    ("ix_customer_metrics_churn_prob",
     "CREATE INDEX IF NOT EXISTS ix_customer_metrics_churn_prob ON customer_metrics(churn_probability)"),

    # customers — lower-case city search used by ilike filter
    ("ix_customers_city_lower",
     "CREATE INDEX IF NOT EXISTS ix_customers_city_lower ON customers(lower(city))"),

    # communications — composite index covering most tracking queries
    ("ix_comms_campaign_status",
     "CREATE INDEX IF NOT EXISTS ix_comms_campaign_status ON communications(campaign_id, status)"),

    # orders — partial index on attributed comms only (skips NULL rows, very fast)
    ("ix_orders_attributed_comm",
     "CREATE INDEX IF NOT EXISTS ix_orders_attributed_comm ON orders(attributed_communication_id) WHERE attributed_communication_id IS NOT NULL"),

    # opportunities — listing with priority filter
    ("ix_opps_status_priority",
     "CREATE INDEX IF NOT EXISTS ix_opps_status_priority ON opportunities(status, priority)"),

    # campaign_metrics — analytics join
    ("ix_campaign_metrics_cid",
     "CREATE INDEX IF NOT EXISTS ix_campaign_metrics_cid ON campaign_metrics(campaign_id)"),
]

def main():
    print("Creating missing indexes on Neon PostgreSQL...")
    with engine.connect() as conn:
        for name, sql in INDEXES:
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"  OK  {name}")
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                print(f"SKIP  {name}: {str(e)[:100]}")

    print("\nAll done.")

if __name__ == "__main__":
    main()
