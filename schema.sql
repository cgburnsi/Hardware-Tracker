DROP TABLE IF EXISTS hardware;

CREATE TABLE hardware (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hardware_id TEXT UNIQUE NOT NULL,   -- HYYXXX
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
