import json
import sqlite3
import os

DB_PATH = os.path.join("instance", "hardware.db")

def import_data():
    if not os.path.exists("backup_data.json"):
        print("No 'backup_data.json' file found!")
        return

    with open("backup_data.json", "r") as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Import Manufacturers
    if 'manufacturers' in data:
        print("Importing Manufacturers...")
        for item in data['manufacturers']:
            # We use INSERT OR IGNORE to avoid duplicates if you run this twice
            cur.execute(
                "INSERT OR IGNORE INTO manufacturers (name, website, notes) VALUES (?, ?, ?)",
                (item.get('name'), item.get('website'), item.get('notes'))
            )

    # 2. Import Hardware
    if 'hardware' in data:
        print("Importing Hardware...")
        for item in data['hardware']:
            # We explicitly list columns to map them safely
            # If you added a NEW column, it won't be in 'item', so .get() returns None
            cur.execute("""
                INSERT OR IGNORE INTO hardware (
                    hardware_id, description, category, classification, manufacturer, 
                    part_number, serial_number, status, custodian, location, 
                    safety_class, propellant_or_media, max_rated_pressure, max_rated_temperature,
                    traveler_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get('hardware_id'), item.get('description'), item.get('category'),
                item.get('classification'), item.get('manufacturer'), item.get('part_number'),
                item.get('serial_number'), item.get('status'), item.get('custodian'),
                item.get('location'), item.get('safety_class'), item.get('propellant_or_media'),
                item.get('max_rated_pressure'), item.get('max_rated_temperature'),
                item.get('traveler_path'), item.get('created_at'), item.get('updated_at')
            ))

    # 3. Import Procedures
    if 'procedures' in data:
        print("Importing Procedures...")
        for item in data['procedures']:
            cur.execute("""
                INSERT OR IGNORE INTO procedures (
                    proc_id, title, type, hardware_id, revision, purpose, 
                    hazards, prereqs, steps, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get('proc_id'), item.get('title'), item.get('type', 'SOP'), # Default to SOP if missing
                item.get('hardware_id'), item.get('revision'), item.get('purpose'),
                item.get('hazards'), item.get('prereqs'), item.get('steps'),
                item.get('created_at'), item.get('updated_at')
            ))
            
    # 4. Import Sections
    if 'procedure_sections' in data:
        print("Importing Sections...")
        for item in data['procedure_sections']:
            # We need to map the old procedure_id to the new one. 
            # Ideally, since we imported procedures in order, IDs match.
            # But relying on proc_id is safer. For simplicity, we assume IDs match here.
            cur.execute("""
                INSERT OR IGNORE INTO procedure_sections (
                    procedure_id, order_index, title, body
                ) VALUES (?, ?, ?, ?)
            """, (
                item.get('procedure_id'), item.get('order_index'), 
                item.get('title'), item.get('body')
            ))

    conn.commit()
    conn.close()
    print("\nSUCCESS: Data restored into database.")

if __name__ == "__main__":
    import_data()