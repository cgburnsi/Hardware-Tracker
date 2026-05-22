"""
seed_data.py  —  Populate the ER64 Ops Hub database with real hardware.

Usage:
    python seed_data.py

Safe to re-run:
    Items with a serial_number are skipped if that serial already exists.
    Items without a serial_number are always inserted (add one to prevent duplicates).

Edit the four sections below (LOOKUP TABLES + HARDWARE) with your real data.
Leave any field as None if it doesn't apply to a given item.
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "hardware.db")


# ============================================================
#  LOOKUP TABLES  (added with INSERT OR IGNORE — safe to re-run)
# ============================================================

MANUFACTURERS = [
    # "Swagelok",
    # "Parker",
    # "Moog",
    # "Marotta",
    # "Solenoid Solutions",
]

LOCATIONS = [
    # "Flammables Cabinet",
    # "Rack A",
    # "Rack B",
    # "Rack C",
    # "Test Cell 1",
    # "Clean Room",
    # "Cage",
]

CUSTODIANS = [
    # "Your Name",
    # "Team Member 2",
]

MEDIA = [
    # "GN2",
    # "GHe",
    # "LN2",
    # "LH2",
    # "LOX",
    # "H2O",
    # "H2O2",
    # "AF-M315E",
    # "Hydrazine",
]

PORT_CONFIGS = [
    # '1/4" Tube',
    # '1/8" Tube',
    # '3/8" Tube',
    # '1/2" Tube',
    # '1/4" NPT',
    # '1/2" NPT',
    # '1/4" VCR',
    # '9/16-18 UNF (AN)',
]


# ============================================================
#  HARDWARE
#  Required:  description
#  Optional:  everything else — omit or set to None
#
#  status choices:   "In-Service" | "New" | "In-Storage" | "Maintenance" | "Quarantined"
#  classification:   "Flight" | "Engineering" | "GSE" | "Surplus"
#  safety_class:     "Pressure" | "Cryo" | "Flammable" | "Toxic" | "Oxidizer" | None
# ============================================================

HARDWARE = [
    # -- Example entry (delete or replace with real items) --
    # {
    #     "description":          "Pressure Relief Valve",
    #     "category":             "Valve",
    #     "classification":       "Engineering",
    #     "manufacturer":         "Swagelok",
    #     "part_number":          "SS-RL3M4-CP",
    #     "serial_number":        "SN-001",          # used for duplicate detection
    #     "status":               "in-service",
    #     "location":             "Rack A",
    #     "custodian":            "Your Name",
    #     "safety_class":         "Pressure",
    #     "propellant_or_media":  "GN2",
    #     "max_rated_pressure":   3000,              # PSI
    #     "max_rated_temperature": 150,              # degC
    #     "port_configuration":   '1/4" Tube',
    #     "cleaning_spec":        "ASTM G93",
    #     "compliance_specs":     None,
    #     "cv":                   None,
    #     "orifice_diameter":     None,
    #     "ecn":                  None,
    #     "calibration_id":       None,
    #     "repair_id":            None,
    #     "work_order_id":        None,
    #     "traveler_path":        None,
    # },
]


# ============================================================
#  ENGINE  (no edits needed below this line)
# ============================================================

def _next_hardware_id(conn):
    yy = f"{datetime.now().year % 100:02d}"
    row = conn.execute(
        "SELECT hardware_id FROM hardware WHERE hardware_id LIKE ? ORDER BY hardware_id DESC LIMIT 1",
        (f"H{yy}%",)
    ).fetchone()
    seq = 1 if row is None else int(row[0][-3:]) + 1
    return f"H{yy}{seq:03d}"


def seed():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run:  flask --app main init-db")
        return

    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat(timespec="seconds")

    # -- Lookup tables --
    for name in MANUFACTURERS:
        conn.execute("INSERT OR IGNORE INTO manufacturers (name) VALUES (?)", (name,))
    for name in LOCATIONS:
        conn.execute("INSERT OR IGNORE INTO locations (name) VALUES (?)", (name,))
    for name in CUSTODIANS:
        conn.execute("INSERT OR IGNORE INTO custodians (name) VALUES (?)", (name,))
    for name in MEDIA:
        conn.execute("INSERT OR IGNORE INTO media (name) VALUES (?)", (name,))
    for name in PORT_CONFIGS:
        conn.execute("INSERT OR IGNORE INTO port_configs (name) VALUES (?)", (name,))

    # -- Hardware --
    added = skipped = 0
    for hw in HARDWARE:
        sn = hw.get("serial_number") or ""
        if sn:
            exists = conn.execute(
                "SELECT id FROM hardware WHERE serial_number = ?", (sn,)
            ).fetchone()
            if exists:
                print(f"  SKIP  {hw['description']} (serial {sn} already in DB)")
                skipped += 1
                continue

        hw_id = _next_hardware_id(conn)
        conn.execute("""
            INSERT INTO hardware (
                hardware_id, description, category, classification,
                manufacturer, part_number, serial_number,
                ecn, calibration_id, repair_id, work_order_id,
                port_configuration, cv, orifice_diameter,
                status, location, custodian,
                safety_class, propellant_or_media, cleaning_spec, compliance_specs,
                max_rated_pressure, max_rated_temperature,
                traveler_path, created_at, updated_at
            ) VALUES (?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?,?,?, ?,?, ?,?,?)
        """, (
            hw_id,
            hw.get("description", ""),
            hw.get("category"),
            hw.get("classification"),
            hw.get("manufacturer"),
            hw.get("part_number"),
            sn or None,
            hw.get("ecn"),
            hw.get("calibration_id"),
            hw.get("repair_id"),
            hw.get("work_order_id"),
            hw.get("port_configuration"),
            hw.get("cv"),
            hw.get("orifice_diameter"),
            hw.get("status", "new"),
            hw.get("location"),
            hw.get("custodian"),
            hw.get("safety_class"),
            hw.get("propellant_or_media"),
            hw.get("cleaning_spec"),
            hw.get("compliance_specs"),
            hw.get("max_rated_pressure"),
            hw.get("max_rated_temperature"),
            hw.get("traveler_path"),
            now, now,
        ))
        print(f"  ADD   {hw_id}  {hw['description']}")
        added += 1

    conn.commit()
    conn.close()
    print(f"\n  {added} added, {skipped} skipped.")


if __name__ == "__main__":
    seed()
