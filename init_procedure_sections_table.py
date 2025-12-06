import sqlite3
import os

DB_PATH = os.path.join("instance", "hardware.db")
os.makedirs("instance", exist_ok=True)

schema = """
CREATE TABLE IF NOT EXISTS procedure_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    FOREIGN KEY (procedure_id) REFERENCES procedures(id)
);
"""

conn = sqlite3.connect(DB_PATH)
conn.executescript(schema)
conn.commit()
conn.close()

print("Ensured procedure_sections table exists in", DB_PATH)
