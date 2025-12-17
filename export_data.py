import json
import sqlite3
import os

DB_PATH = os.path.join("instance", "hardware.db")

def export_data():
    if not os.path.exists(DB_PATH):
        print("No database found to export!")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    data = {}
    
    # List of all tables we want to save
    tables = [
        "hardware",
        "manufacturers",
        "custodians",
        "locations",
        "media",
        "port_configs",
        "personnel",   
        "procedures",
        "procedure_sections",
        "hardware_log",
        "procedure_runs",
        "run_values"  # We will create this one next!
    ]

    print(f"Exporting data from {DB_PATH}...")

    for table in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(row) for row in rows]
            print(f"  - {table}: {len(rows)} records")
        except sqlite3.OperationalError:
            print(f"  - {table}: (Table not found, skipping)")

    conn.close()
    
    with open("backup_data.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print("\nSUCCESS: All data saved to 'backup_data.json'")

if __name__ == "__main__":
    export_data()