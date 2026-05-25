from datetime import datetime
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from app.db import get_db

bp = Blueprint('ha', __name__, url_prefix='/ha')

SEVERITY_LABELS = {
    1: 'Catastrophic',
    2: 'Critical',
    3: 'Marginal',
    4: 'Negligible',
}

PROBABILITY_LABELS = {
    'A': 'Frequent',
    'B': 'Probable',
    'C': 'Occasional',
    'D': 'Remote',
    'E': 'Improbable',
}

RAC_RANK = {
    '1A': 'High',     '1B': 'High',     '1C': 'High',     '1D': 'High',     '1E': 'Moderate',
    '2A': 'High',     '2B': 'High',     '2C': 'High',     '2D': 'Moderate', '2E': 'Low',
    '3A': 'High',     '3B': 'Moderate', '3C': 'Moderate', '3D': 'Low',      '3E': 'Minimal',
    '4A': 'Moderate', '4B': 'Low',      '4C': 'Low',      '4D': 'Minimal',  '4E': 'Minimal',
}

CONTROL_TYPES = ['Elimination', 'Substitution', 'Engineering', 'Administrative', 'PPE']


def refs_locked(ha, sig_map):
    if ha['status'] in ('approved', 'superseded'):
        return True
    return any(s.get('signed_date') for s in sig_map.values())


def compute_rac(severity, probability):
    if severity and probability:
        key = f"{severity}{probability}"
        return key, RAC_RANK.get(key)
    return None, None


def generate_ha_id(db):
    now = datetime.now()
    yy = f"{now.year % 100:02d}"
    row = db.execute(
        "SELECT ha_id FROM hazard_analyses WHERE ha_id LIKE ? ORDER BY ha_id DESC LIMIT 1",
        (f"HA{yy}-%",)
    ).fetchone()
    if row is None:
        seq = 1
    else:
        try:
            seq = int(row['ha_id'].split('-')[1]) + 1
        except Exception:
            seq = 1
    return f"HA{yy}-{seq:03d}"


def get_ha_or_404(db, ha_pk):
    ha = db.execute("SELECT * FROM hazard_analyses WHERE id = ?", (ha_pk,)).fetchone()
    if ha is None:
        abort(404)
    return ha


def get_hazard_or_404(db, item_id, ha_pk):
    item = db.execute(
        "SELECT * FROM hazard_items WHERE id = ? AND ha_id = ?", (item_id, ha_pk)
    ).fetchone()
    if item is None:
        abort(404)
    return item


def get_hazard_position(db, item_id, ha_pk):
    rows = db.execute(
        "SELECT id FROM hazard_items WHERE ha_id = ? ORDER BY order_index, id", (ha_pk,)
    ).fetchall()
    for i, row in enumerate(rows, 1):
        if row['id'] == item_id:
            return i
    return 0


def augment_items(items):
    result = []
    for item in items:
        init_rac, init_rank = compute_rac(item['initial_severity'], item['initial_probability'])
        final_rac, final_rank = compute_rac(item['final_severity'], item['final_probability'])
        result.append({
            **dict(item),
            'init_rac': init_rac, 'init_rank': init_rank,
            'final_rac': final_rac, 'final_rank': final_rank,
        })
    return result


# ── LIST ──────────────────────────────────────────────────────────────────────

@bp.route('/')
def ha_list():
    db = get_db()
    analyses = db.execute("""
        SELECT ha.*, COUNT(hi.id) as hazard_count
        FROM hazard_analyses ha
        LEFT JOIN hazard_items hi ON hi.ha_id = ha.id
        GROUP BY ha.id
        ORDER BY ha.created_at DESC
    """).fetchall()
    return render_template('ha_list.html', analyses=analyses)


# ── NEW ───────────────────────────────────────────────────────────────────────

