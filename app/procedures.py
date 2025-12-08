import os
import tempfile
from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from docx import Document
from app.db import get_db

bp = Blueprint('procedures', __name__, url_prefix='/procedures')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_new_procedure_id(db):
    """Generate next procedure ID PYY-XXX based on current year."""
    now = datetime.now()
    yy = f"{now.year % 100:02d}"
    
    cur = db.execute(
        "SELECT proc_id FROM procedures WHERE proc_id LIKE ? ORDER BY proc_id DESC LIMIT 1",
        (f"P{yy}-%",)
    )
    row = cur.fetchone()
    if row is None:
        seq = 1
    else:
        try:
            seq = int(row["proc_id"].split("-")[1]) + 1
        except:
            seq = 1
    return f"P{yy}-{seq:03d}"

def generate_run_id(db):
    """Generate next Run ID RYY-XXX based on current year."""
    now = datetime.now()
    yy = f"{now.year % 100:02d}"
    
    cur = db.execute(
        "SELECT run_id FROM procedure_runs WHERE run_id LIKE ? ORDER BY run_id DESC LIMIT 1",
        (f"R{yy}-%",)
    )
    row = cur.fetchone()
    if row is None:
        seq = 1
    else:
        try:
            seq = int(row["run_id"].split("-")[1]) + 1
        except:
            seq = 1
    return f"R{yy}-{seq:03d}"

# ---------------------------------------------------------------------------
# Procedure Definitions (SOPs)
# ---------------------------------------------------------------------------

@bp.route("/")
def procedure_list():
    db = get_db()
    q = request.args.get("q", "").strip()
    query = "SELECT * FROM procedures WHERE 1=1"
    params = []
    if q:
        query += " AND (proc_id LIKE ? OR title LIKE ? OR hardware_id LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    query += " ORDER BY proc_id DESC"
    items = db.execute(query, params).fetchall()
    return render_template("procedure_list.html", items=items, q=q)

@bp.route("/<int:id>")
def procedure_detail(id):
    db = get_db()
    item = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()
    if item is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))
    return render_template("procedure_detail.html", item=item)

@bp.route("/new", methods=["GET", "POST"])
def procedure_new():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        proc_type = request.form.get("type", "SOP").strip()
        revision = request.form.get("revision", "").strip() or "A"
        hardware_id = request.form.get("hardware_id", "").strip()
        purpose = request.form.get("purpose", "").strip()
        hazards = request.form.get("hazards", "").strip()
        prereqs = request.form.get("prereqs", "").strip()
        steps = request.form.get("steps", "").strip()

        if not title:
            flash("Title is required.", "error")
            return render_template("procedure_form.html", item=None)

        proc_id = generate_new_procedure_id(db)
        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """INSERT INTO procedures 
            (proc_id, title, type, hardware_id, revision, purpose, hazards, prereqs, steps, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (proc_id, title, proc_type, hardware_id or None, revision, purpose, hazards, prereqs, steps, now, now)
        )
        db.commit()
        flash(f"Created {proc_type} {proc_id}.", "success")
        row = db.execute("SELECT id FROM procedures WHERE proc_id = ?", (proc_id,)).fetchone()
        return redirect(url_for("procedures.procedure_detail", id=row["id"]))

    return render_template("procedure_form.html", item=None)

@bp.route("/<int:id>/edit", methods=["GET", "POST"])
def procedure_edit(id):
    db = get_db()
    item = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()
    if request.method == "POST":
        # ... (Same logic as procedure_new basically)
        title = request.form.get("title", "").strip()
        proc_type = request.form.get("type", "SOP").strip()
        hardware_id = request.form.get("hardware_id", "").strip()
        revision = request.form.get("revision", "").strip()
        purpose = request.form.get("purpose", "").strip()
        hazards = request.form.get("hazards", "").strip()
        prereqs = request.form.get("prereqs", "").strip()
        steps = request.form.get("steps", "").strip()
        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """UPDATE procedures SET title=?, type=?, hardware_id=?, revision=?, purpose=?, hazards=?, prereqs=?, steps=?, updated_at=? WHERE id=?""",
            (title, proc_type, hardware_id, revision, purpose, hazards, prereqs, steps, now, id)
        )
        db.commit()
        flash("Procedure updated.", "success")
        return redirect(url_for("procedures.procedure_detail", id=id))
    return render_template("procedure_form.html", item=item)

@bp.route("/<int:id>/sections", methods=["GET", "POST"])
def procedure_sections(id):
    db = get_db()
    proc = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        
        input_type = request.form.get("input_type", "none").strip()
        unit = request.form.get("unit", "").strip()
        
        # NEW: Capture Limits (Handle empty strings as None)
        min_val = request.form.get("min_value", "").strip()
        max_val = request.form.get("max_value", "").strip()
        min_val = float(min_val) if min_val else None
        max_val = float(max_val) if max_val else None

        if title:
            row = db.execute("SELECT COALESCE(MAX(order_index), 0) as max_ord FROM procedure_sections WHERE procedure_id=?", (id,)).fetchone()
            next_ord = row['max_ord'] + 1
            
            db.execute(
                """INSERT INTO procedure_sections 
                   (procedure_id, order_index, title, body, input_type, unit, min_value, max_value) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, next_ord, title, body, input_type, unit, min_val, max_val)
            )
            db.commit()
            flash("Section added.", "success")
            
    sections = db.execute("SELECT * FROM procedure_sections WHERE procedure_id=? ORDER BY order_index", (id,)).fetchall()
    return render_template("procedure_sections.html", proc=proc, sections=sections)

