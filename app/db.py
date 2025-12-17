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
    DROP TABLE IF EXISTS hardware;
    DROP TABLE IF EXISTS procedures;
    DROP TABLE IF EXISTS procedure_sections;
    DROP TABLE IF EXISTS manufacturers;
    DROP TABLE IF EXISTS custodians;
    DROP TABLE IF EXISTS locations;
    DROP TABLE IF EXISTS media;
    DROP TABLE IF EXISTS port_configs;
    DROP TABLE IF EXISTS hardware_log;
    DROP TABLE IF EXISTS procedure_runs;
    DROP TABLE IF EXISTS run_values;
    DROP TABLE IF EXISTS personnel;

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
        created_at TEXT,
        updated_at TEXT,
        
        parent_id INTEGER, 
        FOREIGN KEY (parent_id) REFERENCES hardware(id)
    );

    -- 3. LOOKUP TABLES
    CREATE TABLE manufacturers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, website TEXT, notes TEXT);
    CREATE TABLE custodians (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE media (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    CREATE TABLE port_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
    
    -- 4. AUTHORIZED PERSONNEL (NEW TABLE)
    CREATE TABLE personnel (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        initials TEXT NOT NULL,
        pin_code TEXT UNIQUE NOT NULL,
        role TEXT DEFAULT 'Operator'
    );

    -- 5. PROCEDURES
    CREATE TABLE procedures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proc_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        type TEXT DEFAULT 'SOP',
        hardware_id TEXT,
        revision TEXT,
        purpose TEXT,
        hazards TEXT,
        prereqs TEXT,
        steps TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    
    -- 6. SECTIONS (Procedure Steps)
    CREATE TABLE procedure_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        procedure_id INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        
        step_label TEXT,
        title TEXT NOT NULL,
        body TEXT,
        command TEXT,
        substeps TEXT,
        
        input_type TEXT DEFAULT 'none',
        unit TEXT,
        min_value REAL,
        max_value REAL,
        requires_initials INTEGER DEFAULT 0,
        
        FOREIGN KEY (procedure_id) REFERENCES procedures(id)
    );

    -- 7. HARDWARE HISTORY LOG
    CREATE TABLE hardware_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hardware_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        action_type TEXT,
        description TEXT,
        operator TEXT,  -- Stores "CGB" etc.
        FOREIGN KEY (hardware_id) REFERENCES hardware(id)
    );

    -- 8. PROCEDURE RUNS
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

    -- 9. RUN VALUES
    CREATE TABLE run_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        section_id INTEGER NOT NULL,
        value TEXT,
        initials TEXT,
        FOREIGN KEY (run_id) REFERENCES procedure_runs(id),
        FOREIGN KEY (section_id) REFERENCES procedure_sections(id)
    );

    -- 10. SEED DATA
    INSERT OR IGNORE INTO manufacturers (name) VALUES ('Swagelok'), ('Parker'), ('McMaster-Carr'), ('Omega'), ('DigiKey');
    INSERT OR IGNORE INTO custodians (name) VALUES ('Lab Manager'), ('Test Engineer'), ('Quality Lead');
    INSERT OR IGNORE INTO locations (name) VALUES ('Flammables Cabinet'), ('Rack A'), ('Rack B'), ('Clean Room');
    INSERT OR IGNORE INTO media (name) VALUES ('N2'), ('He'), ('H2O'), ('H2O2'), ('AF-M315E'), ('Hydrazine');
    INSERT OR IGNORE INTO port_configs (name) VALUES ('1/4" Tube'), ('1/8" Tube'), ('1/4" NPT'), ('1/4" VCR'), ('3/8" Tube');
    
    -- Seed Personnel (So you can log in immediately)
    INSERT INTO personnel (name, initials, pin_code, role) VALUES 
    ('Chris Burnside', 'CGB', '384', 'Admin'),
    ('Test Operator',  'TST', '999', 'Technician');
    """
    
    db.executescript(schema)
    db.commit()

@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)