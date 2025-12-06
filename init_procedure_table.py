import sqlite3
import os

DB_PATH = os.path.join("instance", "hardware.db")
os.makedirs("instance", exist_ok=True)

schema = """
CREATE TABLE IF NOT EXISTS procedures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proc_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    hardware_id TEXT,
    revision TEXT,
    purpose TEXT,
    hazards TEXT,
    prereqs TEXT,
    steps TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""

conn = sqlite3.connect(DB_PATH)
conn.executescript(schema)
conn.commit()
conn.close()

print("Ensured procedures table exists in", DB_PATH)
