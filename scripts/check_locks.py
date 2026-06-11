import os
import sys
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import engine

def main():
    query = """
    SELECT 
        pid, 
        usename, 
        client_addr, 
        state, 
        query, 
        age(clock_timestamp(), query_start) as duration 
    FROM pg_stat_activity 
    WHERE state != 'idle';
    """
    with engine.connect() as conn:
        result = conn.execute(text(query)).fetchall()
        print(f"Active connections ({len(result)}):")
        for row in result:
            print(f"PID: {row.pid} | User: {row.usename} | State: {row.state} | Duration: {row.duration}")
            print(f"Query: {row.query}\n" + "-"*40)

if __name__ == "__main__":
    main()
