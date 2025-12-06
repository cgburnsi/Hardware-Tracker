import sqlite3
import os

DB_PATH = os.path.join("instance", "hardware.db")

os.makedirs("instance", exist_ok=True)

schema = """
    DROP TABLE IF EXISTS hardware;

    CREATE TABLE hardware (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        
        --- IDENTITY ------------------------------------------------------------------------------
        hardware_id             TEXT UNIQUE NOT NULL,               -- e.g. H25001
        description             TEXT NOT NULL,                      -- human readable description
        category                TEXT,                               -- valve, thruster, etc.
        classification          TEXT,                               -- flight, dev, GSE, etc. 
    
        --- DETAILS -------------------------------------------------------------------------------
        part_number             TEXT,
        serial_number           TEXT,
        manufacturer            TEXT,                               -- MSFC, RSS, etc.
    
        --- STATUS & LIFECYCLE --------------------------------------------------------------------
        status                  TEXT,                               -- in-service, retired, etc.
        lifecycle_stage         TEXT,                               -- new, cleaned, as-received, etc.
        disposition_notes       TEXT,
    
        --- LOCATION & CUSTODY --------------------------------------------------------------------
        location                TEXT,
        custodian               TEXT,
        facility                TEXT,                               -- New field
    
        --- SAFETY CONTEXT ------------------------------------------------------------------------
        safety_class            TEXT,                               -- pressure, cryo, flammable
        propellant_or_media     TEXT,                               -- N2, AFM315E
        max_rated_pressure      REAL,                               -- Storing as number for sorting
        max_rated_temperature   REAL,                               -- Storing as number for sorting
    
        --- SYSTEM FIELDS -------------------------------------------------------------------------
        traveler_path           TEXT,
        created_at              TEXT,
        updated_at              TEXT
    );
    """


conn = sqlite3.connect(DB_PATH)
conn.executescript(schema)
conn.commit()
conn.close()

print(f"Initialized DB at {DB_PATH}")
