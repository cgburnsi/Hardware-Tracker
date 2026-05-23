import os
import tempfile
from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from app.db import get_db

bp = Blueprint('procedures', __name__, url_prefix='/procedures')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_new_procedure_id(db):
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
        except Exception:
            seq = 1
    return f"P{yy}-{seq:03d}"

def generate_run_id(db):
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
        except Exception:
            seq = 1
    return f"R{yy}-{seq:03d}"

def get_sections_with_steps(db, procedure_id):
    sections = db.execute(
        "SELECT * FROM procedure_sections WHERE procedure_id = ? ORDER BY order_index",
        (procedure_id,)
    ).fetchall()
    all_steps = db.execute("""
        SELECT s.* FROM procedure_steps s
        JOIN procedure_sections sec ON s.section_id = sec.id
        WHERE sec.procedure_id = ?
        ORDER BY s.section_id, s.order_index
    """, (procedure_id,)).fetchall()
    steps_by_section = {}
    for step in all_steps:
        sid = step['section_id']
        if sid not in steps_by_section:
            steps_by_section[sid] = []
        steps_by_section[sid].append(step)
    return sections, steps_by_section

# ---------------------------------------------------------------------------
# Procedure Definitions
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
    query += " ORDER BY proc_id ASC, revision ASC"
    items = db.execute(query, params).fetchall()
    return render_template("procedure_list.html", items=items, q=q)

@bp.route("/<int:id>")
def procedure_detail(id):
    db = get_db()
    item = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()
    if item is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))
    sections, steps_by_section = get_sections_with_steps(db, id)
    parent = None
    if item['parent_id']:
        parent = db.execute("SELECT id, proc_id, revision, title FROM procedures WHERE id = ?",
                            (item['parent_id'],)).fetchone()
    children = db.execute(
        "SELECT id, proc_id, revision, title FROM procedures WHERE parent_id = ? ORDER BY proc_id, revision",
        (id,)
    ).fetchall()
    comments = db.execute(
        "SELECT * FROM procedure_comments WHERE procedure_id=? ORDER BY resolved ASC, created_at DESC",
        (id,)
    ).fetchall()
    open_by_section = {}
    open_by_step = {}
    for c in comments:
        if not c['resolved']:
            if c['section_id']:
                open_by_section[c['section_id']] = open_by_section.get(c['section_id'], 0) + 1
            if c['step_id']:
                open_by_step[c['step_id']] = open_by_step.get(c['step_id'], 0) + 1
    open_count = sum(1 for c in comments if not c['resolved'])
    hazard_types = db.execute(
        "SELECT * FROM hazard_types WHERE active=1 ORDER BY sort_order"
    ).fetchall()
    return render_template("procedure_detail.html", item=item, sections=sections,
                           steps_by_section=steps_by_section, parent=parent, children=children,
                           comments=comments, open_count=open_count,
                           open_by_section=open_by_section, open_by_step=open_by_step,
                           hazard_types=hazard_types)

def _form_context(db):
    """Shared context data for the procedure form."""
    hardware = db.execute(
        "SELECT hardware_id, description FROM hardware ORDER BY hardware_id"
    ).fetchall()
    hazard_types = db.execute(
        "SELECT * FROM hazard_types WHERE active=1 ORDER BY sort_order"
    ).fetchall()
    return hardware, hazard_types

@bp.route("/new", methods=["GET", "POST"])
def procedure_new():
    db = get_db()
    hardware, hazard_types = _form_context(db)
    if request.method == "POST":
        title      = request.form.get("title", "").strip()
        proc_type  = request.form.get("type", "SOP").strip()
        hardware_id = request.form.get("hardware_id", "").strip()
        purpose    = request.form.get("purpose", "").strip()
        hazards    = ", ".join(request.form.getlist("hazards"))
        prereqs    = request.form.get("prereqs", "").strip()

        if not title:
            flash("Title is required.", "error")
            return render_template("procedure_form.html", item=None,
                                   hardware=hardware, hazard_types=hazard_types)
        if not hardware_id:
            flash("Target hardware is required.", "error")
            return render_template("procedure_form.html", item=None,
                                   hardware=hardware, hazard_types=hazard_types)

        proc_id = generate_new_procedure_id(db)
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            """INSERT INTO procedures
               (proc_id, title, type, hardware_id, revision, purpose, hazards, prereqs, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'A', ?, ?, ?, ?, ?)""",
            (proc_id, title, proc_type, hardware_id, purpose, hazards, prereqs, now, now)
        )
        db.commit()
        flash(f"Created {proc_type} {proc_id}.", "success")
        row = db.execute("SELECT id FROM procedures WHERE proc_id = ? AND revision = 'A'", (proc_id,)).fetchone()
        return redirect(url_for("procedures.procedure_detail", id=row["id"]))

    return render_template("procedure_form.html", item=None,
                           hardware=hardware, hazard_types=hazard_types)

