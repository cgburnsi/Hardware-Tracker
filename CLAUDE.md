# ER64 Ops Hub — Claude Context

Internal NASA ER64 lab tool. Hardware inventory tracker, SOP/procedure management, and live procedure execution checklists. Local-only for now; pending server allocation from NASA IT.

## Running the app

```
.venv\Scripts\python main.py
```

If the venv is missing (OneDrive sometimes corrupts it):
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\flask --app main init-db
```

Database lives at `instance/hardware.db`. Never commit the `instance/` folder.

## Stack

- **Flask** with blueprints (`app/hardware.py`, `app/procedures.py`)
- **SQLite** via raw `sqlite3` — no ORM. `get_db()` / Flask `g` pattern in `app/db.py`
- **Jinja2** templates in `app/templates/`, all extend `base.html`
- No frontend framework, no CDN dependencies — vanilla CSS + inline SVG icons
- GitHub: `cgburnsi/Hardware-Tracker`, HTTPS only (SSH blocked on NASA network)

## Architecture

```
app/
  __init__.py       — app factory, home route (index), backup-db route
  db.py             — get_db(), init_db(), migrate_db() (safe ALTER TABLE migrations)
  hardware.py       — Blueprint: all hardware routes
  procedures.py     — Blueprint: all procedure/run routes
  templates/
    base.html       — nav, sidebar, shared CSS variables and badge classes
    home.html       — landing page (status tiles, recent runs)
    hardware_*.html — list, detail, form
    procedure_*.html / run_*.html
instance/
  hardware.db       — SQLite DB (gitignored)
  uploads/          — hardware images ({hardware_id}.{ext})
  uploads/docs/     — hardware documents ({hardware_id}_{uuid8}.{ext})
```

## Database migrations

`migrate_db()` in `db.py` runs at startup and is the right place to add columns/tables to existing DBs. Pattern:

```python
cols = {row[1] for row in db.execute("PRAGMA table_info(hardware)").fetchall()}
if 'new_column' not in cols:
    db.execute("ALTER TABLE hardware ADD COLUMN new_column TEXT")
db.execute("CREATE TABLE IF NOT EXISTS new_table (...)")
```

## Key features built so far

- **Hardware inventory** — H-number auto-generation (HYYXXX), full field set including safety/compliance fields, images, documents
- **Quantity tracking** — `+/-` adjustment buttons on detail page, logs every change
- **Kit grouping** — any H-number can have a parts list; parts are free-text or linked to another H-number; quantities are independent of child item stock
- **Flight Hardware flag** — checkbox sets `classification='Flight'`; gold FLIGHT badge appears on list and detail pages
- **Operational history** — `hardware_log` table; every create, edit, stock adjustment, image/doc change, and kit change is logged
- **Documents** — multiple attachments per hardware item (PDF, DOCX, DWG, etc.)
- **Procedures & runs** — SOPs with sections, data recording (min/max limits), execution log
- **DB backup** — `/backup-db` route on the home page downloads a consistent SQLite snapshot

## User preferences

- Plain language only — no "dashboard", no corporate jargon
- The landing page is called "Home", not "Dashboard"
- Practical and direct; no unnecessary abstractions or over-engineering
- Prefers changes logged to operational history for auditability
