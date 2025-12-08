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
    
    print(f"Restoring data into {DB_PATH}...")

    # 1. LOOKUP TABLES (Simple Name Lists)
    simple_tables = ['manufacturers', 'custodians', 'locations', 'media', 'port_configs']
    for table in simple_tables:
        if table in data:
            print(f"  - Importing {table}...")
            for item in data[table]:
                # Manufactuers has website/notes, others are just name
                if table == 'manufacturers':
                    cur.execute("INSERT OR IGNORE INTO manufacturers (name, website, notes) VALUES (?, ?, ?)",
                                (item.get('name'), item.get('website'), item.get('notes')))
                else:
                    cur.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (item.get('name'),))

    # 2. HARDWARE (The Big Table)
    if 'hardware' in data:
        print("  - Importing hardware...")
        for item in data['hardware']:
            cur.execute("""
                INSERT OR IGNORE INTO hardware (
                    hardware_id, description, category, classification, manufacturer, 
                    part_number, serial_number, 
                    ecn, calibration_id, repair_id, work_order_id,
                    port_configuration, cv, orifice_diameter,
                    status, custodian, location, 
                    safety_class, propellant_or_media, cleaning_spec, compliance_specs,
                    max_rated_pressure, max_rated_temperature,
                    traveler_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get('hardware_id'), item.get('description'), item.get('category'),
                item.get('classification'), item.get('manufacturer'), item.get('part_number'),
                item.get('serial_number'), 
                item.get('ecn'), item.get('calibration_id'), item.get('repair_id'), item.get('work_order_id'),
                item.get('port_configuration'), item.get('cv'), item.get('orifice_diameter'),
                item.get('status'), item.get('custodian'), item.get('location'),
                item.get('safety_class'), item.get('propellant_or_media'), item.get('cleaning_spec'), item.get('compliance_specs'),
                item.get('max_rated_pressure'), item.get('max_rated_temperature'),
                item.get('traveler_path'), item.get('created_at'), item.get('updated_at')
            ))

    # 3. PROCEDURES
    if 'procedures' in data:
        print("  - Importing procedures...")
        for item in data['procedures']:
            cur.execute("""
                INSERT OR IGNORE INTO procedures (
                    proc_id, title, type, hardware_id, revision, purpose, 
                    hazards, prereqs, steps, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get('proc_id'), item.get('title'), item.get('type', 'SOP'),
                item.get('hardware_id'), item.get('revision'), item.get('purpose'),
                item.get('hazards'), item.get('prereqs'), item.get('steps'),
                item.get('created_at'), item.get('updated_at')
            ))

    # 4. PROCEDURE SECTIONS (Steps)
    if 'procedure_sections' in data:
        print("  - Importing sections...")
        for item in data['procedure_sections']:
            cur.execute("""
                INSERT OR IGNORE INTO procedure_sections (
                    procedure_id, order_index, title, body, input_type, unit
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                item.get('procedure_id'), item.get('order_index'), 
                item.get('title'), item.get('body'),
                item.get('input_type', 'none'), item.get('unit')
            ))

    # 5. LOGS & RUNS
    if 'hardware_log' in data:
        print("  - Importing hardware logs...")
        for item in data['hardware_log']:
            cur.execute("INSERT OR IGNORE INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                        (item.get('hardware_id'), item.get('timestamp'), item.get('action_type'), item.get('description')))

    if 'procedure_runs' in data:
        print("  - Importing procedure runs...")
        for item in data['procedure_runs']:
            cur.execute("""
                INSERT OR IGNORE INTO procedure_runs (
                    run_id, procedure_id, hardware_id, operator, timestamp, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get('run_id'), item.get('procedure_id'), item.get('hardware_id'),
                item.get('operator'), item.get('timestamp'), item.get('status'), item.get('notes')
            ))

    if 'run_values' in data:
        print("  - Importing run values...")
        for item in data['run_values']:
            cur.execute("INSERT OR IGNORE INTO run_values (run_id, section_id, value) VALUES (?, ?, ?)",
                        (item.get('run_id'), item.get('section_id'), item.get('value')))

    conn.commit()
    conn.close()
    print("\nSUCCESS: Data restored.")

if __name__ == "__main__":
    import_data()