@bp.route('/new', methods=['GET', 'POST'])
def ha_new():
    db = get_db()
    procedures = db.execute(
        "SELECT id, proc_id, title FROM procedures ORDER BY proc_id"
    ).fetchall()
    if request.method == 'POST':
        ha_id = generate_ha_id(db)
        now = datetime.now().isoformat(timespec='seconds')
        db.execute("""
            INSERT INTO hazard_analyses
              (ha_id, title, facility_operation, organization, preliminary_classification,
               description, scope, assumptions, linked_procedure_id, revision, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ha_id,
            request.form['title'].strip(),
            request.form.get('facility_operation', '').strip(),
            request.form.get('organization', '').strip(),
            request.form.get('preliminary_classification', '').strip(),
            request.form.get('description', '').strip(),
            request.form.get('scope', '').strip(),
            request.form.get('assumptions', '').strip(),
            request.form.get('linked_procedure_id') or None,
            request.form.get('revision', 'A').strip() or 'A',
            request.form.get('status', 'draft'),
            now, now,
        ))
        db.commit()
        row = db.execute("SELECT id FROM hazard_analyses WHERE ha_id = ?", (ha_id,)).fetchone()
        flash(f"{ha_id} created.", 'success')
        return redirect(url_for('ha.ha_detail', ha_pk=row['id']))
    return render_template('ha_form.html', ha=None, procedures=procedures)


# ── DETAIL ────────────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>')
def ha_detail(ha_pk):
    db = get_db()
    ha = get_ha_or_404(db, ha_pk)
    raw_items = db.execute(
        "SELECT * FROM hazard_items WHERE ha_id = ? ORDER BY order_index, id", (ha_pk,)
    ).fetchall()
    items = augment_items(raw_items)
    signatures = db.execute(
        "SELECT * FROM hazard_signatures WHERE ha_id = ?", (ha_pk,)
    ).fetchall()
    sig_map = {s['role']: dict(s) for s in signatures}
    references = db.execute(
        "SELECT * FROM hazard_references WHERE ha_id = ? ORDER BY sort_order, id", (ha_pk,)
    ).fetchall()
    ref_library = db.execute(
        "SELECT * FROM reference_documents ORDER BY sort_order, doc_number"
    ).fetchall()
    locked = refs_locked(ha, sig_map)
    linked_proc = None
    if ha['linked_procedure_id']:
        linked_proc = db.execute(
            "SELECT proc_id, title FROM procedures WHERE id = ?",
            (ha['linked_procedure_id'],)
        ).fetchone()
    return render_template('ha_detail.html',
        ha=ha, items=items, sig_map=sig_map, linked_proc=linked_proc,
        references=references, ref_library=ref_library, locked=locked,
        SEVERITY_LABELS=SEVERITY_LABELS, PROBABILITY_LABELS=PROBABILITY_LABELS,
    )


# ── EDIT ──────────────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/edit', methods=['GET', 'POST'])
def ha_edit(ha_pk):
    db = get_db()
    ha = get_ha_or_404(db, ha_pk)
    procedures = db.execute(
        "SELECT id, proc_id, title FROM procedures ORDER BY proc_id"
    ).fetchall()
    if request.method == 'POST':
        now = datetime.now().isoformat(timespec='seconds')
        db.execute("""
            UPDATE hazard_analyses SET
              title=?, facility_operation=?, organization=?, preliminary_classification=?,
              description=?, scope=?, assumptions=?, linked_procedure_id=?,
              revision=?, status=?, updated_at=?
            WHERE id=?
        """, (
            request.form['title'].strip(),
            request.form.get('facility_operation', '').strip(),
            request.form.get('organization', '').strip(),
            request.form.get('preliminary_classification', '').strip(),
            request.form.get('description', '').strip(),
            request.form.get('scope', '').strip(),
            request.form.get('assumptions', '').strip(),
            request.form.get('linked_procedure_id') or None,
            request.form.get('revision', 'A').strip() or 'A',
            request.form.get('status', 'draft'),
            now, ha_pk,
        ))
        db.commit()
        flash('Hazard Analysis updated.', 'success')
        return redirect(url_for('ha.ha_detail', ha_pk=ha_pk))
    return render_template('ha_form.html', ha=ha, procedures=procedures)


# ── DELETE ────────────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/delete', methods=['POST'])
def ha_delete(ha_pk):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    item_rows = db.execute("SELECT id FROM hazard_items WHERE ha_id = ?", (ha_pk,)).fetchall()
    for row in item_rows:
        db.execute("DELETE FROM hazard_controls WHERE hazard_item_id = ?", (row['id'],))
        db.execute("DELETE FROM hazard_notes WHERE hazard_item_id = ?", (row['id'],))
    db.execute("DELETE FROM hazard_items WHERE ha_id = ?", (ha_pk,))
    db.execute("DELETE FROM hazard_signatures WHERE ha_id = ?", (ha_pk,))
    db.execute("DELETE FROM hazard_references WHERE ha_id = ?", (ha_pk,))
    db.execute("DELETE FROM hazard_analyses WHERE id = ?", (ha_pk,))
    db.commit()
    flash('Hazard Analysis deleted.', 'success')
    return redirect(url_for('ha.ha_list'))


# ── SIGNATURES ────────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/signatures', methods=['POST'])
def ha_signatures(ha_pk):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    for role in ('prepared_by', 'safety_review', 'risk_acceptance'):
        name = request.form.get(f'{role}_name', '').strip()
        org  = request.form.get(f'{role}_org',  '').strip()
        date = request.form.get(f'{role}_date', '').strip()
        existing = db.execute(
            "SELECT id FROM hazard_signatures WHERE ha_id = ? AND role = ?", (ha_pk, role)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE hazard_signatures SET signer_name=?, signer_org=?, signed_date=? WHERE id=?",
                (name, org, date, existing['id'])
            )
        else:
            db.execute(
                "INSERT INTO hazard_signatures (ha_id, role, signer_name, signer_org, signed_date) VALUES (?,?,?,?,?)",
                (ha_pk, role, name, org, date)
            )
    db.commit()
    flash('Signatures saved.', 'success')
    return redirect(url_for('ha.ha_detail', ha_pk=ha_pk) + '#signatures')


# ── HAZARD NEW ────────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/new', methods=['GET', 'POST'])
def hazard_new(ha_pk):
    db = get_db()
    ha = get_ha_or_404(db, ha_pk)
    if request.method == 'POST':
        row = db.execute(
            "SELECT MAX(order_index) as mx FROM hazard_items WHERE ha_id = ?", (ha_pk,)
        ).fetchone()
        next_idx = (row['mx'] or 0) + 1
        db.execute("""
            INSERT INTO hazard_items
              (ha_id, order_index, hazard_description, cause, consequence,
               initial_severity, initial_probability, final_severity, final_probability, closed)
            VALUES (?,?,?,?,?,?,?,?,?,0)
        """, (
            ha_pk, next_idx,
            request.form['hazard_description'].strip(),
            request.form.get('cause', '').strip(),
            request.form.get('consequence', '').strip(),
            request.form.get('initial_severity') or None,
            request.form.get('initial_probability') or None,
            request.form.get('final_severity') or None,
            request.form.get('final_probability') or None,
        ))
        db.commit()
        item_id = db.execute("SELECT last_insert_rowid() as id").fetchone()['id']
        flash('Hazard added.', 'success')
        return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id))
    return render_template('ha_hazard_form.html', ha=ha, item=None,
                           SEVERITY_LABELS=SEVERITY_LABELS, PROBABILITY_LABELS=PROBABILITY_LABELS)


# ── HAZARD DETAIL ─────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/<int:item_id>')
def hazard_detail(ha_pk, item_id):
    db = get_db()
    ha = get_ha_or_404(db, ha_pk)
    item = get_hazard_or_404(db, item_id, ha_pk)
    position = get_hazard_position(db, item_id, ha_pk)
    raw_recs = db.execute(
        "SELECT * FROM hazard_recommendations WHERE hazard_item_id = ? ORDER BY order_index, id",
        (item_id,)
    ).fetchall()
    recommendations = []
    for rec in raw_recs:
        ctrls = db.execute(
            "SELECT * FROM hazard_controls WHERE recommendation_id = ? ORDER BY order_index, id",
            (rec['id'],)
        ).fetchall()
        recommendations.append({'rec': rec, 'controls': ctrls})
    notes = db.execute(
        "SELECT * FROM hazard_notes WHERE hazard_item_id = ? ORDER BY created_at",
        (item_id,)
    ).fetchall()
    # Adjacent hazard navigation
    all_ids = [r['id'] for r in db.execute(
        "SELECT id FROM hazard_items WHERE ha_id = ? ORDER BY order_index, id", (ha_pk,)
    ).fetchall()]
    pos_idx = all_ids.index(item_id) if item_id in all_ids else -1
    prev_id = all_ids[pos_idx - 1] if pos_idx > 0 else None
    next_id = all_ids[pos_idx + 1] if pos_idx >= 0 and pos_idx < len(all_ids) - 1 else None

    init_rac, init_rank = compute_rac(item['initial_severity'], item['initial_probability'])
    final_rac, final_rank = compute_rac(item['final_severity'], item['final_probability'])
    return render_template('ha_hazard_detail.html',
        ha=ha, item=item, position=position,
        recommendations=recommendations, notes=notes,
        prev_id=prev_id, next_id=next_id,
        init_rac=init_rac, init_rank=init_rank,
        final_rac=final_rac, final_rank=final_rank,
        SEVERITY_LABELS=SEVERITY_LABELS, PROBABILITY_LABELS=PROBABILITY_LABELS,
        CONTROL_TYPES=CONTROL_TYPES,
    )


# ── HAZARD EDIT ───────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/<int:item_id>/edit', methods=['GET', 'POST'])
def hazard_edit(ha_pk, item_id):
    db = get_db()
    ha = get_ha_or_404(db, ha_pk)
    item = get_hazard_or_404(db, item_id, ha_pk)
    if request.method == 'POST':
        db.execute("""
            UPDATE hazard_items SET
              hazard_description=?, cause=?, consequence=?,
              initial_severity=?, initial_probability=?,
              final_severity=?, final_probability=?
            WHERE id=?
        """, (
            request.form['hazard_description'].strip(),
            request.form.get('cause', '').strip(),
            request.form.get('consequence', '').strip(),
            request.form.get('initial_severity') or None,
            request.form.get('initial_probability') or None,
            request.form.get('final_severity') or None,
            request.form.get('final_probability') or None,
            item_id,
        ))
        db.commit()
        flash('Hazard updated.', 'success')
        return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id))
    return render_template('ha_hazard_form.html', ha=ha, item=item,
                           SEVERITY_LABELS=SEVERITY_LABELS, PROBABILITY_LABELS=PROBABILITY_LABELS)


# ── HAZARD DELETE ─────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/<int:item_id>/delete', methods=['POST'])
def hazard_delete(ha_pk, item_id):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    get_hazard_or_404(db, item_id, ha_pk)
    rec_rows = db.execute("SELECT id FROM hazard_recommendations WHERE hazard_item_id = ?", (item_id,)).fetchall()
    for rec in rec_rows:
        db.execute("DELETE FROM hazard_controls WHERE recommendation_id = ?", (rec['id'],))
    db.execute("DELETE FROM hazard_recommendations WHERE hazard_item_id = ?", (item_id,))
    db.execute("DELETE FROM hazard_controls WHERE hazard_item_id = ?", (item_id,))
    db.execute("DELETE FROM hazard_notes WHERE hazard_item_id = ?", (item_id,))
    db.execute("DELETE FROM hazard_items WHERE id = ?", (item_id,))
    db.commit()
    flash('Hazard removed.', 'success')
    return redirect(url_for('ha.ha_detail', ha_pk=ha_pk))


# ── HAZARD CLOSE TOGGLE ───────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/<int:item_id>/close', methods=['POST'])
def hazard_close(ha_pk, item_id):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    item = get_hazard_or_404(db, item_id, ha_pk)
    db.execute("UPDATE hazard_items SET closed=? WHERE id=?", (0 if item['closed'] else 1, item_id))
    db.commit()
    return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id))


# ── NOTES ─────────────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/<int:item_id>/notes', methods=['POST'])
def note_add(ha_pk, item_id):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    get_hazard_or_404(db, item_id, ha_pk)
    author = request.form.get('author', '').strip()
    body   = request.form.get('body', '').strip()
    if author and body:
        db.execute(
            "INSERT INTO hazard_notes (hazard_item_id, author, body, created_at) VALUES (?,?,?,?)",
            (item_id, author, body, datetime.now().isoformat(timespec='seconds'))
        )
        db.commit()
    return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id) + '#notes')


# ── RECOMMENDATIONS ───────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/<int:item_id>/recs/add', methods=['POST'])
def rec_add(ha_pk, item_id):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    get_hazard_or_404(db, item_id, ha_pk)
    text = request.form.get('text', '').strip()
    if text:
        row = db.execute(
            "SELECT MAX(order_index) as mx FROM hazard_recommendations WHERE hazard_item_id=?", (item_id,)
        ).fetchone()
        next_idx = (row['mx'] or 0) + 1
        db.execute(
            "INSERT INTO hazard_recommendations (hazard_item_id, order_index, text) VALUES (?,?,?)",
            (item_id, next_idx, text)
        )
        db.commit()
    return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id) + '#controls')


@bp.route('/<int:ha_pk>/hazards/<int:item_id>/recs/<int:rec_id>/delete', methods=['POST'])
def rec_delete(ha_pk, item_id, rec_id):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    get_hazard_or_404(db, item_id, ha_pk)
    db.execute("DELETE FROM hazard_controls WHERE recommendation_id = ?", (rec_id,))
    db.execute("DELETE FROM hazard_recommendations WHERE id=? AND hazard_item_id=?", (rec_id, item_id))
    db.commit()
    return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id) + '#controls')


# ── CONTROLS ──────────────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/hazards/<int:item_id>/recs/<int:rec_id>/controls/add', methods=['POST'])
def control_add(ha_pk, item_id, rec_id):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    get_hazard_or_404(db, item_id, ha_pk)
    rec = db.execute(
        "SELECT id FROM hazard_recommendations WHERE id=? AND hazard_item_id=?", (rec_id, item_id)
    ).fetchone()
    if not rec:
        abort(404)
    row = db.execute(
        "SELECT MAX(order_index) as mx FROM hazard_controls WHERE recommendation_id=?", (rec_id,)
    ).fetchone()
    next_idx = (row['mx'] or 0) + 1
    desc = request.form.get('description', '').strip()
    if desc:
        db.execute("""
            INSERT INTO hazard_controls
              (hazard_item_id, recommendation_id, order_index, control_type, description, verification)
            VALUES (?,?,?,?,?,?)
        """, (
            item_id, rec_id, next_idx,
            request.form.get('control_type', '').strip(),
            desc,
            request.form.get('verification', '').strip(),
        ))
        db.commit()
    return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id) + '#controls')


@bp.route('/<int:ha_pk>/hazards/<int:item_id>/recs/<int:rec_id>/controls/<int:ctrl_id>/delete', methods=['POST'])
def control_delete(ha_pk, item_id, rec_id, ctrl_id):
    db = get_db()
    get_ha_or_404(db, ha_pk)
    get_hazard_or_404(db, item_id, ha_pk)
    db.execute("DELETE FROM hazard_controls WHERE id=? AND recommendation_id=?", (ctrl_id, rec_id))
    db.commit()
    return redirect(url_for('ha.hazard_detail', ha_pk=ha_pk, item_id=item_id) + '#controls')


# ── REFERENCE LIBRARY (config) ────────────────────────────────────────────────

@bp.route('/ref-docs')
def ref_docs_list():
    db = get_db()
    docs = db.execute(
        "SELECT * FROM reference_documents ORDER BY sort_order, doc_number"
    ).fetchall()
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('ref_docs_config.html', docs=docs, today=today)


@bp.route('/ref-docs/add', methods=['POST'])
def ref_doc_add():
    db = get_db()
    doc_number      = request.form.get('doc_number', '').strip()
    title           = request.form.get('title', '').strip()
    revision        = request.form.get('revision', '').strip()
    description     = request.form.get('description', '').strip()
    effective_date  = request.form.get('effective_date', '').strip()
    expiration_date = request.form.get('expiration_date', '').strip()
    if doc_number and title:
        row = db.execute("SELECT MAX(sort_order) as mx FROM reference_documents").fetchone()
        next_order = (row['mx'] or 0) + 1
        db.execute(
            "INSERT INTO reference_documents"
            " (doc_number, title, revision, description, effective_date, expiration_date, sort_order)"
            " VALUES (?,?,?,?,?,?,?)",
            (doc_number, title, revision or None, description or None,
             effective_date or None, expiration_date or None, next_order)
        )
        db.commit()
        flash(f'"{doc_number}" added to reference library.', 'success')
    return redirect(url_for('ha.ref_docs_list'))


@bp.route('/ref-docs/<int:doc_id>/edit', methods=['POST'])
def ref_doc_edit(doc_id):
    db = get_db()
    doc_number      = request.form.get('doc_number', '').strip()
    title           = request.form.get('title', '').strip()
    revision        = request.form.get('revision', '').strip()
    description     = request.form.get('description', '').strip()
    effective_date  = request.form.get('effective_date', '').strip()
    expiration_date = request.form.get('expiration_date', '').strip()
    if doc_number and title:
        db.execute(
            "UPDATE reference_documents"
            " SET doc_number=?, title=?, revision=?, description=?, effective_date=?, expiration_date=?"
            " WHERE id=?",
            (doc_number, title, revision or None, description or None,
             effective_date or None, expiration_date or None, doc_id)
        )
        db.commit()
        flash('Reference document updated.', 'success')
    return redirect(url_for('ha.ref_docs_list'))


@bp.route('/ref-docs/<int:doc_id>/delete', methods=['POST'])
def ref_doc_delete(doc_id):
    db = get_db()
    row = db.execute("SELECT * FROM reference_documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        return redirect(url_for('ha.ref_docs_list'))
    in_use = db.execute(
        "SELECT COUNT(*) FROM hazard_references WHERE ref_doc_id = ?", (doc_id,)
    ).fetchone()[0]
    if in_use > 0:
        flash(
            f'Cannot delete "{row["doc_number"]}" — it is cited in {in_use} hazard analysis reference(s).',
            'error'
        )
        return redirect(url_for('ha.ref_docs_list'))
    db.execute("DELETE FROM reference_documents WHERE id = ?", (doc_id,))
    db.commit()
    flash(f'"{row["doc_number"]}" removed from reference library.', 'success')
    return redirect(url_for('ha.ref_docs_list'))


# ── PER-HA REFERENCES ─────────────────────────────────────────────────────────

@bp.route('/<int:ha_pk>/refs/add', methods=['POST'])
def ha_ref_add(ha_pk):
    db = get_db()
    ha = get_ha_or_404(db, ha_pk)
    signatures = db.execute("SELECT * FROM hazard_signatures WHERE ha_id = ?", (ha_pk,)).fetchall()
    sig_map = {s['role']: dict(s) for s in signatures}
    if refs_locked(ha, sig_map):
        flash('This hazard analysis is locked — references cannot be modified.', 'error')
        return redirect(url_for('ha.ha_detail', ha_pk=ha_pk) + '#references')
    doc_number    = request.form.get('doc_number', '').strip()
    title         = request.form.get('title', '').strip()
    revision      = request.form.get('revision', '').strip()
    section_cited = request.form.get('section_cited', '').strip()
    ref_doc_id    = request.form.get('ref_doc_id') or None
    if not doc_number or not title:
        flash('Document number and title are required.', 'error')
        return redirect(url_for('ha.ha_detail', ha_pk=ha_pk) + '#references')
    row = db.execute(
        "SELECT MAX(sort_order) as mx FROM hazard_references WHERE ha_id = ?", (ha_pk,)
    ).fetchone()
    next_order = (row['mx'] or 0) + 1
    db.execute(
        "INSERT INTO hazard_references (ha_id, ref_doc_id, doc_number, title, revision, section_cited, sort_order)"
        " VALUES (?,?,?,?,?,?,?)",
        (ha_pk, ref_doc_id, doc_number, title, revision or None, section_cited or None, next_order)
    )
    db.commit()
    flash('Reference added.', 'success')
    return redirect(url_for('ha.ha_detail', ha_pk=ha_pk) + '#references')


@bp.route('/<int:ha_pk>/refs/<int:ref_id>/delete', methods=['POST'])
def ha_ref_delete(ha_pk, ref_id):
    db = get_db()
    ha = get_ha_or_404(db, ha_pk)
    signatures = db.execute("SELECT * FROM hazard_signatures WHERE ha_id = ?", (ha_pk,)).fetchall()
    sig_map = {s['role']: dict(s) for s in signatures}
    if refs_locked(ha, sig_map):
        flash('This hazard analysis is locked — references cannot be modified.', 'error')
        return redirect(url_for('ha.ha_detail', ha_pk=ha_pk) + '#references')
    db.execute("DELETE FROM hazard_references WHERE id = ? AND ha_id = ?", (ref_id, ha_pk))
    db.commit()
    return redirect(url_for('ha.ha_detail', ha_pk=ha_pk) + '#references')