@bp.route("/<int:id>/export/docx")
def procedure_export_docx(id):
    # (Keep your existing export logic here - omitted for brevity but paste it back in!)
    # ...
    return "Export Logic Placeholder (Paste your old function here)"

# ---------------------------------------------------------------------------
# PROCEDURE RUNNER (The Execution Engine)
# ---------------------------------------------------------------------------

@bp.route("/run/setup", methods=["GET", "POST"])
def run_setup():
    """Step 1: Pick Hardware and Procedure"""
    db = get_db()
    hw_id_arg = request.args.get('hardware_id')
    
    if request.method == "POST":
        hw_id = request.form.get("hardware_id")
        proc_id = request.form.get("procedure_id")
        operator = request.form.get("operator")
        
        run_id = generate_run_id(db)
        now = datetime.utcnow().isoformat(timespec="seconds")
        
        db.execute(
            "INSERT INTO procedure_runs (run_id, procedure_id, hardware_id, operator, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, proc_id, hw_id, operator, now, "In-Progress")
        )
        db.commit()
        
        row = db.execute("SELECT id FROM procedure_runs WHERE run_id = ?", (run_id,)).fetchone()
        return redirect(url_for("procedures.run_execute", id=row['id']))

    hardware = db.execute("SELECT id, hardware_id, description FROM hardware ORDER BY hardware_id").fetchall()
    procedures = db.execute("SELECT id, proc_id, title FROM procedures ORDER BY proc_id").fetchall()
    return render_template("run_setup.html", hardware=hardware, procedures=procedures, sel_hw=hw_id_arg)

@bp.route("/run/<int:id>/execute", methods=["GET", "POST"])
def run_execute(id):
    """Step 2: The Checklist"""
    db = get_db()
    run = db.execute("""
        SELECT r.*, p.title as proc_title, p.proc_id, h.hardware_id, h.description as hw_desc 
        FROM procedure_runs r
        JOIN procedures p ON r.procedure_id = p.id
        JOIN hardware h ON r.hardware_id = h.id
        WHERE r.id = ?
    """, (id,)).fetchone()
    
    sections = db.execute("SELECT * FROM procedure_sections WHERE procedure_id = ? ORDER BY order_index", (run['procedure_id'],)).fetchall()

    if request.method == "POST":
        notes = request.form.get("notes", "")
        status = request.form.get("status", "Completed")
        
        # 1. Update Run Record
        db.execute("UPDATE procedure_runs SET status = ?, notes = ? WHERE id = ?", (status, notes, id))
        
        # 2. Add Entry to Hardware History Log
        log_desc = f"Procedure Run {run['run_id']} ({run['proc_id']}) completed. Status: {status}"
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute("INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                   (run['hardware_id'], now, "Procedure Run", log_desc))
        
        db.commit()
        flash(f"Run {run['run_id']} finished.", "success")
        return redirect(url_for("hardware.hardware_detail", id=run['hardware_id']))

    return render_template("run_execute.html", run=run, sections=sections)



# ... existing code ...

@bp.route("/runs")
def run_list():
    db = get_db()
    
    # Fetch all runs with details
    runs = db.execute("""
        SELECT r.*, p.title as proc_title, p.proc_id, h.hardware_id, h.description as hw_desc 
        FROM procedure_runs r
        JOIN procedures p ON r.procedure_id = p.id
        JOIN hardware h ON r.hardware_id = h.id
        ORDER BY r.timestamp DESC
    """).fetchall()
    
    return render_template("run_list.html", runs=runs)

# ... existing code ...


