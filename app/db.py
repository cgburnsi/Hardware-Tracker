import json
import sqlite3
import click
from datetime import datetime
from flask import current_app, g

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    
    schema = """
    -- 1. CLEANUP
    DROP TABLE IF EXISTS kit_items;
    DROP TABLE IF EXISTS hardware;
    DROP TABLE IF EXISTS procedures;
    DROP TABLE IF EXISTS procedure_steps;
    DROP TABLE IF EXISTS procedure_sections;
    DROP TABLE IF EXISTS procedure_comments;
    DROP TABLE IF EXISTS hazard_types;
    DROP TABLE IF EXISTS manufacturers;
    DROP TABLE IF EXISTS custodians;
    DROP TABLE IF EXISTS locations;
    DROP TABLE IF EXISTS media;
    DROP TABLE IF EXISTS port_configs;
    DROP TABLE IF EXISTS hardware_log;
    DROP TABLE IF EXISTS procedure_runs;
    DROP TABLE IF EXISTS run_values;

    -- 2. HARDWARE TABLE
    CREATE TABLE hardware (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hardware_id TEXT UNIQUE NOT NULL,
        description TEXT NOT NULL,
        category TEXT,
        classification TEXT,
        manufacturer TEXT,
        part_number TEXT,
        serial_number TEXT,
        
        -- MSFC TRACKING
        ecn TEXT,
        calibration_id TEXT,
        repair_id TEXT,
        work_order_id TEXT,

        -- TECHNICAL PARAMS
        port_configuration TEXT,
        cv REAL,
        orifice_diameter REAL,

        -- STATUS & LOCATION
        status TEXT,
        location TEXT,
        custodian TEXT,

        -- SAFETY & COMPLIANCE
        safety_class TEXT,
        propellant_or_media TEXT,
        cleaning_spec TEXT,
        compliance_specs TEXT,
        max_rated_pressure REAL,
        max_rated_temperature REAL,

        traveler_path TEXT,
        image_filename TEXT,
        quantity INTEGER NOT NULL DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    );

    -- 3. LOOKUP TABLES
    -- (Added 'notes' back to manufacturers!)
    CREATE TABLE manufacturers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, website TEXT, notes TEXT);
    CREATE TABLE custodians (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE media (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE port_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    
    -- 4. PROCEDURES
    CREATE TABLE procedures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proc_id TEXT NOT NULL,
        title TEXT NOT NULL,
        type TEXT DEFAULT 'SOP',
        hardware_id TEXT,
        revision TEXT NOT NULL DEFAULT 'A',
        purpose TEXT,
        hazards TEXT,
        prereqs TEXT,
        parent_id INTEGER REFERENCES procedures(id),
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(proc_id, revision)
    );

    -- 4b. PROCEDURE COMMENTS (review annotations)
    CREATE TABLE procedure_comments (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        procedure_id INTEGER NOT NULL,
        section_id   INTEGER,
        step_id      INTEGER,
        target_label TEXT NOT NULL DEFAULT 'General',
        author_name  TEXT NOT NULL,
        body         TEXT NOT NULL,
        created_at   TEXT NOT NULL,
        resolved     INTEGER NOT NULL DEFAULT 0,
        resolved_by  TEXT,
        resolved_at  TEXT,
        FOREIGN KEY (procedure_id) REFERENCES procedures(id),
        FOREIGN KEY (section_id)   REFERENCES procedure_sections(id),
        FOREIGN KEY (step_id)      REFERENCES procedure_steps(id)
    );
    
    -- 5. SECTIONS (Groupings)
    CREATE TABLE procedure_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        procedure_id INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY (procedure_id) REFERENCES procedures(id)
    );

    -- 5b. STEPS (Individual items within a section)
    CREATE TABLE procedure_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        title TEXT NOT NULL,
        body TEXT,
        input_type TEXT DEFAULT 'none',
        unit TEXT,
        min_value REAL,
        max_value REAL,
        notes_enabled INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (section_id) REFERENCES procedure_sections(id)
    );

    -- 6. HARDWARE HISTORY LOG
    CREATE TABLE hardware_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hardware_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        action_type TEXT,
        description TEXT,
        FOREIGN KEY (hardware_id) REFERENCES hardware(id)
    );

    -- 7. PROCEDURE RUNS (Execution Log)
    CREATE TABLE procedure_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT UNIQUE NOT NULL,
        procedure_id INTEGER NOT NULL,
        hardware_id INTEGER NOT NULL,
        operator TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        status TEXT NOT NULL,
        notes TEXT,
        FOREIGN KEY (procedure_id) REFERENCES procedures(id),
        FOREIGN KEY (hardware_id) REFERENCES hardware(id)
    );

    -- 8. HARDWARE DOCUMENTS
    CREATE TABLE IF NOT EXISTS hardware_docs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hardware_id INTEGER NOT NULL,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL UNIQUE,
        label TEXT,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY (hardware_id) REFERENCES hardware(id)
    );

    -- 10. KIT CONTENTS
    CREATE TABLE kit_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kit_hardware_id INTEGER NOT NULL,
        ref_hardware_id INTEGER,
        description TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        FOREIGN KEY (kit_hardware_id) REFERENCES hardware(id),
        FOREIGN KEY (ref_hardware_id) REFERENCES hardware(id)
    );

    -- 9. RUN VALUES (Data Recording per step)
    CREATE TABLE run_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        step_id INTEGER NOT NULL,
        checked INTEGER DEFAULT 0,
        value TEXT,
        notes TEXT,
        FOREIGN KEY (run_id) REFERENCES procedure_runs(id),
        FOREIGN KEY (step_id) REFERENCES procedure_steps(id)
    );

    -- 10. HAZARD TYPES (configurable safety checklist)
    CREATE TABLE hazard_types (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE,
        ppe_text    TEXT,
        color       TEXT DEFAULT '#dc3545',
        sort_order  INTEGER DEFAULT 0,
        active      INTEGER DEFAULT 1
    );

    -- 11. HAZARD ANALYSES
    CREATE TABLE hazard_analyses (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        ha_id                    TEXT NOT NULL UNIQUE,
        title                    TEXT NOT NULL,
        facility_operation       TEXT,
        organization             TEXT,
        preliminary_classification TEXT,
        description              TEXT,
        scope                    TEXT,
        assumptions              TEXT,
        linked_procedure_id      INTEGER REFERENCES procedures(id),
        revision                 TEXT NOT NULL DEFAULT 'A',
        status                   TEXT NOT NULL DEFAULT 'draft',
        parent_id                INTEGER REFERENCES hazard_analyses(id),
        created_at               TEXT,
        updated_at               TEXT
    );

    CREATE TABLE hazard_items (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        ha_id               INTEGER NOT NULL,
        order_index         INTEGER NOT NULL DEFAULT 0,
        hazard_title        TEXT,
        hazard_description  TEXT,
        cause               TEXT,
        consequence         TEXT,
        initial_severity    INTEGER,
        initial_probability TEXT,
        final_severity      INTEGER,
        final_probability   TEXT,
        closed              INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (ha_id) REFERENCES hazard_analyses(id)
    );

    CREATE TABLE hazard_recommendations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        hazard_item_id  INTEGER NOT NULL,
        order_index     INTEGER NOT NULL DEFAULT 0,
        text            TEXT NOT NULL,
        FOREIGN KEY (hazard_item_id) REFERENCES hazard_items(id)
    );

    CREATE TABLE hazard_controls (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        hazard_item_id    INTEGER NOT NULL,
        recommendation_id INTEGER NOT NULL,
        order_index       INTEGER NOT NULL DEFAULT 0,
        control_type      TEXT,
        description       TEXT NOT NULL,
        verification      TEXT,
        FOREIGN KEY (hazard_item_id)    REFERENCES hazard_items(id),
        FOREIGN KEY (recommendation_id) REFERENCES hazard_recommendations(id)
    );

    CREATE TABLE hazard_notes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        hazard_item_id  INTEGER NOT NULL,
        author          TEXT NOT NULL,
        body            TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        FOREIGN KEY (hazard_item_id) REFERENCES hazard_items(id)
    );

    CREATE TABLE hazard_signatures (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ha_id        INTEGER NOT NULL,
        role         TEXT NOT NULL,
        signer_name  TEXT,
        signer_org   TEXT,
        signed_date  TEXT,
        FOREIGN KEY (ha_id) REFERENCES hazard_analyses(id)
    );

    -- 9. SEED DATA
    INSERT OR IGNORE INTO manufacturers (name) VALUES ('Swagelok'), ('Parker'), ('McMaster-Carr'), ('Omega'), ('DigiKey');
    INSERT OR IGNORE INTO custodians (name) VALUES ('Lab Manager'), ('Test Engineer'), ('Quality Lead');
    INSERT OR IGNORE INTO locations (name) VALUES ('Flammables Cabinet'), ('Rack A'), ('Rack B'), ('Clean Room');
    INSERT OR IGNORE INTO categories (name) VALUES ('Valve'), ('Regulator'), ('Sensor'), ('Tank'), ('Fitting'), ('Tool'), ('Electronics'), ('Other');
    INSERT OR IGNORE INTO media (name) VALUES ('N2'), ('He'), ('H2O'), ('H2O2'), ('AF-M315E'), ('Hydrazine');
    INSERT OR IGNORE INTO port_configs (name) VALUES ('1/4" Tube'), ('1/8" Tube'), ('1/4" NPT'), ('1/4" VCR'), ('3/8" Tube');

    INSERT OR IGNORE INTO hazard_types (name, ppe_text, color, sort_order) VALUES
        ('High Pressure',       'Safety glasses required. Face shield required for pressures above 100 PSI. Verify pressure ratings on all fittings and tubing before pressurization.',                                                      '#c0392b', 1),
        ('Propellant (ASCENT)', 'Chemical-resistant gloves (nitrile minimum). Chemical splash goggles. Lab coat or chemical-resistant apron. Ensure eyewash station is accessible and unobstructed. Review ASCENT SDS before handling.',   '#e67e22', 2),
        ('Noise',               'Hearing protection required for operations exceeding 85 dB. Double protection (plugs + muffs) required above 100 dB.',                                                                                     '#f39c12', 3),
        ('Cryogenic',           'Cryogenic-rated insulated gloves. Full face shield. Avoid synthetic clothing near cryogenic fluids. Ensure adequate ventilation to prevent oxygen displacement.',                                          '#2980b9', 4),
        ('Flammable/Ignition',  'Eliminate all ignition sources within the test area. Fire extinguisher accessible and recently inspected. No open flames. Ground all conductive components.',                                              '#d35400', 5),
        ('Electrical/ESD',      'ESD wrist strap required when handling electronics. Insulated tools only. Verify lockout/tagout procedure is complete before working on powered systems.',                                                 '#8e44ad', 6),
        ('Toxic/Chemical',      'Chemical-resistant gloves. Splash goggles. Fume hood or forced ventilation required. Review SDS for all chemicals present. Know location of nearest emergency shower.',                                   '#27ae60', 7),
        ('Heavy Lift',          'Back brace recommended for lifts over 35 lbs. Two-person lift required for loads over 50 lbs. Clear path before moving. Use lifting aids (dollies, hoists) where available.',                            '#7f8c8d', 8);
    """
    
    db.executescript(schema)
    db.commit()