@bp.route("/<int:id>/edit", methods=["GET", "POST"])
def procedure_edit(id):
    db = get_db()
    item = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()
    hardware, hazard_types = _form_context(db)
    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        proc_type   = request.form.get("type", "SOP").strip()
        hardware_id = request.form.get("hardware_id", "").strip()
        purpose     = request.form.get("purpose", "").strip()
        hazards     = ", ".join(request.form.getlist("hazards"))
        prereqs     = request.form.get("prereqs", "").strip()
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            """UPDATE procedures SET title=?, type=?, hardware_id=?,
               purpose=?, hazards=?, prereqs=?, updated_at=? WHERE id=?""",
            (title, proc_type, hardware_id, purpose, hazards, prereqs, now, id)
        )
        db.commit()
        flash("Procedure updated.", "success")
        return redirect(url_for("procedures.procedure_detail", id=id))
    return render_template("procedure_form.html", item=item,
                           hardware=hardware, hazard_types=hazard_types)

# ---------------------------------------------------------------------------
# Revise / Branch
# ---------------------------------------------------------------------------

@bp.route("/<int:id>/revise", methods=["GET", "POST"])
def procedure_revise(id):
    db = get_db()
    source = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()
    if source is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))

    if request.method == "POST":
        mode = request.form.get("mode")          # "revision" or "variant"
        title = request.form.get("title", "").strip()
        revision = request.form.get("revision", "A").strip() or "A"
        new_proc_id = request.form.get("proc_id", "").strip()
        hardware_id = request.form.get("hardware_id", "").strip()
        purpose = request.form.get("purpose", "").strip()
        hazards = request.form.get("hazards", "").strip()
        prereqs = request.form.get("prereqs", "").strip()
        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """INSERT INTO procedures
               (proc_id, title, type, hardware_id, revision, purpose, hazards, prereqs, parent_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_proc_id, title, source['type'], hardware_id or None,
             revision, purpose, hazards, prereqs, id, now, now)
        )
        db.commit()
        new_proc = db.execute(
            "SELECT id FROM procedures WHERE proc_id = ? AND revision = ?", (new_proc_id, revision)
        ).fetchone()

        # Deep copy sections + steps
        source_sections, source_steps = get_sections_with_steps(db, id)
        for sec in source_sections:
            db.execute(
                "INSERT INTO procedure_sections (procedure_id, order_index, title, description) VALUES (?, ?, ?, ?)",
                (new_proc['id'], sec['order_index'], sec['title'], sec['description'])
            )
            db.commit()
            new_sec = db.execute(
                "SELECT id FROM procedure_sections WHERE procedure_id=? ORDER BY id DESC LIMIT 1",
                (new_proc['id'],)
            ).fetchone()
            for step in source_steps.get(sec['id'], []):
                db.execute(
                    """INSERT INTO procedure_steps
                       (section_id, order_index, title, body, input_type, unit, min_value, max_value, notes_enabled)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (new_sec['id'], step['order_index'], step['title'], step['body'],
                     step['input_type'], step['unit'], step['min_value'], step['max_value'],
                     step['notes_enabled'])
                )
        db.commit()

        label = "revision" if mode == "revision" else "variant"
        flash(f"Created {label} {new_proc_id} Rev {revision}.", "success")
        return redirect(url_for("procedures.procedure_detail", id=new_proc['id']))

    # Suggest next revision letter
    cur_rev = (source['revision'] or 'A').strip().upper()
    if len(cur_rev) == 1 and cur_rev.isalpha() and cur_rev < 'Z':
        next_rev = chr(ord(cur_rev) + 1)
    else:
        next_rev = cur_rev + '1'

    next_proc_id = generate_new_procedure_id(db)
    sections, steps_by_section = get_sections_with_steps(db, id)
    step_count = sum(len(v) for v in steps_by_section.values())

    return render_template("procedure_revise.html",
                           source=source, next_rev=next_rev,
                           next_proc_id=next_proc_id,
                           section_count=len(sections), step_count=step_count)

