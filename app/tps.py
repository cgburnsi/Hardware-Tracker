from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.db import get_db

bp = Blueprint('tps', __name__, url_prefix='/tps')

APPROVAL_ROLES = [
    'Prepared By', 'Test Engineer', 'Design Engineer',
    'Safety', 'Quality', 'Environmental Health', 'Lead Engineer', 'Other',
]

def generate_tps_id(db):
    yy = f"{datetime.now().year % 100:02d}"
    row = db.execute(
        "SELECT tps_number FROM tps WHERE tps_number LIKE ? ORDER BY tps_number DESC LIMIT 1",
        (f"TPS{yy}-%",)
    ).fetchone()
    if row is None:
        seq = 1
    else:
        try:
            seq = int(row['tps_number'].split('-')[1]) + 1
        except Exception:
            seq = 1
    return f"TPS{yy}-{seq:03d}"

def _tps_form_save(db, id=None):
    """Extract TPS header fields from request.form. Returns a dict ready for INSERT/UPDATE."""
    return dict(
        tps_number=request.form.get('tps_number', '').strip(),
        title=request.form.get('title', '').strip(),
        tps_type=request.form.get('tps_type', 'B'),
        quality_sensitive=1 if request.form.get('quality_sensitive') else 0,
        safety_critical=1 if request.form.get('safety_critical') else 0,
        limited_life=1 if request.form.get('limited_life') else 0,
        experiment_number=request.form.get('experiment_number', '').strip() or None,
        date_prepared=request.form.get('date_prepared', '').strip() or None,
        need_date=request.form.get('need_date', '').strip() or None,
        reference_docs=request.form.get('reference_docs', '').strip() or None,
        initiating_org=request.form.get('initiating_org', 'ER64').strip(),
        system_name=request.form.get('system_name', '').strip() or None,
        reason_for_work=request.form.get('reason_for_work', '').strip() or None,
        special_notes=request.form.get('special_notes', '').strip() or None,
        prepared_by=request.form.get('prepared_by', '').strip() or None,
        linked_procedure_id=request.form.get('linked_procedure_id') or None,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@bp.route('/')
def tps_list():
    db = get_db()
    q = request.args.get('q', '').strip()
    status_f = request.args.get('status', '').strip()
    query = "SELECT * FROM tps WHERE 1=1"
    params = []
    if q:
        query += " AND (tps_number LIKE ? OR title LIKE ? OR system_name LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if status_f:
        query += " AND status=?"
        params.append(status_f)
    query += " ORDER BY created_at DESC"
    items = db.execute(query, params).fetchall()
    return render_template('tps_list.html', items=items, q=q, status_f=status_f)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@bp.route('/new', methods=['GET', 'POST'])
def tps_new():
    db = get_db()
    procedures = db.execute(
        "SELECT id, proc_id, title FROM procedures ORDER BY proc_id"
    ).fetchall()

    if request.method == 'POST':
        f = _tps_form_save(db)
        if not f['tps_number']:
            f['tps_number'] = generate_tps_id(db)
        if not f['title']:
            flash("Title is required.", "error")
            return render_template('tps_form.html', item=None, procedures=procedures,
                                   roles=APPROVAL_ROLES, default_number=generate_tps_id(db))
        now = datetime.utcnow().isoformat(timespec='seconds')
        try:
            db.execute("""
                INSERT INTO tps (tps_number, title, tps_type,
                    quality_sensitive, safety_critical, limited_life,
                    experiment_number, date_prepared, need_date, reference_docs,
                    initiating_org, system_name, reason_for_work, special_notes,
                    prepared_by, linked_procedure_id, status, created_at, updated_at)
                VALUES (:tps_number,:title,:tps_type,
                    :quality_sensitive,:safety_critical,:limited_life,
                    :experiment_number,:date_prepared,:need_date,:reference_docs,
                    :initiating_org,:system_name,:reason_for_work,:special_notes,
                    :prepared_by,:linked_procedure_id,'draft',:now,:now)
            """, {**f, 'now': now})
            db.commit()
        except Exception as e:
            flash(f"Could not create TPS: {e}", "error")
            return render_template('tps_form.html', item=None, procedures=procedures,
                                   roles=APPROVAL_ROLES, default_number=f['tps_number'])
        row = db.execute("SELECT id FROM tps WHERE tps_number=?", (f['tps_number'],)).fetchone()
        flash(f"TPS {f['tps_number']} created.", "success")
        return redirect(url_for('tps.tps_detail', id=row['id']))

    return render_template('tps_form.html', item=None, procedures=procedures,
                           roles=APPROVAL_ROLES, default_number=generate_tps_id(db))


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@bp.route('/<int:id>')
def tps_detail(id):
    db = get_db()
    item = db.execute("SELECT * FROM tps WHERE id=?", (id,)).fetchone()
    if item is None:
        flash("TPS not found.", "error")
        return redirect(url_for('tps.tps_list'))
    steps = db.execute(
        "SELECT * FROM tps_steps WHERE tps_id=? ORDER BY order_index", (id,)
    ).fetchall()
    approvals = db.execute(
        "SELECT * FROM tps_approvals WHERE tps_id=? ORDER BY id", (id,)
    ).fetchall()
    procedures = db.execute(
        "SELECT id, proc_id, title FROM procedures ORDER BY proc_id"
    ).fetchall()
    total = len(steps)
    completed = sum(1 for s in steps if s['result'] is not None)
    return render_template('tps_detail.html', item=item, steps=steps, approvals=approvals,
                           procedures=procedures, roles=APPROVAL_ROLES,
                           total=total, completed=completed)


# ---------------------------------------------------------------------------
# Edit header
# ---------------------------------------------------------------------------

@bp.route('/<int:id>/edit', methods=['POST'])
def tps_edit(id):
    db = get_db()
    item = db.execute("SELECT * FROM tps WHERE id=?", (id,)).fetchone()
    if item is None:
        return redirect(url_for('tps.tps_list'))
    f = _tps_form_save(db, id)
    f['tps_number'] = item['tps_number']  # number is immutable after creation
    if not f['title']:
        flash("Title is required.", "error")
        return redirect(url_for('tps.tps_detail', id=id))
    now = datetime.utcnow().isoformat(timespec='seconds')
    db.execute("""
        UPDATE tps SET tps_number=:tps_number, title=:title, tps_type=:tps_type,
            quality_sensitive=:quality_sensitive, safety_critical=:safety_critical,
            limited_life=:limited_life, experiment_number=:experiment_number,
            date_prepared=:date_prepared, need_date=:need_date,
            reference_docs=:reference_docs, initiating_org=:initiating_org,
            system_name=:system_name, reason_for_work=:reason_for_work,
            special_notes=:special_notes, prepared_by=:prepared_by,
            linked_procedure_id=:linked_procedure_id, updated_at=:now
        WHERE id=:id
    """, {**f, 'now': now, 'id': id})
    db.commit()
    flash("TPS updated.", "success")
    return redirect(url_for('tps.tps_detail', id=id))


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

@bp.route('/<int:id>/set-status', methods=['POST'])
def tps_set_status(id):
    db = get_db()
    new_status = request.form.get('status', '')
    if new_status in {'draft', 'approved', 'in_progress', 'complete', 'voided'}:
        now = datetime.utcnow().isoformat(timespec='seconds')
        db.execute("UPDATE tps SET status=?, updated_at=? WHERE id=?", (new_status, now, id))
        db.commit()
    return redirect(url_for('tps.tps_detail', id=id))


# ---------------------------------------------------------------------------
# Steps — editing (draft only)
# ---------------------------------------------------------------------------

@bp.route('/<int:id>/steps/add', methods=['POST'])
def step_add(id):
    db = get_db()
    description = request.form.get('description', '').strip()
    if not description:
        flash("Step description is required.", "error")
        return redirect(url_for('tps.tps_detail', id=id) + '#steps')
    max_row = db.execute(
        "SELECT MAX(order_index) FROM tps_steps WHERE tps_id=?", (id,)
    ).fetchone()
    next_idx = (max_row[0] or 0) + 1
    db.execute("""
        INSERT INTO tps_steps (tps_id, order_index, description, input_type, unit, min_value, max_value)
        VALUES (?,?,?,?,?,?,?)
    """, (
        id, next_idx, description,
        request.form.get('input_type', 'none'),
        request.form.get('unit', '').strip() or None,
        request.form.get('min_value') or None,
        request.form.get('max_value') or None,
    ))
    db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#steps')


@bp.route('/<int:id>/steps/<int:sid>/edit', methods=['POST'])
def step_edit(id, sid):
    db = get_db()
    description = request.form.get('description', '').strip()
    if not description:
        flash("Description is required.", "error")
        return redirect(url_for('tps.tps_detail', id=id) + '#steps')
    db.execute("""
        UPDATE tps_steps SET description=?, input_type=?, unit=?, min_value=?, max_value=?
        WHERE id=? AND tps_id=?
    """, (
        description,
        request.form.get('input_type', 'none'),
        request.form.get('unit', '').strip() or None,
        request.form.get('min_value') or None,
        request.form.get('max_value') or None,
        sid, id,
    ))
    db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#steps')


@bp.route('/<int:id>/steps/<int:sid>/delete', methods=['POST'])
def step_delete(id, sid):
    db = get_db()
    db.execute("DELETE FROM tps_steps WHERE id=? AND tps_id=?", (sid, id))
    steps = db.execute(
        "SELECT id FROM tps_steps WHERE tps_id=? ORDER BY order_index", (id,)
    ).fetchall()
    for i, s in enumerate(steps):
        db.execute("UPDATE tps_steps SET order_index=? WHERE id=?", (i + 1, s['id']))
    db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#steps')


@bp.route('/<int:id>/steps/<int:sid>/move', methods=['POST'])
def step_move(id, sid):
    db = get_db()
    direction = request.form.get('direction', 'up')
    step = db.execute(
        "SELECT * FROM tps_steps WHERE id=? AND tps_id=?", (sid, id)
    ).fetchone()
    if step is None:
        return redirect(url_for('tps.tps_detail', id=id) + '#steps')
    if direction == 'up':
        neighbor = db.execute(
            "SELECT * FROM tps_steps WHERE tps_id=? AND order_index<? ORDER BY order_index DESC LIMIT 1",
            (id, step['order_index'])
        ).fetchone()
    else:
        neighbor = db.execute(
            "SELECT * FROM tps_steps WHERE tps_id=? AND order_index>? ORDER BY order_index ASC LIMIT 1",
            (id, step['order_index'])
        ).fetchone()
    if neighbor:
        db.execute("UPDATE tps_steps SET order_index=? WHERE id=?", (neighbor['order_index'], sid))
        db.execute("UPDATE tps_steps SET order_index=? WHERE id=?", (step['order_index'], neighbor['id']))
        db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#steps')


# ---------------------------------------------------------------------------
# Steps — execution
# ---------------------------------------------------------------------------

@bp.route('/<int:id>/steps/<int:sid>/execute', methods=['POST'])
def step_execute(id, sid):
    db = get_db()
    result = request.form.get('result', '').strip() or None
    now = datetime.utcnow().isoformat(timespec='seconds')
    db.execute("""
        UPDATE tps_steps
        SET result=?, tech_initial=?, recorded_value=?, step_notes=?, completed_at=?
        WHERE id=? AND tps_id=?
    """, (
        result,
        request.form.get('tech_initial', '').strip() or None,
        request.form.get('recorded_value', '').strip() or None,
        request.form.get('step_notes', '').strip() or None,
        now if result else None,
        sid, id,
    ))
    # Auto-advance status: approved → in_progress on first step completion
    tps = db.execute("SELECT status FROM tps WHERE id=?", (id,)).fetchone()
    if tps and tps['status'] == 'approved' and result:
        db.execute("UPDATE tps SET status='in_progress', updated_at=? WHERE id=?", (now, id))
    db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#steps')


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@bp.route('/<int:id>/approve', methods=['POST'])
def tps_approve(id):
    db = get_db()
    role = request.form.get('role', '').strip()
    signer_name = request.form.get('signer_name', '').strip()
    signed_date = request.form.get('signed_date', '').strip() or None
    if role and signer_name:
        db.execute(
            "INSERT INTO tps_approvals (tps_id, role, signer_name, signed_date) VALUES (?,?,?,?)",
            (id, role, signer_name, signed_date)
        )
        db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#approvals')


@bp.route('/<int:id>/approve/<int:aid>/delete', methods=['POST'])
def approval_delete(id, aid):
    db = get_db()
    db.execute("DELETE FROM tps_approvals WHERE id=? AND tps_id=?", (aid, id))
    db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#approvals')


# ---------------------------------------------------------------------------
# Final acceptance
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

@bp.route('/<int:id>/refs/add', methods=['POST'])
def ref_add(id):
    db = get_db()
    ref_type = request.form.get('ref_type', '').strip()
    linked_id = request.form.get('linked_id', '').strip()
    if ref_type in ('hardware', 'procedure') and linked_id:
        existing = db.execute(
            "SELECT id FROM tps_references WHERE tps_id=? AND ref_type=? AND linked_id=?",
            (id, ref_type, int(linked_id))
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO tps_references (tps_id, ref_type, linked_id) VALUES (?,?,?)",
                (id, ref_type, int(linked_id))
            )
            db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#references')


@bp.route('/<int:id>/refs/<int:rid>/delete', methods=['POST'])
def ref_delete(id, rid):
    db = get_db()
    db.execute("DELETE FROM tps_references WHERE id=? AND tps_id=?", (rid, id))
    db.commit()
    return redirect(url_for('tps.tps_detail', id=id) + '#references')


@bp.route('/<int:id>/accept', methods=['POST'])
def tps_accept(id):
    db = get_db()
    accepted_by = request.form.get('final_accepted_by', '').strip()
    acc_date = (request.form.get('acceptance_date', '').strip()
                or datetime.utcnow().strftime('%Y-%m-%d'))
    if accepted_by:
        now = datetime.utcnow().isoformat(timespec='seconds')
        db.execute("""
            UPDATE tps SET final_accepted_by=?, acceptance_date=?, status='complete', updated_at=?
            WHERE id=?
        """, (accepted_by, acc_date, now, id))
        db.commit()
        flash("TPS accepted and marked complete.", "success")
    return redirect(url_for('tps.tps_detail', id=id))
