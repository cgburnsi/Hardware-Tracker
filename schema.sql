-- schema.sql

DROP TABLE IF EXISTS hardware;

CREATE TABLE hardware (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    hardware_id         TEXT NOT NULL UNIQUE,         -- e.g. H25001
    description         TEXT NOT NULL,                -- human-readable

    category            TEXT,                         -- valve, thruster, sensor, etc.
    classification      TEXT,                         -- development, flight, GSE, etc.

    part_number         TEXT,
    serial_number       TEXT,
    manufacturer        TEXT,

    -- Status / lifecycle
    status              TEXT,                         -- in-service, under-test, retired, etc.
    lifecycle_stage     TEXT,                         -- new, as-received, cleaned, accepted, etc.
    date_added          TEXT,                         -- ISO timestamp string
    date_status_updated TEXT,                         -- ISO timestamp string
    disposition_notes   TEXT,

    -- Location & custody
    location            TEXT,                         -- "Lab A rack 3"
    custodian           TEXT,                         -- person / group name
    facility            TEXT,                         -- "MSFC ER64", etc.
    loan_status         TEXT,                         -- in-lab, loaned-out, in-transit
    loan_notes          TEXT,                         -- "loaned to J. Smith..." etc.

    -- Safety context
    safety_class        TEXT,                         -- pressure, cryo, etc.
    propellant_media    TEXT,                         -- AF-M315E, H2O2, GN2, etc.
    max_rated_pressure  REAL,                         -- numeric, units implied (later we can refine)
    max_rated_temp      REAL,

    -- Meta / audit
    created_by          TEXT,
    created_at          TEXT,
    updated_by          TEXT,
    updated_at          TEXT
);