# ---------------------------------------------------------------------------
# Section Editor
# ---------------------------------------------------------------------------

@bp.route("/<int:id>/sections", methods=["GET", "POST"])
def procedure_sections(id):
    # Legacy all-in-one editor — kept as a fallback, unlinked from the main UI.
    db = get_db()
    proc = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        if title:
            row = db.execute(
                "SELECT COALESCE(MAX(order_index), 0) as m FROM procedure_sections WHERE procedure_id=?", (id,)
            ).fetchone()
            db.execute(
                "INSERT INTO procedure_sections (procedure_id, order_index, title, description) VALUES (?, ?, ?, ?)",
                (id, row['m'] + 1, title, description)
            )
            db.commit()
            flash("Section added.", "success")

    sections, steps_by_section = get_sections_with_steps(db, id)
    open_comments = db.execute(
        "SELECT section_id, step_id FROM procedure_comments WHERE procedure_id=? AND resolved=0", (id,)
    ).fetchall()
    open_by_section = {}
    open_by_step = {}
    for c in open_comments:
        if c['section_id']:
            open_by_section[c['section_id']] = open_by_section.get(c['section_id'], 0) + 1
        if c['step_id']:
            open_by_step[c['step_id']] = open_by_step.get(c['step_id'], 0) + 1
    return render_template("procedure_sections.html", proc=proc, sections=sections,
                           steps_by_section=steps_by_section,
                           open_by_section=open_by_section, open_by_step=open_by_step)

# ---------------------------------------------------------------------------
# Per-Section Detail (redesigned workflow)
# ---------------------------------------------------------------------------

@bp.route("/<int:id>/sections/new", methods=["POST"])
def section_new(id):
    db = get_db()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if not title:
        flash("Section title is required.", "error")
        return redirect(url_for("procedures.procedure_detail", id=id))
    row = db.execute(
        "SELECT COALESCE(MAX(order_index), 0) as m FROM procedure_sections WHERE procedure_id=?", (id,)
    ).fetchone()
    db.execute(
        "INSERT INTO procedure_sections (procedure_id, order_index, title, description) VALUES (?, ?, ?, ?)",
        (id, row['m'] + 1, title, description)
    )
    db.commit()
    new_sec = db.execute(
        "SELECT id FROM procedure_sections WHERE procedure_id=? ORDER BY id DESC LIMIT 1", (id,)
    ).fetchone()
    flash("Section added.", "success")
    return redirect(url_for("procedures.section_detail", id=id, sid=new_sec['id']))

@bp.route("/<int:id>/sections/<int:sid>")
def section_detail(id, sid):
    db = get_db()
    proc = db.execute("SELECT * FROM procedures WHERE id = ?", (id,)).fetchone()
    if proc is None:
        flash("Procedure not found.", "error")
        return redirect(url_for("procedures.procedure_list"))
    section = db.execute(
        "SELECT * FROM procedure_sections WHERE id = ? AND procedure_id = ?", (sid, id)
    ).fetchone()
    if section is None:
        flash("Section not found.", "error")
        return redirect(url_for("procedures.procedure_detail", id=id))

    all_sections = db.execute(
        "SELECT id, title FROM procedure_sections WHERE procedure_id = ? ORDER BY order_index", (id,)
    ).fetchall()
    sec_ids = [s['id'] for s in all_sections]
    pos_idx  = sec_ids.index(sid) if sid in sec_ids else -1
    position = pos_idx + 1
    total    = len(sec_ids)
    prev_sid = sec_ids[pos_idx - 1] if pos_idx > 0 else None
    next_sid = sec_ids[pos_idx + 1] if 0 <= pos_idx < total - 1 else None

    steps = db.execute(
        "SELECT * FROM procedure_steps WHERE section_id = ? ORDER BY order_index", (sid,)
    ).fetchall()
    comments = db.execute(
        "SELECT * FROM procedure_comments WHERE procedure_id=? AND section_id=? ORDER BY resolved ASC, created_at DESC",
        (id, sid)
    ).fetchall()
    open_count = sum(1 for c in comments if not c['resolved'])

    return render_template("procedure_section_detail.html",
        proc=proc, section=section, steps=steps,
        comments=comments, open_count=open_count,
        position=position, total=total,
        prev_sid=prev_sid, next_sid=next_sid,
    )

