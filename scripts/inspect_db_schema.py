import os
import sys
from sqlalchemy import inspect

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine

def main():
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    
    # We will generate a markdown report
    md = []
    md.append("# Xenia CRM – PostgreSQL Database Schema Report\n")
    md.append("This document outlines the complete database schema of Xenia CRM, reflected directly from the active PostgreSQL database.\n")
    
    # Add a Mermaid diagram of the relationships
    md.append("## Entity Relationship Diagram (ERD)\n")
    md.append("```mermaid")
    md.append("erDiagram")
    
    # Generate ERD relationships
    relationships = []
    for table in tables:
        fks = inspector.get_foreign_keys(table)
        for fk in fks:
            referred_table = fk["referred_table"]
            # To simplify, we show a basic link
            relationships.append(f"    {referred_table} ||--o{{ {table} : \"fk\"")
            
    # De-duplicate relationships
    relationships = sorted(list(set(relationships)))
    md.extend(relationships)
    md.append("```\n")
    
    # Table details
    md.append("## Table Specifications\n")
    
    for table in tables:
        md.append(f"### Table: `{table}`")
        md.append("")
        
        # Primary Key
        pk = inspector.get_pk_constraint(table)
        pk_cols = pk.get("constrained_columns", [])
        
        # Columns
        columns = inspector.get_columns(table)
        md.append("| Column | Type | Nullable | Primary Key | Default / FK |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        
        fks = {col: fk for fk in inspector.get_foreign_keys(table) for col in fk["constrained_columns"]}
        
        for col in columns:
            name = col["name"]
            col_type = str(col["type"])
            nullable = "YES" if col["nullable"] else "NO"
            is_pk = "YES" if name in pk_cols else "NO"
            
            # Default / FK details
            extra = []
            if col.get("default"):
                extra.append(f"Default: `{col['default']}`")
            if name in fks:
                fk_info = fks[name]
                ref_t = fk_info["referred_table"]
                ref_c = ", ".join(fk_info["referred_columns"])
                extra.append(f"FK: `{ref_t}({ref_c})`")
            
            extra_str = "; ".join(extra) if extra else "-"
            md.append(f"| **{name}** | {col_type} | {nullable} | {is_pk} | {extra_str} |")
            
        md.append("")
        
        # Indexes
        indexes = inspector.get_indexes(table)
        if indexes:
            md.append("#### Indexes:")
            for idx in indexes:
                cols = ", ".join(idx["include_columns"] + idx["column_names"])
                unique = " (Unique)" if idx["unique"] else ""
                md.append(f"- `{idx['name']}`: on columns `({cols})`{unique}")
            md.append("")
            
        md.append("---")
        md.append("")

    report_content = "\n".join(md)
    
    # Save the report in the artifacts folder
    artifact_dir = r"C:\Users\Srevarshan\.gemini\antigravity-ide\brain\08167df3-39e2-465e-b52a-d0e8e92033d0"
    os.makedirs(artifact_dir, exist_ok=True)
    report_path = os.path.join(artifact_dir, "db_schema_report.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"[OK] Reflected database schema. Report generated at: {report_path}")

if __name__ == "__main__":
    main()
