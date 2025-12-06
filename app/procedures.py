import os
import tempfile
from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from docx import Document
from app.db import get_db

# Define the Blueprint
bp = Blueprint('procedures', __name__, url_prefix='/procedures')

# ---------------------------------------------------------------------------
# Helper: ID Generator
# ---------------------------------------------------------------------------

def generate_new_procedure_id(db):
    """Generate next procedure ID PYY-XXX based on current year."""
    now = datetime.now()
    yy = now.year % 100  # 2025 -> 25
    yy_str = f"{yy:02d}"

    like_pattern = f"P{yy_str}-%"
    cur = db.execute(
        "SELECT proc_id FROM procedures WHERE proc_id LIKE ? ORDER BY proc_id DESC LIMIT 1",
        (like_pattern,),
    )
    row = cur.fetchone()
    
    if row is None:
        seq = 1
    else:
        last_id = row["proc_id"]  # e.g. 'P25-007'
        last_seq_str = last_id.split("-")[-1]
        try:
            seq = int(last_seq_str) + 1
        except ValueError:
            seq = 1

    seq_str = f"{seq:03d}"
    return f"P{yy_str}-{seq_str}"


# ---------------------------------------------------------------------------
# Routes
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

    query += " ORDER BY proc_id"

    cur = db.execute(query, params)
    items = cur.fetchall()

    return render_template(
        "procedure_list.html",
        items=items,
        q=q,
    )

@bp.route("/<int:id>")
def procedure_detail(id):
    db = get_db()
    cur = db.execute("SELECT * FROM procedures WHERE id = ?", (id,))
    item = cur.fetchone()
    if item is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))
    return render_template("procedure_detail.html", item=item)

@bp.route("/new", methods=["GET", "POST"])
def procedure_new():
    db = get_db()
    if request.method == "POST":
        # 1. Identity
        title = request.form.get("title", "").strip()
        proc_type = request.form.get("type", "SOP").strip() # New Field
        revision = request.form.get("revision", "").strip() or "A"
        hardware_id = request.form.get("hardware_id", "").strip()
        
        # 2. Context & Safety
        purpose = request.form.get("purpose", "").strip()
        hazards = request.form.get("hazards", "").strip()
        prereqs = request.form.get("prereqs", "").strip()
        
        # 3. Content
        steps = request.form.get("steps", "").strip()

        if not title:
            flash("Title is required.", "error")
            return render_template("procedure_form.html", item=None)

        # ID Generation (We can customize this later for 'Test' types)
        proc_id = generate_new_procedure_id(db)
        
        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """
            INSERT INTO procedures
            (proc_id, title, type, hardware_id, revision, purpose, hazards, prereqs, steps, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proc_id, title, proc_type, hardware_id or None, revision,
                purpose or None, hazards or None, prereqs or None, steps or None,
                now, now,
            ),
        )
        db.commit()

        flash(f"Created {proc_type} {proc_id}.", "success")
        row = db.execute("SELECT id FROM procedures WHERE proc_id = ?", (proc_id,)).fetchone()
        return redirect(url_for("procedures.procedure_detail", id=row["id"]))

    return render_template("procedure_form.html", item=None)

@bp.route("/<int:id>/edit", methods=["GET", "POST"])
def procedure_edit(id):
    db = get_db()
    cur = db.execute("SELECT * FROM procedures WHERE id = ?", (id,))
    item = cur.fetchone()
    if item is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        proc_type = request.form.get("type", "SOP").strip() # New Field
        hardware_id = request.form.get("hardware_id", "").strip()
        revision = request.form.get("revision", "").strip()
        purpose = request.form.get("purpose", "").strip()
        hazards = request.form.get("hazards", "").strip()
        prereqs = request.form.get("prereqs", "").strip()
        steps = request.form.get("steps", "").strip()

        if not title:
            flash("Title is required.", "error")
            return render_template("procedure_form.html", item=item)

        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """
            UPDATE procedures
            SET title = ?, type = ?, hardware_id = ?, revision = ?, purpose = ?, hazards = ?,
                prereqs = ?, steps = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                title, proc_type, hardware_id or None, revision or None,
                purpose or None, hazards or None, prereqs or None, steps or None,
                now, id,
            ),
        )
        db.commit()
        flash("Procedure updated.", "success")
        return redirect(url_for("procedures.procedure_detail", id=id))

    return render_template("procedure_form.html", item=item)

@bp.route("/<int:id>/sections", methods=["GET", "POST"])
def procedure_sections(id):
    db = get_db()
    # Ensure procedure exists
    cur = db.execute("SELECT * FROM procedures WHERE id = ?", (id,))
    proc = cur.fetchone()
    if proc is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()

        if not title:
            flash("Section title is required.", "error")
        else:
            # Find next order_index
            cur = db.execute(
                "SELECT COALESCE(MAX(order_index), 0) AS max_ord FROM procedure_sections WHERE procedure_id = ?",
                (id,),
            )
            row = cur.fetchone()
            next_ord = (row["max_ord"] or 0) + 1

            db.execute(
                """
                INSERT INTO procedure_sections (procedure_id, order_index, title, body)
                VALUES (?, ?, ?, ?)
                """,
                (id, next_ord, title, body or None),
            )
            db.commit()
            flash("Section added.", "success")

    cur = db.execute(
        "SELECT * FROM procedure_sections WHERE procedure_id = ? ORDER BY order_index",
        (id,),
    )
    sections = cur.fetchall()

    return render_template("procedure_sections.html", proc=proc, sections=sections)

@bp.route("/<int:id>/export/docx")
def procedure_export_docx(id):
    db = get_db()
    cur = db.execute("SELECT * FROM procedures WHERE id = ?", (id,))
    proc = cur.fetchone()
    if proc is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))

    cur = db.execute(
        "SELECT * FROM procedure_sections WHERE procedure_id = ? ORDER BY order_index",
        (id,),
    )
    sections = cur.fetchall()

    doc = Document()
    doc.add_heading(f"{proc['proc_id']} – {proc['title']}", level=1)

    if proc["revision"]:
        doc.add_paragraph(f"Revision: {proc['revision']}")
    if proc["hardware_id"]:
        doc.add_paragraph(f"Hardware ID: {proc['hardware_id']}")
    if proc["purpose"]:
        doc.add_paragraph(f"Purpose: {proc['purpose']}")

    if proc["hazards"]:
        doc.add_paragraph(f"Hazards: {proc['hazards']}")
    if proc["prereqs"]:
        doc.add_paragraph(f"Prereqs: {proc['prereqs']}")

    doc.add_paragraph("")  # spacing

    for s in sections:
        doc.add_heading(s["title"], level=2)
        if s["body"]:
            for line in s["body"].splitlines():
                doc.add_paragraph(line)

    # If no sections, fall back to steps text
    if not sections and proc["steps"]:
        doc.add_heading("Procedure", level=2)
        for line in proc["steps"].splitlines():
            doc.add_paragraph(line)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    doc.save(tmp.name)
    tmp.flush()
    # It's important to close the file handle before Flask tries to send it
    tmp.close()

    filename = f"{proc['proc_id']}.docx"
    
    # We use try/finally to ensure the temp file is deleted (optional but good hygiene)
    return send_file(tmp.name, as_attachment=True, download_name=filename)