@bp.route("/<int:id>/sections/<int:sid>/edit", methods=["POST"])
def section_edit(id, sid):
    db = get_db()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if title:
        db.execute(
            "UPDATE procedure_sections SET title=?, description=? WHERE id=? AND procedure_id=?",
            (title, description, sid, id)
        )
        db.commit()
        flash("Section updated.", "success")
    return redirect(url_for("procedures.section_detail", id=id, sid=sid))

@bp.route("/<int:id>/sections/<int:sid>/delete", methods=["POST"])
def section_delete(id, sid):
    db = get_db()
    db.execute("DELETE FROM procedure_steps WHERE section_id = ?", (sid,))
    db.execute("DELETE FROM procedure_sections WHERE id = ? AND procedure_id = ?", (sid, id))
    db.commit()
    flash("Section deleted.", "success")
    return redirect(url_for("procedures.procedure_detail", id=id))

# ---------------------------------------------------------------------------
# Step Editor
# ---------------------------------------------------------------------------

def _parse_step_form(form):
    title = form.get("title", "").strip()
    body = form.get("body", "").strip()
    input_type = form.get("input_type", "none").strip()
    unit = form.get("unit", "").strip()
    min_val = form.get("min_value", "").strip()
    max_val = form.get("max_value", "").strip()
    notes_enabled = 1 if form.get("notes_enabled") else 0
    min_val = float(min_val) if min_val else None
    max_val = float(max_val) if max_val else None
    return title, body, input_type, unit, min_val, max_val, notes_enabled

