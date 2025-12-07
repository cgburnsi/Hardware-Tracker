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
    -- 1. CLEANUP (Drop old tables to reset)
    DROP TABLE IF EXISTS hardware;
    DROP TABLE IF EXISTS procedures;
    DROP TABLE IF EXISTS procedure_sections;
    DROP TABLE IF EXISTS manufacturers;

    -- 2. HARDWARE TABLE
    CREATE TABLE hardware (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hardware_id TEXT UNIQUE NOT NULL,
        description TEXT NOT NULL,
        category TEXT,
        classification TEXT,
        part_number TEXT,
        serial_number TEXT,
        manufacturer TEXT,
        status TEXT,
        location TEXT,
        custodian TEXT,
        safety_class TEXT,
        propellant_or_media TEXT,
        max_rated_pressure REAL,
        max_rated_temperature REAL,
        traveler_path TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    
    -- 3. MANUFACTURERS TABLE (Controlled List)
    CREATE TABLE manufacturers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        website TEXT,
        notes TEXT
    );

    -- 4. PROCEDURES TABLE (Definitions)
    CREATE TABLE procedures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proc_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        type TEXT DEFAULT 'SOP',    -- 'SOP' or 'Test'
        hardware_id TEXT,
        revision TEXT,
        purpose TEXT,
        hazards TEXT,
        prereqs TEXT,
        steps TEXT,                 -- Simple text steps (optional)
        created_at TEXT,
        updated_at TEXT
    );
    
    -- 5. PROCEDURE SECTIONS TABLE (The detailed steps)
    CREATE TABLE procedure_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        procedure_id INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        title TEXT NOT NULL,
        body TEXT,
        FOREIGN KEY (procedure_id) REFERENCES procedures(id)
    );
    
    -- 6. PRE-SEED DATA
    INSERT OR IGNORE INTO manufacturers (name) VALUES 
    ('Swagelok'), 
    ('Parker'), 
    ('McMaster-Carr'), 
    ('Omega'), 
    ('DigiKey'), 
    ('Thorlabs'), 
    ('National Instruments');
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