import sqlite3
import os

DB_PATH = os.path.join("instance", "hardware.db")

os.makedirs("instance", exist_ok=True)

schema = """
DROP TABLE IF EXISTS hardware;

CREATE TABLE hardware (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hardware_id TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    category TEXT,
    part_number TEXT,
    serial_number TEXT,
    status TEXT,
    custodian TEXT,
    location TEXT,
    traveler_path TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""

conn = sqlite3.connect(DB_PATH)
conn.executescript(schema)
conn.commit()
conn.close()

print(f"Initialized DB at {DB_PATH}")