@bp.route("/<int:id>/sections/<int:sid>/steps", methods=["POST"])
def step_add(id, sid):
    db = get_db()
    title, body, input_type, unit, min_val, max_val, notes_enabled = _parse_step_form(request.form)
    if title:
        row = db.execute(
            "SELECT COALESCE(MAX(order_index), 0) as m FROM procedure_steps WHERE section_id=?", (sid,)
        ).fetchone()
        db.execute(
            """INSERT INTO procedure_steps
               (section_id, order_index, title, body, input_type, unit, min_value, max_value, notes_enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, row['m'] + 1, title, body, input_type, unit, min_val, max_val, notes_enabled)
        )
        db.commit()
        flash("Step added.", "success")
    return redirect(url_for("procedures.section_detail", id=id, sid=sid))

@bp.route("/<int:id>/sections/<int:sid>/steps/<int:step_id>/edit", methods=["POST"])
def step_edit(id, sid, step_id):
    db = get_db()
    title, body, input_type, unit, min_val, max_val, notes_enabled = _parse_step_form(request.form)
    if title:
        db.execute(
            """UPDATE procedure_steps
               SET title=?, body=?, input_type=?, unit=?, min_value=?, max_value=?, notes_enabled=?
               WHERE id=? AND section_id=?""",
            (title, body, input_type, unit, min_val, max_val, notes_enabled, step_id, sid)
        )
        db.commit()
        flash("Step updated.", "success")
    return redirect(url_for("procedures.section_detail", id=id, sid=sid))

@bp.route("/<int:id>/sections/<int:sid>/steps/<int:step_id>/delete", methods=["POST"])
def step_delete(id, sid, step_id):
    db = get_db()
    db.execute("DELETE FROM procedure_steps WHERE id = ? AND section_id = ?", (step_id, sid))
    db.commit()
    flash("Step deleted.", "success")
    return redirect(url_for("procedures.section_detail", id=id, sid=sid))

@bp.route("/<int:id>/sections/<int:sid>/steps/<int:step_id>/move", methods=["POST"])
def step_move(id, sid, step_id):
    db = get_db()
    direction = request.form.get("direction")
    steps = db.execute(
        "SELECT id, order_index FROM procedure_steps WHERE section_id=? ORDER BY order_index", (sid,)
    ).fetchall()
    ids = [s['id'] for s in steps]
    idx = ids.index(step_id) if step_id in ids else -1
    if direction == "up" and idx > 0:
        a, b = steps[idx], steps[idx - 1]
        db.execute("UPDATE procedure_steps SET order_index=? WHERE id=?", (b['order_index'], a['id']))
        db.execute("UPDATE procedure_steps SET order_index=? WHERE id=?", (a['order_index'], b['id']))
        db.commit()
    elif direction == "down" and 0 <= idx < len(steps) - 1:
        a, b = steps[idx], steps[idx + 1]
        db.execute("UPDATE procedure_steps SET order_index=? WHERE id=?", (b['order_index'], a['id']))
        db.execute("UPDATE procedure_steps SET order_index=? WHERE id=?", (a['order_index'], b['id']))
        db.commit()
    return redirect(url_for("procedures.section_detail", id=id, sid=sid))

# ---------------------------------------------------------------------------
# Export (placeholder)
# ---------------------------------------------------------------------------

@bp.route("/<int:id>/export/docx")
def procedure_export_docx(id):
    return "Export Logic Placeholder"

# ---------------------------------------------------------------------------
# Procedure Runner
# ---------------------------------------------------------------------------

@bp.route("/run/setup", methods=["GET", "POST"])
def run_setup():
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
    db = get_db()

    run = db.execute("""
        SELECT r.*, p.title as proc_title, p.proc_id, h.hardware_id, h.description as hw_desc
        FROM procedure_runs r
        JOIN procedures p ON r.procedure_id = p.id
        JOIN hardware h ON r.hardware_id = h.id
        WHERE r.id = ?
    """, (id,)).fetchone()

    sections, steps_by_section = get_sections_with_steps(db, run['procedure_id'])

    val_rows = db.execute("SELECT * FROM run_values WHERE run_id = ?", (id,)).fetchall()
    saved_values = {row['step_id']: row for row in val_rows}

    if request.method == "POST":
        run_notes = request.form.get("notes", "")
        action = request.form.get("action")
        status = "In-Progress" if action == "save" else request.form.get("final_result", "Completed")

        db.execute("UPDATE procedure_runs SET status=?, notes=? WHERE id=?", (status, run_notes, id))
        db.execute("DELETE FROM run_values WHERE run_id=?", (id,))

        for section in sections:
            for step in steps_by_section.get(section['id'], []):
                step_id = step['id']
                checked = 1 if request.form.get(f"check_{step_id}") else 0
                val_data = request.form.get(f"val_{step_id}", "").strip()
                step_notes = request.form.get(f"notes_{step_id}", "").strip()
                if checked or val_data or step_notes:
                    db.execute(
                        "INSERT INTO run_values (run_id, step_id, checked, value, notes) VALUES (?, ?, ?, ?, ?)",
                        (id, step_id, checked, val_data or None, step_notes or None)
                    )

        if status in ['Completed', 'Failed', 'Aborted']:
            log_desc = f"Procedure Run {run['run_id']} ({run['proc_id']}) - Status: {status}"
            now = datetime.utcnow().isoformat(timespec="seconds")
            db.execute(
                "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                (run['hardware_id'], now, "Procedure Run", log_desc)
            )

        db.commit()
        flash(f"Run {run['run_id']} saved.", "success")

        if status == 'In-Progress':
            return redirect(url_for("procedures.run_list"))
        else:
            return redirect(url_for("hardware.hardware_detail", id=run['hardware_id']))

    return render_template("run_execute.html", run=run, sections=sections,
                           steps_by_section=steps_by_section, saved_values=saved_values)

# ---------------------------------------------------------------------------
# Review Comments
# ---------------------------------------------------------------------------

@bp.route("/<int:id>/comments", methods=["POST"])
def comment_add(id):
    db = get_db()
    author_name  = request.form.get("author_name", "").strip()
    body         = request.form.get("body", "").strip()
    target_label = request.form.get("target_label", "General").strip()
    section_id   = request.form.get("section_id") or None
    step_id      = request.form.get("step_id") or None
    if author_name and body:
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            """INSERT INTO procedure_comments
               (procedure_id, section_id, step_id, target_label, author_name, body, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id, section_id, step_id, target_label, author_name, body, now)
        )
        db.commit()
        flash("Comment added.", "success")
    next_url = request.form.get("next_url", "")
    if next_url:
        return redirect(next_url + "#comments")
    return redirect(url_for("procedures.procedure_detail", id=id) + "#comments")

