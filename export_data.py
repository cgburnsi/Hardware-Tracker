import json
import sqlite3
import os

# Connect to the database directly
DB_PATH = os.path.join("instance", "hardware.db")

def export_data():
    if not os.path.exists(DB_PATH):
        print("No database found to export!")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This lets us access columns by name
    
    data = {}
    
    # 1. Export Hardware
    try:
        hw_rows = conn.execute("SELECT * FROM hardware").fetchall()
        data['hardware'] = [dict(row) for row in hw_rows]
        print(f"Exported {len(hw_rows)} hardware items.")
    except sqlite3.OperationalError:
        print("Hardware table not found or empty.")

    # 2. Export Manufacturers
    try:
        man_rows = conn.execute("SELECT * FROM manufacturers").fetchall()
        data['manufacturers'] = [dict(row) for row in man_rows]
        print(f"Exported {len(man_rows)} manufacturers.")
    except sqlite3.OperationalError:
        pass

    # 3. Export Procedures
    try:
        proc_rows = conn.execute("SELECT * FROM procedures").fetchall()
        data['procedures'] = [dict(row) for row in proc_rows]
        print(f"Exported {len(proc_rows)} procedures.")
    except sqlite3.OperationalError:
        pass

    # 4. Export Procedure Sections
    try:
        sect_rows = conn.execute("SELECT * FROM procedure_sections").fetchall()
        data['procedure_sections'] = [dict(row) for row in sect_rows]
        print(f"Exported {len(sect_rows)} procedure sections.")
    except sqlite3.OperationalError:
        pass

    conn.close()
    
    # Save to a file
    with open("backup_data.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print("\nSUCCESS: Data saved to 'backup_data.json'")

if __name__ == "__main__":
    export_data()