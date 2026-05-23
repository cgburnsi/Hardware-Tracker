import sqlite3
import click
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

    -- 9. SEED DATA
    INSERT OR IGNORE INTO manufacturers (name) VALUES ('Swagelok'), ('Parker'), ('McMaster-Carr'), ('Omega'), ('DigiKey');
    INSERT OR IGNORE INTO custodians (name) VALUES ('Lab Manager'), ('Test Engineer'), ('Quality Lead');
    INSERT OR IGNORE INTO locations (name) VALUES ('Flammables Cabinet'), ('Rack A'), ('Rack B'), ('Clean Room');
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
    db.commit()

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

    with app.app_context():
        try:
            migrate_db()
        except Exception:
            pass  # DB doesn't exist yet — init-db will create it with the full schema