@bp.route("/<int:id>/comments/<int:cid>/resolve", methods=["POST"])
def comment_resolve(id, cid):
    db = get_db()
    resolved_by = request.form.get("resolved_by", "").strip() or "Author"
    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        "UPDATE procedure_comments SET resolved=1, resolved_by=?, resolved_at=? WHERE id=? AND procedure_id=?",
        (resolved_by, now, cid, id)
    )
    db.commit()
    next_url = request.form.get("next_url", "")
    if next_url:
        return redirect(next_url + "#comments")
    return redirect(url_for("procedures.procedure_detail", id=id) + "#comments")

@bp.route("/<int:id>/comments/<int:cid>/reopen", methods=["POST"])
def comment_reopen(id, cid):
    db = get_db()
    db.execute(
        "UPDATE procedure_comments SET resolved=0, resolved_by=NULL, resolved_at=NULL WHERE id=? AND procedure_id=?",
        (cid, id)
    )
    db.commit()
    next_url = request.form.get("next_url", "")
    if next_url:
        return redirect(next_url + "#comments")
    return redirect(url_for("procedures.procedure_detail", id=id) + "#comments")

@bp.route("/<int:id>/set-status", methods=["POST"])
def procedure_set_status(id):
    db = get_db()
    new_status = request.form.get("status", "").strip()
    if new_status in ("draft", "in_review", "approved"):
        db.execute("UPDATE procedures SET status=? WHERE id=?", (new_status, id))
        db.commit()
        labels = {"draft": "returned to Draft", "in_review": "sent for Review", "approved": "marked Approved"}
        flash(f"Procedure {labels.get(new_status, new_status)}.", "success")
    return redirect(url_for("procedures.procedure_detail", id=id))

# ---------------------------------------------------------------------------
# Hazard Type Settings
# ---------------------------------------------------------------------------

@bp.route("/hazards", methods=["GET", "POST"])
def hazard_settings():
    db = get_db()
    if request.method == "POST":
        name       = request.form.get("name", "").strip()
        ppe_text   = request.form.get("ppe_text", "").strip()
        color      = request.form.get("color", "#dc3545").strip()
        sort_order = request.form.get("sort_order", "0").strip()
        if name:
            db.execute(
                "INSERT OR IGNORE INTO hazard_types (name, ppe_text, color, sort_order) VALUES (?, ?, ?, ?)",
                (name, ppe_text, color, int(sort_order) if sort_order.isdigit() else 0)
            )
            db.commit()
            flash(f"Hazard type '{name}' added.", "success")
    hazards = db.execute("SELECT * FROM hazard_types ORDER BY sort_order, name").fetchall()
    return render_template("hazard_settings.html", hazards=hazards)

@bp.route("/hazards/<int:hid>/edit", methods=["POST"])
def hazard_edit(hid):
    db = get_db()
    name       = request.form.get("name", "").strip()
    ppe_text   = request.form.get("ppe_text", "").strip()
    color      = request.form.get("color", "#dc3545").strip()
    sort_order = request.form.get("sort_order", "0").strip()
    active     = 1 if request.form.get("active") else 0
    if name:
        db.execute(
            "UPDATE hazard_types SET name=?, ppe_text=?, color=?, sort_order=?, active=? WHERE id=?",
            (name, ppe_text, color, int(sort_order) if sort_order.isdigit() else 0, active, hid)
        )
        db.commit()
        flash("Hazard type updated.", "success")
    return redirect(url_for("procedures.hazard_settings"))

@bp.route("/hazards/<int:hid>/delete", methods=["POST"])
def hazard_delete(hid):
    db = get_db()
    db.execute("DELETE FROM hazard_types WHERE id = ?", (hid,))
    db.commit()
    flash("Hazard type deleted.", "success")
    return redirect(url_for("procedures.hazard_settings"))

@bp.route("/runs")
def run_list():
    db = get_db()
    runs = db.execute("""
        SELECT r.*, p.title as proc_title, p.proc_id, h.hardware_id, h.description as hw_desc
        FROM procedure_runs r
        JOIN procedures p ON r.procedure_id = p.id
        JOIN hardware h ON r.hardware_id = h.id
        ORDER BY r.timestamp DESC
    """).fetchall()
    return render_template("run_list.html", runs=runs)