@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

def migrate_db():
    """Add columns/tables introduced after initial schema — safe to run on existing DBs."""
    db = get_db()
    cols = {row[1] for row in db.execute("PRAGMA table_info(hardware)").fetchall()}
    if 'image_filename' not in cols:
        db.execute("ALTER TABLE hardware ADD COLUMN image_filename TEXT")
    if 'quantity' not in cols:
        db.execute("ALTER TABLE hardware ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
    proc_cols = {row[1] for row in db.execute("PRAGMA table_info(procedures)").fetchall()}
    if 'parent_id' not in proc_cols:
        db.execute("ALTER TABLE procedures ADD COLUMN parent_id INTEGER REFERENCES procedures(id)")
    if 'status' not in proc_cols:
        db.execute("ALTER TABLE procedures ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'")
    sec_cols = {row[1] for row in db.execute("PRAGMA table_info(procedure_sections)").fetchall()}
    if 'description' not in sec_cols:
        db.execute("ALTER TABLE procedure_sections ADD COLUMN description TEXT")
    rv_cols = {row[1] for row in db.execute("PRAGMA table_info(run_values)").fetchall()}
    if 'step_id' not in rv_cols:
        db.execute("ALTER TABLE run_values ADD COLUMN step_id INTEGER")
    if 'checked' not in rv_cols:
        db.execute("ALTER TABLE run_values ADD COLUMN checked INTEGER DEFAULT 0")
    if 'notes' not in rv_cols:
        db.execute("ALTER TABLE run_values ADD COLUMN notes TEXT")
    db.execute("""
        CREATE TABLE IF NOT EXISTS hardware_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hardware_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            label TEXT,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (hardware_id) REFERENCES hardware(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    db.executescript("""
        INSERT OR IGNORE INTO categories (name) VALUES
            ('Valve'), ('Regulator'), ('Sensor'), ('Tank'),
            ('Fitting'), ('Tool'), ('Electronics'), ('Other');
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS kit_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kit_hardware_id INTEGER NOT NULL,
            ref_hardware_id INTEGER,
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            FOREIGN KEY (kit_hardware_id) REFERENCES hardware(id),
            FOREIGN KEY (ref_hardware_id) REFERENCES hardware(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS procedure_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL,
            order_index INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            input_type TEXT DEFAULT 'none',
            unit TEXT,
            min_value REAL,
            max_value REAL,
            notes_enabled INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (section_id) REFERENCES procedure_sections(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS procedure_comments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            procedure_id INTEGER NOT NULL,
            section_id   INTEGER,
            step_id      INTEGER,
            target_label TEXT NOT NULL DEFAULT 'General',
            author_name  TEXT NOT NULL,
            body         TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            resolved     INTEGER NOT NULL DEFAULT 0,
            resolved_by  TEXT,
            resolved_at  TEXT,
            FOREIGN KEY (procedure_id) REFERENCES procedures(id),
            FOREIGN KEY (section_id)   REFERENCES procedure_sections(id),
            FOREIGN KEY (step_id)      REFERENCES procedure_steps(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_types (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            ppe_text    TEXT,
            color       TEXT DEFAULT '#dc3545',
            sort_order  INTEGER DEFAULT 0,
            active      INTEGER DEFAULT 1
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_analyses (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            ha_id                    TEXT NOT NULL UNIQUE,
            title                    TEXT NOT NULL,
            facility_operation       TEXT,
            organization             TEXT,
            preliminary_classification TEXT,
            description              TEXT,
            scope                    TEXT,
            assumptions              TEXT,
            linked_procedure_id      INTEGER REFERENCES procedures(id),
            revision                 TEXT NOT NULL DEFAULT 'A',
            status                   TEXT NOT NULL DEFAULT 'draft',
            parent_id                INTEGER REFERENCES hazard_analyses(id),
            created_at               TEXT,
            updated_at               TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_items (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            ha_id               INTEGER NOT NULL,
            order_index         INTEGER NOT NULL DEFAULT 0,
            hazard_title        TEXT,
            hazard_description  TEXT,
            cause               TEXT,
            consequence         TEXT,
            initial_severity    INTEGER,
            initial_probability TEXT,
            final_severity      INTEGER,
            final_probability   TEXT,
            closed              INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (ha_id) REFERENCES hazard_analyses(id)
        )
    """)
    hi_cols = {row[1] for row in db.execute("PRAGMA table_info(hazard_items)").fetchall()}
    if 'hazard_title' not in hi_cols:
        db.execute("ALTER TABLE hazard_items ADD COLUMN hazard_title TEXT")
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_controls (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            hazard_item_id    INTEGER NOT NULL,
            recommendation_id INTEGER,
            order_index       INTEGER NOT NULL DEFAULT 0,
            control_type      TEXT,
            description       TEXT NOT NULL,
            verification      TEXT,
            FOREIGN KEY (hazard_item_id)    REFERENCES hazard_items(id),
            FOREIGN KEY (recommendation_id) REFERENCES hazard_recommendations(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_recommendations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            hazard_item_id  INTEGER NOT NULL,
            order_index     INTEGER NOT NULL DEFAULT 0,
            text            TEXT NOT NULL,
            FOREIGN KEY (hazard_item_id) REFERENCES hazard_items(id)
        )
    """)
    hc_cols = {row[1] for row in db.execute("PRAGMA table_info(hazard_controls)").fetchall()}
    if 'recommendation_id' not in hc_cols:
        db.execute("ALTER TABLE hazard_controls ADD COLUMN recommendation_id INTEGER REFERENCES hazard_recommendations(id)")
    # Migrate any orphaned controls (existing controls with no recommendation)
    orphaned = db.execute(
        "SELECT DISTINCT hazard_item_id FROM hazard_controls WHERE recommendation_id IS NULL"
    ).fetchall()
    for row in orphaned:
        db.execute(
            "INSERT INTO hazard_recommendations (hazard_item_id, order_index, text) VALUES (?,?,?)",
            (row['hazard_item_id'], 0, 'General Controls')
        )
        rec_id = db.execute("SELECT last_insert_rowid() as id").fetchone()['id']
        db.execute(
            "UPDATE hazard_controls SET recommendation_id=? WHERE hazard_item_id=? AND recommendation_id IS NULL",
            (rec_id, row['hazard_item_id'])
        )
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_notes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            hazard_item_id  INTEGER NOT NULL,
            author          TEXT NOT NULL,
            body            TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (hazard_item_id) REFERENCES hazard_items(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_signatures (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ha_id        INTEGER NOT NULL,
            role         TEXT NOT NULL,
            signer_name  TEXT,
            signer_org   TEXT,
            signed_date  TEXT,
            FOREIGN KEY (ha_id) REFERENCES hazard_analyses(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS tps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tps_number TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            tps_type TEXT NOT NULL DEFAULT 'B',
            quality_sensitive INTEGER NOT NULL DEFAULT 0,
            safety_critical INTEGER NOT NULL DEFAULT 0,
            limited_life INTEGER NOT NULL DEFAULT 0,
            experiment_number TEXT,
            date_prepared TEXT,
            need_date TEXT,
            reference_docs TEXT,
            initiating_org TEXT DEFAULT 'ER64',
            system_name TEXT,
            reason_for_work TEXT,
            special_notes TEXT,
            prepared_by TEXT,
            final_accepted_by TEXT,
            acceptance_date TEXT,
            linked_procedure_id INTEGER REFERENCES procedures(id),
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS tps_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tps_id INTEGER NOT NULL,
            order_index INTEGER NOT NULL,
            description TEXT NOT NULL,
            input_type TEXT NOT NULL DEFAULT 'none',
            unit TEXT,
            min_value REAL,
            max_value REAL,
            result TEXT,
            recorded_value TEXT,
            tech_initial TEXT,
            step_notes TEXT,
            completed_at TEXT,
            FOREIGN KEY (tps_id) REFERENCES tps(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS tps_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tps_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            signer_name TEXT NOT NULL,
            signed_date TEXT,
            FOREIGN KEY (tps_id) REFERENCES tps(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS tps_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tps_id INTEGER NOT NULL,
            ref_type TEXT NOT NULL,
            linked_id INTEGER NOT NULL,
            FOREIGN KEY (tps_id) REFERENCES tps(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS category_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            field_key TEXT NOT NULL,
            label TEXT NOT NULL,
            field_type TEXT NOT NULL DEFAULT 'text',
            options TEXT,
            unit TEXT,
            placeholder TEXT,
            sort_order INTEGER DEFAULT 0,
            UNIQUE(category, field_key)
        )
    """)
    if 'specs_json' not in cols:
        db.execute("ALTER TABLE hardware ADD COLUMN specs_json TEXT")
    rows_to_migrate = db.execute(
        "SELECT id, port_configuration, cv, orifice_diameter FROM hardware"
        " WHERE specs_json IS NULL"
        "  AND (port_configuration IS NOT NULL OR cv IS NOT NULL OR orifice_diameter IS NOT NULL)"
    ).fetchall()
    for row in rows_to_migrate:
        specs = {}
        if row['port_configuration']:
            specs['port_configuration'] = row['port_configuration']
        if row['cv'] is not None:
            specs['cv'] = row['cv']
        if row['orifice_diameter'] is not None:
            specs['orifice_diameter'] = row['orifice_diameter']
        db.execute(
            "UPDATE hardware SET specs_json = ? WHERE id = ?",
            (json.dumps(specs), row['id'])
        )
    db.executemany(
        "INSERT OR IGNORE INTO category_fields"
        " (category, field_key, label, field_type, options, unit, placeholder, sort_order)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ('Valve', 'port_configuration', 'Port / Fitting Config', 'select',
             json.dumps(['1/4" Tube', '1/8" Tube', '1/4" NPT', '1/4" VCR',
                         '3/8" Tube', '1/2" Tube', '1/2" NPT', '3/4" Tube']),
             None, None, 1),
            ('Valve', 'cv', 'Cv (Flow Coeff)', 'number', None, None, '0.0', 2),
            ('Valve', 'orifice_diameter', 'Orifice Diameter', 'number', None, 'in', '0.0', 3),
        ]
    )
    if 'ctn' not in cols:
        db.execute("ALTER TABLE hardware ADD COLUMN ctn TEXT")

    db.execute("""
        CREATE TABLE IF NOT EXISTS ctns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS ecns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    for row in db.execute(
        "SELECT DISTINCT ctn FROM hardware WHERE ctn IS NOT NULL AND ctn != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO ctns (name) VALUES (?)", (row[0],))
        except Exception:
            pass
    for row in db.execute(
        "SELECT DISTINCT ecn FROM hardware WHERE ecn IS NOT NULL AND ecn != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO ecns (name) VALUES (?)", (row[0],))
        except Exception:
            pass

    db.execute("""
        CREATE TABLE IF NOT EXISTS part_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS other_specs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS a50_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    for row in db.execute(
        "SELECT DISTINCT part_number FROM hardware WHERE part_number IS NOT NULL AND part_number != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO part_numbers (name) VALUES (?)", (row[0],))
        except Exception:
            pass
    for row in db.execute(
        "SELECT DISTINCT compliance_specs FROM hardware WHERE compliance_specs IS NOT NULL AND compliance_specs != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO other_specs (name) VALUES (?)", (row[0],))
        except Exception:
            pass

    db.execute("""
        CREATE TABLE IF NOT EXISTS calibration_ids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS repair_ids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    for row in db.execute(
        "SELECT DISTINCT calibration_id FROM hardware WHERE calibration_id IS NOT NULL AND calibration_id != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO calibration_ids (name) VALUES (?)", (row[0],))
        except Exception:
            pass
    for row in db.execute(
        "SELECT DISTINCT repair_id FROM hardware WHERE repair_id IS NOT NULL AND repair_id != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO repair_ids (name) VALUES (?)", (row[0],))
        except Exception:
            pass

    db.execute("""
        CREATE TABLE IF NOT EXISTS cleaning_specs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    db.executescript("""
        INSERT OR IGNORE INTO cleaning_specs (name) VALUES
            ('O2 Clean'), ('MSFC-SPEC-164'), ('Solvent Clean'),
            ('Aqueous Clean'), ('N2 Purge'), ('As-Received');
    """)
    for row in db.execute(
        "SELECT DISTINCT cleaning_spec FROM hardware WHERE cleaning_spec IS NOT NULL AND cleaning_spec != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO cleaning_specs (name) VALUES (?)", (row[0],))
        except Exception:
            pass

    db.execute("""
        CREATE TABLE IF NOT EXISTS hardware_calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hardware_id INTEGER NOT NULL,
            cal_number TEXT NOT NULL,
            date_performed TEXT,
            due_date TEXT,
            notes TEXT,
            added_at TEXT NOT NULL,
            FOREIGN KEY (hardware_id) REFERENCES hardware(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hardware_repairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hardware_id INTEGER NOT NULL,
            repair_number TEXT NOT NULL,
            date TEXT,
            notes TEXT,
            added_at TEXT NOT NULL,
            FOREIGN KEY (hardware_id) REFERENCES hardware(id)
        )
    """)
    _mig_now = datetime.utcnow().isoformat(timespec="seconds")
    for row in db.execute(
        "SELECT id, calibration_id FROM hardware WHERE calibration_id IS NOT NULL AND calibration_id != ''"
    ).fetchall():
        existing = db.execute(
            "SELECT id FROM hardware_calibrations WHERE hardware_id = ? AND cal_number = ?",
            (row['id'], row['calibration_id'])
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO hardware_calibrations (hardware_id, cal_number, added_at) VALUES (?, ?, ?)",
                (row['id'], row['calibration_id'], _mig_now)
            )
    for row in db.execute(
        "SELECT id, repair_id FROM hardware WHERE repair_id IS NOT NULL AND repair_id != ''"
    ).fetchall():
        existing = db.execute(
            "SELECT id FROM hardware_repairs WHERE hardware_id = ? AND repair_number = ?",
            (row['id'], row['repair_id'])
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO hardware_repairs (hardware_id, repair_number, added_at) VALUES (?, ?, ?)",
                (row['id'], row['repair_id'], _mig_now)
            )

    db.execute("""
        CREATE TABLE IF NOT EXISTS hardware_work_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hardware_id INTEGER NOT NULL,
            work_order_number TEXT NOT NULL,
            date TEXT,
            notes TEXT,
            added_at TEXT NOT NULL,
            FOREIGN KEY (hardware_id) REFERENCES hardware(id)
        )
    """)
    for row in db.execute(
        "SELECT DISTINCT work_order_number FROM hardware_work_orders WHERE work_order_number IS NOT NULL AND work_order_number != ''"
    ).fetchall():
        try:
            db.execute("INSERT OR IGNORE INTO a50_numbers (name) VALUES (?)", (row[0],))
        except Exception:
            pass
    _now = datetime.utcnow().isoformat(timespec="seconds")
    for row in db.execute(
        "SELECT id, work_order_id FROM hardware WHERE work_order_id IS NOT NULL AND work_order_id != ''"
    ).fetchall():
        existing = db.execute(
            "SELECT id FROM hardware_work_orders WHERE hardware_id = ? AND work_order_number = ?",
            (row['id'], row['work_order_id'])
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO hardware_work_orders (hardware_id, work_order_number, added_at) VALUES (?, ?, ?)",
                (row['id'], row['work_order_id'], _now)
            )

    db.execute("""
        CREATE TABLE IF NOT EXISTS reference_documents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_number      TEXT NOT NULL,
            title           TEXT NOT NULL,
            revision        TEXT,
            description     TEXT,
            effective_date  TEXT,
            expiration_date TEXT,
            sort_order      INTEGER NOT NULL DEFAULT 0
        )
    """)
    rd_cols = {row[1] for row in db.execute("PRAGMA table_info(reference_documents)").fetchall()}
    if 'effective_date' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN effective_date TEXT")
    if 'expiration_date' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN expiration_date TEXT")
    if 'url' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN url TEXT")
    if 'file_original' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN file_original TEXT")
    if 'file_stored' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN file_stored TEXT")
    if 'cui' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN cui INTEGER NOT NULL DEFAULT 0")
    if 'cui_categories' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN cui_categories TEXT")
    if 'dist_statement' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN dist_statement TEXT")
    if 'dist_reason' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN dist_reason TEXT")
    if 'cui_dissem' not in rd_cols:
        db.execute("ALTER TABLE reference_documents ADD COLUMN cui_dissem TEXT")
    db.execute("""
        CREATE TABLE IF NOT EXISTS cui_categories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            code       TEXT NOT NULL UNIQUE,
            label      TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)
    db.executemany(
        "INSERT OR IGNORE INTO cui_categories (code, label, sort_order) VALUES (?, ?, ?)",
        [
            ('SP-EXPT',    'Export Controlled (EAR)',                        1),
            ('SP-EXPTR',   'Export Controlled Research',                     2),
            ('SP-PROPIN',  'Proprietary Manufacturing/Business Information',  3),
            ('SP-PROCURE', 'Procurement and Acquisition',                    4),
            ('SP-CTI',     'Controlled Technical Information',               5),
            ('SP-PRVCY',   'Privacy Act',                                    6),
        ]
    )
    cui_cat_cols = {row[1] for row in db.execute("PRAGMA table_info(cui_categories)").fetchall()}
    if 'description' not in cui_cat_cols:
        db.execute("ALTER TABLE cui_categories ADD COLUMN description TEXT")
    db.execute("""
        CREATE TABLE IF NOT EXISTS cui_dissem_controls (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL UNIQUE,
            label       TEXT NOT NULL,
            description TEXT,
            sort_order  INTEGER NOT NULL DEFAULT 0
        )
    """)
    cui_dissem_cols = {row[1] for row in db.execute("PRAGMA table_info(cui_dissem_controls)").fetchall()}
    if 'description' not in cui_dissem_cols:
        db.execute("ALTER TABLE cui_dissem_controls ADD COLUMN description TEXT")
    db.executemany(
        "INSERT OR IGNORE INTO cui_dissem_controls (code, label, description, sort_order) VALUES (?, ?, ?, ?)",
        [
            ('NOFORN',   'Not Releasable to Foreign Nationals',
             'Cannot be released to foreign nationals or representative of foreign nations.', 1),
            ('FED ONLY', 'Federal Employees and DoD Contractors Only',
             'Dissemination limited to federal government employees and DoD contractors.', 2),
            ('FEDCON',   'Federal and Contractor Employees Only',
             'Dissemination limited to federal employees and authorized contractors.', 3),
            ('NOCON',    'Not Releasable to Contractors',
             'Cannot be released to contractor personnel regardless of clearance level.', 4),
            ('DL ONLY',  'Dissemination and Extraction Controlled by Originator',
             'Further dissemination or extraction of information requires originator approval.', 5),
            ('REL TO',   'Authorized for Release To (append country codes)',
             'Authorized for release to the listed countries only, e.g. REL TO USA, GBR.', 6),
        ]
    )
    db.execute("""
        CREATE TABLE IF NOT EXISTS ref_doc_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_doc_id  INTEGER,
            doc_number  TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            action_type TEXT NOT NULL,
            description TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hazard_references (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ha_id         INTEGER NOT NULL,
            ref_doc_id    INTEGER,
            doc_number    TEXT NOT NULL,
            title         TEXT NOT NULL,
            revision      TEXT,
            section_cited TEXT,
            sort_order    INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (ha_id) REFERENCES hazard_analyses(id),
            FOREIGN KEY (ref_doc_id) REFERENCES reference_documents(id)
        )
    """)
    db.executescript("""
        INSERT OR IGNORE INTO hazard_types (name, ppe_text, color, sort_order) VALUES
            ('High Pressure',       'Safety glasses required. Face shield required for pressures above 100 PSI. Verify pressure ratings on all fittings and tubing before pressurization.',                                                      '#c0392b', 1),
            ('Propellant (ASCENT)', 'Chemical-resistant gloves (nitrile minimum). Chemical splash goggles. Lab coat or chemical-resistant apron. Ensure eyewash station is accessible and unobstructed. Review ASCENT SDS before handling.',   '#e67e22', 2),
            ('Noise',               'Hearing protection required for operations exceeding 85 dB. Double protection (plugs + muffs) required above 100 dB.',                                                                                     '#f39c12', 3),
            ('Cryogenic',           'Cryogenic-rated insulated gloves. Full face shield. Avoid synthetic clothing near cryogenic fluids. Ensure adequate ventilation to prevent oxygen displacement.',                                          '#2980b9', 4),
            ('Flammable/Ignition',  'Eliminate all ignition sources within the test area. Fire extinguisher accessible and recently inspected. No open flames. Ground all conductive components.',                                              '#d35400', 5),
            ('Electrical/ESD',      'ESD wrist strap required when handling electronics. Insulated tools only. Verify lockout/tagout procedure is complete before working on powered systems.',                                                 '#8e44ad', 6),
            ('Toxic/Chemical',      'Chemical-resistant gloves. Splash goggles. Fume hood or forced ventilation required. Review SDS for all chemicals present. Know location of nearest emergency shower.',                                   '#27ae60', 7),
            ('Heavy Lift',          'Back brace recommended for lifts over 35 lbs. Two-person lift required for loads over 50 lbs. Clear path before moving. Use lifting aids (dollies, hoists) where available.',                            '#7f8c8d', 8);
    """)
    db.commit()

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

    with app.app_context():
        try:
            migrate_db()
        except Exception:
            pass  # DB doesn't exist yet — init-db will create it with the full schema