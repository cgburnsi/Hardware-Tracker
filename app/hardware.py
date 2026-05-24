import json
import os
import uuid
from datetime import datetime
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename
from app.db import get_db

_ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
_ALLOWED_DOC_EXT = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'csv', 'dwg', 'dxf', 'zip', 'png', 'jpg', 'jpeg',
}

def _upload_folder():
    folder = os.path.join(current_app.instance_path, 'uploads')
    os.makedirs(folder, exist_ok=True)
    return folder

def _save_image(file, hardware_id):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        return None
    filename = f"{hardware_id}.{ext}"
    file.save(os.path.join(_upload_folder(), filename))
    return filename

def _delete_image_file(filename):
    if filename:
        path = os.path.join(_upload_folder(), filename)
        if os.path.exists(path):
            os.remove(path)

def _doc_folder():
    folder = os.path.join(current_app.instance_path, 'uploads', 'docs')
    os.makedirs(folder, exist_ok=True)
    return folder

def _save_doc(file, hardware_id):
    """Save uploaded document. Returns (stored_name, original_name) or (None, None)."""
    if not file or not file.filename:
        return None, None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in _ALLOWED_DOC_EXT:
        return None, None
    stored_name = f"{hardware_id}_{uuid.uuid4().hex[:8]}.{ext}"
    file.save(os.path.join(_doc_folder(), stored_name))
    return stored_name, file.filename

bp = Blueprint('hardware', __name__, url_prefix='/hardware')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_new_hardware_id(db):
    """Generate next HYYXXX ID based on current year and existing records."""
    now = datetime.now()
    yy = f"{now.year % 100:02d}"

    # Find max XXX for this year
    cur = db.execute(
        "SELECT hardware_id FROM hardware WHERE hardware_id LIKE ? ORDER BY hardware_id DESC LIMIT 1",
        (f"H{yy}%",)
    )
    row = cur.fetchone()
    
    if row is None:
        seq = 1
    else:
        # e.g. H25027 -> take last 3 chars -> int
        try:
            seq = int(row["hardware_id"][-3:]) + 1
        except ValueError:
            seq = 1

    return f"H{yy}{seq:03d}"

def get_dropdown_data(db):
    """Helper to fetch all controlled lists for the form."""
    return {
        'manufacturers': db.execute("SELECT name FROM manufacturers ORDER BY name").fetchall(),
        'custodians': db.execute("SELECT name FROM custodians ORDER BY name").fetchall(),
        'locations': db.execute("SELECT name FROM locations ORDER BY name").fetchall(),
        'media': db.execute("SELECT name FROM media ORDER BY name").fetchall(),
        'port_configs': db.execute("SELECT name FROM port_configs ORDER BY name").fetchall(),
        'categories': db.execute("SELECT name FROM categories ORDER BY name").fetchall(),
        'cleaning_specs': db.execute("SELECT name FROM cleaning_specs ORDER BY name").fetchall(),
        'ctns': db.execute("SELECT name FROM ctns ORDER BY name").fetchall(),
        'ecns': db.execute("SELECT name FROM ecns ORDER BY name").fetchall(),
        'calibration_ids': db.execute("SELECT name FROM calibration_ids ORDER BY name").fetchall(),
        'repair_ids': db.execute("SELECT name FROM repair_ids ORDER BY name").fetchall(),
        'part_numbers': db.execute("SELECT name FROM part_numbers ORDER BY name").fetchall(),
        'other_specs': db.execute("SELECT name FROM other_specs ORDER BY name").fetchall(),
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

SORT_COLS = {'hardware_id', 'description', 'classification', 'category', 'status', 'quantity', 'location', 'manufacturer'}
_VALID_PER_PAGE = (10, 25, 50, 100)

@bp.route("/")
def hardware_list():
    db = get_db()
    q            = request.args.get("q", "").strip()
    category     = request.args.get("category", "").strip()
    status       = request.args.get("status", "").strip()
    location     = request.args.get("location", "").strip()
    classification = request.args.get("classification", "").strip()
    manufacturer = request.args.get("manufacturer", "").strip()
    kits_only    = request.args.get("kits_only", "")
    low_stock    = request.args.get("low_stock", "")
    sort         = request.args.get("sort", "hardware_id").strip()
    order        = request.args.get("order", "desc").strip()
    per_page_raw = request.args.get("per_page", "25").strip()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    if sort not in SORT_COLS:
        sort = "hardware_id"
    if order not in ("asc", "desc"):
        order = "desc"
    if per_page_raw == "all":
        per_page = 0
    else:
        try:
            per_page = int(per_page_raw)
            if per_page not in _VALID_PER_PAGE:
                per_page = 25
        except ValueError:
            per_page = 25

    conditions = "WHERE 1=1"
    params = []

    if q:
        conditions += " AND (hardware_id LIKE ? OR description LIKE ? OR part_number LIKE ? OR ecn LIKE ? OR manufacturer LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like, like])
    if category:
        conditions += " AND category = ?"; params.append(category)
    if status:
        conditions += " AND status = ?"; params.append(status)
    if location:
        conditions += " AND location = ?"; params.append(location)
    if classification:
        conditions += " AND classification = ?"; params.append(classification)
    if manufacturer:
        conditions += " AND manufacturer = ?"; params.append(manufacturer)
    if kits_only:
        conditions += " AND id IN (SELECT DISTINCT kit_hardware_id FROM kit_items)"
    if low_stock:
        conditions += " AND COALESCE(quantity, 1) <= 2"

    total = db.execute(f"SELECT COUNT(*) FROM hardware {conditions}", params).fetchone()[0]

    if per_page > 0:
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page
        items = db.execute(
            f"SELECT * FROM hardware {conditions} ORDER BY {sort} {order.upper()} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()
    else:
        total_pages = 1
        page = 1
        items = db.execute(
            f"SELECT * FROM hardware {conditions} ORDER BY {sort} {order.upper()}",
            params
        ).fetchall()

    # Build page list for pagination controls (None = ellipsis)
    if total_pages <= 7:
        page_list = list(range(1, total_pages + 1))
    else:
        visible = sorted({1, total_pages} | set(range(max(1, page - 2), min(total_pages, page + 2) + 1)))
        page_list = []
        for i, p in enumerate(visible):
            if i > 0 and p > visible[i - 1] + 1:
                page_list.append(None)
            page_list.append(p)

    def distinct(col):
        return [r[0] for r in db.execute(
            f"SELECT DISTINCT {col} FROM hardware WHERE {col} IS NOT NULL AND {col} != '' ORDER BY {col}"
        ).fetchall()]

    kit_ids = {row[0] for row in db.execute("SELECT DISTINCT kit_hardware_id FROM kit_items").fetchall()}

    return render_template(
        "hardware_list.html",
        items=items, kit_ids=kit_ids,
        q=q, category=category, status=status,
        location=location, classification=classification, manufacturer=manufacturer,
        kits_only=kits_only, low_stock=low_stock,
        sort=sort, order=order,
        categories=distinct("category"),
        statuses=distinct("status"),
        locations=distinct("location"),
        manufacturers=distinct("manufacturer"),
        classifications=distinct("classification"),
        total=total, page=page, per_page=per_page,
        total_pages=total_pages, page_list=page_list,
    )

@bp.route("/stats")
def stats():
    db = get_db()

    def count_by(table, col):
        rows = db.execute(
            f"SELECT COALESCE({col},'(none)') as label, COUNT(*) as n"
            f" FROM {table} GROUP BY {col} ORDER BY n DESC"
        ).fetchall()
        return [(r['label'], r['n']) for r in rows]

    return render_template("stats.html",
        total_hw=db.execute("SELECT COUNT(*) FROM hardware").fetchone()[0],
        total_runs=db.execute("SELECT COUNT(*) FROM procedure_runs").fetchone()[0],
        total_procs=db.execute("SELECT COUNT(*) FROM procedures").fetchone()[0],
        total_tps=db.execute("SELECT COUNT(*) FROM tps").fetchone()[0],
        total_ha=db.execute("SELECT COUNT(*) FROM hazard_analyses").fetchone()[0],
        total_log=db.execute("SELECT COUNT(*) FROM hardware_log").fetchone()[0],
        hw_by_status=count_by("hardware", "status"),
        hw_by_class=count_by("hardware", "classification"),
        hw_by_category=count_by("hardware", "category"),
        hw_by_location=count_by("hardware", "location"),
        runs_by_status=count_by("procedure_runs", "status"),
        procs_by_status=count_by("procedures", "status"),
        tps_by_status=count_by("tps", "status"),
        ha_by_status=count_by("hazard_analyses", "status"),
    )


@bp.route("/manufacturers", methods=["GET", "POST"])
def manufacturer_list():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        website = request.form.get("website", "").strip()
        
        if name:
            try:
                db.execute("INSERT INTO manufacturers (name, website) VALUES (?, ?)", (name, website))
                db.commit()
                flash(f"Added {name}", "success")
            except:
                flash("Manufacturer already exists.", "error")
                
    valid_per_page = (10, 25, 50, 100, 0)
    try:
        per_page = int(request.args.get('per_page', 25))
        if per_page not in valid_per_page:
            per_page = 25
    except (ValueError, TypeError):
        per_page = 25
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        log_limit = int(request.args.get('log_limit', 25))
        if log_limit not in (10, 25, 50, 100):
            log_limit = 25
    except (ValueError, TypeError):
        log_limit = 25

    total = db.execute("SELECT COUNT(*) FROM manufacturers").fetchone()[0]
    if per_page > 0:
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page
        rows = db.execute("SELECT * FROM manufacturers ORDER BY name LIMIT ? OFFSET ?",
                          (per_page, offset)).fetchall()
    else:
        total_pages = 1; page = 1
        rows = db.execute("SELECT * FROM manufacturers ORDER BY name").fetchall()

    if total_pages <= 7:
        page_list = list(range(1, total_pages + 1))
    else:
        visible = sorted({1, total_pages} | set(range(max(1, page - 2), min(total_pages, page + 2) + 1)))
        page_list = []
        for i, p in enumerate(visible):
            if i > 0 and p > visible[i - 1] + 1:
                page_list.append(None)
            page_list.append(p)

    items = []
    for row in rows:
        count = db.execute(
            "SELECT COUNT(*) FROM hardware WHERE manufacturer = ?", (row['name'],)
        ).fetchone()[0]
        items.append({'name': row['name'], 'website': row['website'], 'count': count})

    history = db.execute(
        """SELECT hl.hardware_id, hl.timestamp, hl.action_type, hl.description,
                  h.id as hw_pk
           FROM hardware_log hl
           LEFT JOIN hardware h ON h.hardware_id = hl.hardware_id
           WHERE h.manufacturer IN (SELECT name FROM manufacturers)
           ORDER BY hl.timestamp DESC LIMIT ?""",
        (log_limit,)
    ).fetchall()

    return render_template("manufacturer_list.html", items=items,
                           total=total, page=page, per_page=per_page,
                           total_pages=total_pages, page_list=page_list,
                           history=history, log_limit=log_limit)

@bp.route("/<int:id>")
def hardware_detail(id):
    db = get_db()
    
    # 1. Get the Item
    cur = db.execute("SELECT * FROM hardware WHERE id = ?", (id,))
    item = cur.fetchone()
    
    # 2. Get the History Log
    logs = db.execute(
        "SELECT * FROM hardware_log WHERE hardware_id = ? ORDER BY timestamp DESC", (id,)
    ).fetchall()

    # 3. Get attached documents
    docs = db.execute(
        "SELECT * FROM hardware_docs WHERE hardware_id = ? ORDER BY uploaded_at DESC", (id,)
    ).fetchall()

    # 4. Kit contents (parts this item contains)
    kit_items = db.execute("""
        SELECT ki.*, h.hardware_id AS linked_hid
        FROM kit_items ki
        LEFT JOIN hardware h ON ki.ref_hardware_id = h.id
        WHERE ki.kit_hardware_id = ?
        ORDER BY ki.id
    """, (id,)).fetchall()

    # 5. Kit memberships (kits that contain this item)
    kit_memberships = db.execute("""
        SELECT ki.quantity, ki.notes, h.id AS kit_id, h.hardware_id AS kit_hid, h.description AS kit_desc
        FROM kit_items ki
        JOIN hardware h ON ki.kit_hardware_id = h.id
        WHERE ki.ref_hardware_id = ?
        ORDER BY h.hardware_id
    """, (id,)).fetchall()

    if item is None:
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))

    spec_fields = db.execute(
        "SELECT * FROM category_fields WHERE category = ? ORDER BY sort_order, id",
        (item['category'],)
    ).fetchall() if item['category'] else []
    specs = json.loads(item['specs_json']) if item['specs_json'] else {}

    work_orders = db.execute(
        "SELECT * FROM hardware_work_orders WHERE hardware_id = ? ORDER BY added_at DESC", (id,)
    ).fetchall()
    calibrations = db.execute(
        "SELECT * FROM hardware_calibrations WHERE hardware_id = ? ORDER BY added_at DESC", (id,)
    ).fetchall()
    repairs = db.execute(
        "SELECT * FROM hardware_repairs WHERE hardware_id = ? ORDER BY added_at DESC", (id,)
    ).fetchall()
    a50_numbers = db.execute("SELECT name FROM a50_numbers ORDER BY name").fetchall()
    calibration_ids = db.execute("SELECT name FROM calibration_ids ORDER BY name").fetchall()
    repair_ids = db.execute("SELECT name FROM repair_ids ORDER BY name").fetchall()

    return render_template("hardware_detail.html", item=item, logs=logs, docs=docs,
                           kit_items=kit_items, kit_memberships=kit_memberships,
                           spec_fields=spec_fields, specs=specs,
                           work_orders=work_orders, calibrations=calibrations,
                           repairs=repairs, a50_numbers=a50_numbers,
                           calibration_ids=calibration_ids, repair_ids=repair_ids)

@bp.route("/new", methods=("GET", "POST"))
def hardware_new():
    db = get_db()
    
    if request.method == "POST":
        # 1. Identity
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        classification = request.form.get("classification", "").strip()
        manufacturer = request.form.get("manufacturer", "").strip()
        part_number = request.form.get("part_number", "").strip()
        serial_number = request.form.get("serial_number", "").strip()
        
        # 2. Tracking / MSFC
        ctn = request.form.get("ctn", "").strip()
        ecn = request.form.get("ecn", "").strip()
        calibration_id = request.form.get("calibration_id", "").strip()
        repair_id = request.form.get("repair_id", "").strip()

        # 3. Technical Specs
        specs_json = request.form.get("specs_json", "").strip() or None

        # 4. Status
        status = request.form.get("status", "").strip()
        custodian = request.form.get("custodian", "").strip()
        location = request.form.get("location", "").strip()
        traveler_path = request.form.get("traveler_path", "").strip()

        # 5. Safety & Compliance
        safety_class = request.form.get("safety_class", "").strip()
        propellant_or_media = request.form.get("propellant_or_media", "").strip()
        cleaning_spec = request.form.get("cleaning_spec", "").strip()
        compliance_specs = request.form.get("compliance_specs", "").strip()
        max_pressure = request.form.get("max_rated_pressure", "").strip()
        max_temp = request.form.get("max_rated_temperature", "").strip()

        # 6. Quantity
        try:
            quantity = max(1, int(request.form.get("quantity", "1") or 1))
        except ValueError:
            quantity = 1

        if not description:
            flash("Description is required.", "error")
            _a50 = db.execute("SELECT name FROM a50_numbers ORDER BY name").fetchall()
            return render_template("hardware_form.html", item=None,
                                   work_orders=[], calibrations=[], repairs=[], a50_numbers=_a50,
                                   **get_dropdown_data(db))

        hardware_id = generate_new_hardware_id(db)
        now = datetime.utcnow().isoformat(timespec="seconds")
        image_filename = _save_image(request.files.get('image'), hardware_id)

        db.execute(
            """
            INSERT INTO hardware (
                hardware_id, description, category, classification, manufacturer,
                part_number, serial_number,
                ctn, ecn, calibration_id, repair_id,
                port_configuration, cv, orifice_diameter,
                status, custodian, location,
                safety_class, propellant_or_media, cleaning_spec, compliance_specs,
                max_rated_pressure, max_rated_temperature,
                traveler_path, image_filename, quantity, specs_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hardware_id, description, category, classification, manufacturer,
                part_number, serial_number,
                ctn, ecn, calibration_id, repair_id,
                None, None, None,
                status, custodian, location,
                safety_class, propellant_or_media, cleaning_spec, compliance_specs,
                max_pressure or None, max_temp or None,
                traveler_path, image_filename, quantity, specs_json, now, now
            )
        )
        row = db.execute("SELECT id FROM hardware WHERE hardware_id = ?", (hardware_id,)).fetchone()
        new_id = row["id"]
        db.execute(
            "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
            (new_id, now, "Created", f"Item added: {description}" + (f" | S/N: {serial_number}" if serial_number else ""))
        )
        wo_number = request.form.get("new_work_order_number", "").strip()
        if wo_number:
            wo_date = request.form.get("new_work_order_date", "").strip() or None
            wo_notes = request.form.get("new_work_order_notes", "").strip() or None
            db.execute(
                "INSERT INTO hardware_work_orders (hardware_id, work_order_number, date, notes, added_at) VALUES (?, ?, ?, ?, ?)",
                (new_id, wo_number, wo_date, wo_notes, now)
            )
            db.execute(
                "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                (new_id, now, "Work Order", f"Added work order: {wo_number}" + (f" ({wo_date})" if wo_date else ""))
            )
        cal_performed = request.form.get("new_cal_date_performed", "").strip() or None
        cal_due = request.form.get("new_cal_due_date", "").strip() or None
        cal_notes = request.form.get("new_cal_notes", "").strip() or None
        if cal_performed or cal_due or cal_notes:
            db.execute(
                "INSERT INTO hardware_calibrations (hardware_id, cal_number, date_performed, due_date, notes, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id, calibration_id, cal_performed, cal_due, cal_notes, now)
            )
            db.execute(
                "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                (new_id, now, "Calibration", f"Added calibration entry ({calibration_id or 'no M-number'})" + (f" — due {cal_due}" if cal_due else ""))
            )
        repair_number = request.form.get("new_repair_number", "").strip()
        if repair_number:
            repair_date = request.form.get("new_repair_date", "").strip() or None
            repair_notes = request.form.get("new_repair_notes", "").strip() or None
            db.execute(
                "INSERT INTO hardware_repairs (hardware_id, repair_number, date, notes, added_at) VALUES (?, ?, ?, ?, ?)",
                (new_id, repair_number, repair_date, repair_notes, now)
            )
            db.execute(
                "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                (new_id, now, "Repair", f"Added repair: {repair_number}" + (f" ({repair_date})" if repair_date else ""))
            )
        db.commit()
        flash(f"Created hardware {hardware_id}.", "success")
        return redirect(url_for("hardware.hardware_detail", id=new_id))

    _a50 = db.execute("SELECT name FROM a50_numbers ORDER BY name").fetchall()
    return render_template("hardware_form.html", item=None,
                           work_orders=[], calibrations=[], repairs=[], a50_numbers=_a50,
                           **get_dropdown_data(db))

@bp.route("/<int:id>/edit", methods=("GET", "POST"))
def hardware_edit(id):
    db = get_db()
    cur = db.execute("SELECT * FROM hardware WHERE id = ?", (id,))
    item = cur.fetchone()
    
    if item is None:
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))

    if request.method == "POST":
        # 1. Identity
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        classification = request.form.get("classification", "").strip()
        manufacturer = request.form.get("manufacturer", "").strip()
        part_number = request.form.get("part_number", "").strip()
        serial_number = request.form.get("serial_number", "").strip()

        # 2. Tracking / MSFC
        ctn = request.form.get("ctn", "").strip()
        ecn = request.form.get("ecn", "").strip()
        calibration_id = request.form.get("calibration_id", "").strip()
        repair_id = request.form.get("repair_id", "").strip()

        # 3. Technical Specs
        specs_json = request.form.get("specs_json", "").strip() or None

        # 4. Status
        status = request.form.get("status", "").strip()
        custodian = request.form.get("custodian", "").strip()
        location = request.form.get("location", "").strip()
        traveler_path = request.form.get("traveler_path", "").strip()

        # 5. Safety & Compliance
        safety_class = request.form.get("safety_class", "").strip()
        propellant_or_media = request.form.get("propellant_or_media", "").strip()
        cleaning_spec = request.form.get("cleaning_spec", "").strip()
        compliance_specs = request.form.get("compliance_specs", "").strip()
        max_pressure = request.form.get("max_rated_pressure", "").strip()
        max_temp = request.form.get("max_rated_temperature", "").strip()

        # 6. Quantity
        try:
            quantity = max(0, int(request.form.get("quantity", "1") or 1))
        except ValueError:
            quantity = item['quantity'] or 1

        if not description:
            flash("Description is required.", "error")
            wo = db.execute("SELECT * FROM hardware_work_orders WHERE hardware_id = ? ORDER BY added_at DESC", (id,)).fetchall()
            cals = db.execute("SELECT * FROM hardware_calibrations WHERE hardware_id = ? ORDER BY added_at DESC", (id,)).fetchall()
            reps = db.execute("SELECT * FROM hardware_repairs WHERE hardware_id = ? ORDER BY added_at DESC", (id,)).fetchall()
            _a50 = db.execute("SELECT name FROM a50_numbers ORDER BY name").fetchall()
            return render_template("hardware_form.html", item=item,
                                   work_orders=wo, calibrations=cals, repairs=reps, a50_numbers=_a50,
                                   **get_dropdown_data(db))

        now = datetime.utcnow().isoformat(timespec="seconds")

        # Handle image upload — replace existing if a new file was provided
        new_image = _save_image(request.files.get('image'), item['hardware_id'])
        if new_image and new_image != item['image_filename']:
            _delete_image_file(item['image_filename'])
            image_filename = new_image
        else:
            image_filename = item['image_filename']

        # --- HISTORY LOG LOGIC ---
        def _s(v):
            return "" if v is None else str(v).strip()

        def _eq(db_val, form_val):
            a, b = _s(db_val), form_val.strip()
            if a == b:
                return True
            try:                          # treat "3000.0" == "3000" as no change
                return float(a) == float(b)
            except (ValueError, TypeError):
                return False

        watched = [
            ("Description",    item['description'],           description),
            ("Category",       item['category'],              category),
            ("Classification", item['classification'],        classification),
            ("Manufacturer",   item['manufacturer'],          manufacturer),
            ("Part Number",    item['part_number'],           part_number),
            ("Serial Number",  item['serial_number'],         serial_number),
            ("CTN",            item['ctn'],                   ctn),
            ("ECN",            item['ecn'],                   ecn),
            ("Calibration ID", item['calibration_id'],        calibration_id),
            ("Repair Ref",     item['repair_id'],             repair_id),
            ("Status",         item['status'],                status),
            ("Location",       item['location'],              location),
            ("Custodian",      item['custodian'],             custodian),
            ("Safety Class",   item['safety_class'],          safety_class),
            ("Media",          item['propellant_or_media'],   propellant_or_media),
            ("Cleaning Spec",  item['cleaning_spec'],         cleaning_spec),
            ("Compliance",     item['compliance_specs'],      compliance_specs),
            ("Max Pressure",   item['max_rated_pressure'],    max_pressure),
            ("Max Temp",       item['max_rated_temperature'], max_temp),
            ("Traveler Path",  item['traveler_path'],         traveler_path),
            ("Quantity",       item['quantity'],               str(quantity)),
        ]

        changes = [
            f"{label}: '{_s(old)}' → '{new.strip()}'"
            for label, old, new in watched
            if not _eq(old, new)
        ]

        if item['specs_json'] != specs_json:
            changes.append("Technical specs updated")

        if new_image:
            changes.append("Photo: " + ("replaced" if item['image_filename'] else "added"))

        if changes:
            db.execute(
                "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                (id, now, "Update", "; ".join(changes))
            )

        # --- SAVE UPDATE ---
        db.execute(
            """
            UPDATE hardware SET
                description=?, category=?, classification=?, manufacturer=?,
                part_number=?, serial_number=?,
                ctn=?, ecn=?, calibration_id=?, repair_id=?,
                port_configuration=?, cv=?, orifice_diameter=?,
                status=?, custodian=?, location=?,
                safety_class=?, propellant_or_media=?, cleaning_spec=?, compliance_specs=?,
                max_rated_pressure=?, max_rated_temperature=?,
                traveler_path=?, image_filename=?, quantity=?, specs_json=?, updated_at=?
            WHERE id=?
            """,
            (
                description, category, classification, manufacturer,
                part_number, serial_number,
                ctn, ecn, calibration_id, repair_id,
                None, None, None,
                status, custodian, location,
                safety_class, propellant_or_media, cleaning_spec, compliance_specs,
                max_pressure or None, max_temp or None,
                traveler_path, image_filename, quantity, specs_json, now, id
            )
        )
        db.commit()
        flash("Hardware updated.", "success")
        return redirect(url_for("hardware.hardware_detail", id=id))

    # GET Request: Render form with item data AND dropdown lists
    work_orders = db.execute(
        "SELECT * FROM hardware_work_orders WHERE hardware_id = ? ORDER BY added_at DESC", (id,)
    ).fetchall()
    calibrations = db.execute(
        "SELECT * FROM hardware_calibrations WHERE hardware_id = ? ORDER BY added_at DESC", (id,)
    ).fetchall()
    repairs = db.execute(
        "SELECT * FROM hardware_repairs WHERE hardware_id = ? ORDER BY added_at DESC", (id,)
    ).fetchall()
    a50_numbers = db.execute("SELECT name FROM a50_numbers ORDER BY name").fetchall()
    return render_template("hardware_form.html", item=item,
                           work_orders=work_orders, calibrations=calibrations,
                           repairs=repairs, a50_numbers=a50_numbers,
                           **get_dropdown_data(db))




@bp.route("/image/<path:filename>")
def serve_image(filename):
    return send_from_directory(_upload_folder(), filename)

@bp.route("/<int:id>/delete-image", methods=["POST"])
def delete_image(id):
    db = get_db()
    item = db.execute("SELECT image_filename FROM hardware WHERE id = ?", (id,)).fetchone()
    if item and item['image_filename']:
        _delete_image_file(item['image_filename'])
        db.execute("UPDATE hardware SET image_filename = NULL WHERE id = ?", (id,))
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
            (id, now, "Update", "Photo: removed")
        )
        db.commit()
        flash("Image removed.", "success")
    return redirect(url_for("hardware.hardware_detail", id=id))

@bp.route("/<int:id>/adjust-qty", methods=["POST"])
def adjust_qty(id):
    db = get_db()
    item = db.execute("SELECT id, quantity, hardware_id FROM hardware WHERE id = ?", (id,)).fetchone()
    if not item:
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))

    try:
        delta = int(request.form.get("delta", "0"))
    except ValueError:
        flash("Invalid adjustment value.", "error")
        return redirect(url_for("hardware.hardware_detail", id=id))

    current_qty = item['quantity'] or 0
    new_qty = max(0, current_qty + delta)

    if new_qty == current_qty:
        flash("Quantity unchanged — cannot go below 0.", "warning")
        return redirect(url_for("hardware.hardware_detail", id=id))

    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute("UPDATE hardware SET quantity=?, updated_at=? WHERE id=?", (new_qty, now, id))
    direction = "added" if delta > 0 else "removed"
    db.execute(
        "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
        (id, now, "Stock", f"Qty {direction} {abs(delta)}: {current_qty} → {new_qty}")
    )
    db.commit()
    return redirect(url_for("hardware.hardware_detail", id=id))

@bp.route("/docs/file/<path:stored_name>")
def serve_doc(stored_name):
    return send_from_directory(_doc_folder(), stored_name)

@bp.route("/<int:id>/docs/upload", methods=["POST"])
def upload_doc(id):
    db = get_db()
    if not db.execute("SELECT id FROM hardware WHERE id = ?", (id,)).fetchone():
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))

    label = request.form.get("label", "").strip()
    stored_name, original_name = _save_doc(request.files.get("doc"), id)

    if not stored_name:
        flash("Upload failed — check that the file type is supported.", "error")
        return redirect(url_for("hardware.hardware_detail", id=id))

    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO hardware_docs (hardware_id, original_name, stored_name, label, uploaded_at) VALUES (?, ?, ?, ?, ?)",
        (id, original_name, stored_name, label or None, now)
    )
    log_desc = f"Document added: {label or original_name}"
    db.execute(
        "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
        (id, now, "Document", log_desc)
    )
    db.commit()
    flash(f"Uploaded {original_name}.", "success")
    return redirect(url_for("hardware.hardware_detail", id=id))

@bp.route("/docs/<int:doc_id>/delete", methods=["POST"])
def delete_doc(doc_id):
    db = get_db()
    doc = db.execute("SELECT * FROM hardware_docs WHERE id = ?", (doc_id,)).fetchone()
    if doc:
        path = os.path.join(_doc_folder(), doc['stored_name'])
        if os.path.exists(path):
            os.remove(path)
        db.execute("DELETE FROM hardware_docs WHERE id = ?", (doc_id,))
        now = datetime.utcnow().isoformat(timespec="seconds")
        log_desc = f"Document removed: {doc['label'] or doc['original_name']}"
        db.execute(
            "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
            (doc['hardware_id'], now, "Document", log_desc)
        )
        db.commit()
        flash(f"Removed {doc['original_name']}.", "success")
        return redirect(url_for("hardware.hardware_detail", id=doc['hardware_id']))
    return redirect(url_for("hardware.hardware_list"))


# --- KIT ROUTES ---

@bp.route("/<int:id>/kit/add", methods=["POST"])
def kit_add_item(id):
    db = get_db()
    if not db.execute("SELECT id FROM hardware WHERE id = ?", (id,)).fetchone():
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))

    description = request.form.get("description", "").strip()
    notes = request.form.get("notes", "").strip()
    ref_hid_str = request.form.get("ref_hardware_id", "").strip().upper()
    try:
        quantity = max(1, int(request.form.get("quantity", "1") or 1))
    except ValueError:
        quantity = 1

    if not description:
        flash("Description is required for a kit item.", "error")
        return redirect(url_for("hardware.hardware_detail", id=id))

    # Resolve optional H-number reference
    ref_id = None
    if ref_hid_str:
        ref_row = db.execute("SELECT id FROM hardware WHERE hardware_id = ?", (ref_hid_str,)).fetchone()
        if ref_row:
            ref_id = ref_row['id']
        else:
            flash(f"H-number '{ref_hid_str}' not found — item added without link.", "warning")

    db.execute(
        "INSERT INTO kit_items (kit_hardware_id, ref_hardware_id, description, quantity, notes) VALUES (?, ?, ?, ?, ?)",
        (id, ref_id, description, quantity, notes or None)
    )
    now = datetime.utcnow().isoformat(timespec="seconds")
    link_note = f" ({ref_hid_str})" if ref_id else ""
    db.execute(
        "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
        (id, now, "Kit", f"Added to kit: {quantity}× {description}{link_note}")
    )
    db.commit()
    return redirect(url_for("hardware.hardware_detail", id=id))


@bp.route("/kit-item/<int:kit_item_id>/delete", methods=["POST"])
def kit_delete_item(kit_item_id):
    db = get_db()
    row = db.execute("SELECT kit_hardware_id FROM kit_items WHERE id = ?", (kit_item_id,)).fetchone()
    if row:
        item_row = db.execute("SELECT description, quantity FROM kit_items WHERE id = ?", (kit_item_id,)).fetchone()
        db.execute("DELETE FROM kit_items WHERE id = ?", (kit_item_id,))
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
            (row['kit_hardware_id'], now, "Kit", f"Removed from kit: {item_row['quantity']}× {item_row['description']}")
        )
        db.commit()
        return redirect(url_for("hardware.hardware_detail", id=row['kit_hardware_id']))
    return redirect(url_for("hardware.hardware_list"))


# --- CALIBRATION ROUTES ---

@bp.route("/<int:id>/calibrations/add", methods=["POST"])
def calibration_add(id):
    db = get_db()
    if not db.execute("SELECT id FROM hardware WHERE id = ?", (id,)).fetchone():
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))
    hw = db.execute("SELECT calibration_id FROM hardware WHERE id = ?", (id,)).fetchone()
    cal_number = hw['calibration_id'] if hw and hw['calibration_id'] else ''
    date_performed = request.form.get("date_performed", "").strip() or None
    due_date = request.form.get("due_date", "").strip() or None
    notes = request.form.get("notes", "").strip() or None
    if not date_performed and not due_date and not notes:
        flash("Enter at least one field (date or notes).", "error")
        referrer = request.referrer or ""
        if "/edit" in referrer:
            return redirect(url_for("hardware.hardware_edit", id=id))
        return redirect(url_for("hardware.hardware_detail", id=id))
    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO hardware_calibrations (hardware_id, cal_number, date_performed, due_date, notes, added_at) VALUES (?, ?, ?, ?, ?, ?)",
        (id, cal_number, date_performed, due_date, notes, now)
    )
    label = cal_number or "record"
    db.execute(
        "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
        (id, now, "Calibration", f"Added calibration entry ({label})" + (f" — due {due_date}" if due_date else ""))
    )
    db.commit()
    flash("Calibration record added.", "success")
    referrer = request.referrer or ""
    if "/edit" in referrer:
        return redirect(url_for("hardware.hardware_edit", id=id))
    return redirect(url_for("hardware.hardware_detail", id=id))

@bp.route("/calibrations/<int:cal_id>/delete", methods=["POST"])
def calibration_delete(cal_id):
    db = get_db()
    row = db.execute("SELECT * FROM hardware_calibrations WHERE id = ?", (cal_id,)).fetchone()
    if row:
        db.execute("DELETE FROM hardware_calibrations WHERE id = ?", (cal_id,))
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
            (row['hardware_id'], now, "Calibration", f"Removed calibration: {row['cal_number']}")
        )
        db.commit()
        flash(f"Removed calibration {row['cal_number']}.", "success")
        referrer = request.referrer or ""
        if "/edit" in referrer:
            return redirect(url_for("hardware.hardware_edit", id=row['hardware_id']))
        return redirect(url_for("hardware.hardware_detail", id=row['hardware_id']))
    return redirect(url_for("hardware.hardware_list"))


# --- REPAIR ROUTES ---

@bp.route("/<int:id>/repairs/add", methods=["POST"])
def repair_add(id):
    db = get_db()
    if not db.execute("SELECT id FROM hardware WHERE id = ?", (id,)).fetchone():
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))
    repair_number = request.form.get("repair_number", "").strip()
    date = request.form.get("date", "").strip() or None
    notes = request.form.get("notes", "").strip() or None
    if not repair_number:
        flash("Repair number is required.", "error")
        return redirect(url_for("hardware.hardware_edit", id=id))
    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO hardware_repairs (hardware_id, repair_number, date, notes, added_at) VALUES (?, ?, ?, ?, ?)",
        (id, repair_number, date, notes, now)
    )
    db.execute(
        "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
        (id, now, "Repair", f"Added repair: {repair_number}" + (f" ({date})" if date else ""))
    )
    db.commit()
    flash(f"Added repair {repair_number}.", "success")
    referrer = request.referrer or ""
    if "/edit" in referrer:
        return redirect(url_for("hardware.hardware_edit", id=id))
    return redirect(url_for("hardware.hardware_detail", id=id))

@bp.route("/repairs/<int:repair_id>/delete", methods=["POST"])
def repair_delete(repair_id):
    db = get_db()
    row = db.execute("SELECT * FROM hardware_repairs WHERE id = ?", (repair_id,)).fetchone()
    if row:
        db.execute("DELETE FROM hardware_repairs WHERE id = ?", (repair_id,))
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
            (row['hardware_id'], now, "Repair", f"Removed repair: {row['repair_number']}")
        )
        db.commit()
        flash(f"Removed repair {row['repair_number']}.", "success")
        referrer = request.referrer or ""
        if "/edit" in referrer:
            return redirect(url_for("hardware.hardware_edit", id=row['hardware_id']))
        return redirect(url_for("hardware.hardware_detail", id=row['hardware_id']))
    return redirect(url_for("hardware.hardware_list"))


# --- WORK ORDER ROUTES ---

@bp.route("/<int:id>/work-orders/add", methods=["POST"])
def work_order_add(id):
    db = get_db()
    if not db.execute("SELECT id FROM hardware WHERE id = ?", (id,)).fetchone():
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))
    work_order_number = request.form.get("work_order_number", "").strip()
    date = request.form.get("date", "").strip() or None
    notes = request.form.get("notes", "").strip() or None
    if not work_order_number:
        flash("Work order number is required.", "error")
        return redirect(url_for("hardware.hardware_detail", id=id))
    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO hardware_work_orders (hardware_id, work_order_number, date, notes, added_at) VALUES (?, ?, ?, ?, ?)",
        (id, work_order_number, date, notes, now)
    )
    db.execute(
        "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
        (id, now, "Work Order", f"Added work order: {work_order_number}" + (f" ({date})" if date else ""))
    )
    db.commit()
    flash(f"Added work order {work_order_number}.", "success")
    referrer = request.referrer or ""
    if "/edit" in referrer:
        return redirect(url_for("hardware.hardware_edit", id=id))
    return redirect(url_for("hardware.hardware_detail", id=id))

@bp.route("/work-orders/<int:wo_id>/delete", methods=["POST"])
def work_order_delete(wo_id):
    db = get_db()
    row = db.execute("SELECT * FROM hardware_work_orders WHERE id = ?", (wo_id,)).fetchone()
    if row:
        db.execute("DELETE FROM hardware_work_orders WHERE id = ?", (wo_id,))
        now = datetime.utcnow().isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
            (row['hardware_id'], now, "Work Order", f"Removed work order: {row['work_order_number']}")
        )
        db.commit()
        flash(f"Removed work order {row['work_order_number']}.", "success")
        referrer = request.referrer or ""
        if "/edit" in referrer:
            return redirect(url_for("hardware.hardware_edit", id=row['hardware_id']))
        return redirect(url_for("hardware.hardware_detail", id=row['hardware_id']))
    return redirect(url_for("hardware.hardware_list"))


# --- QUICK-ADD (modal fetch endpoint) ---

_QUICK_ADD_TABLES = {'manufacturers', 'custodians', 'locations', 'media', 'port_configs', 'categories', 'cleaning_specs', 'ctns', 'ecns', 'calibration_ids', 'repair_ids', 'part_numbers', 'other_specs', 'a50_numbers'}

# table_name → (source_table, column_on_that_table_that_holds_the_value)
# 'hardware' = direct column; anything else = join via hardware_id FK
_TRACEABLE = {
    'manufacturers':   ('hardware',             'manufacturer'),
    'custodians':      ('hardware',             'custodian'),
    'locations':       ('hardware',             'location'),
    'media':           ('hardware',             'propellant_or_media'),
    'part_numbers':    ('hardware',             'part_number'),
    'ctns':            ('hardware',             'ctn'),
    'ecns':            ('hardware',             'ecn'),
    'calibration_ids': ('hardware',             'calibration_id'),
    'other_specs':     ('hardware',             'compliance_specs'),
    'a50_numbers':     ('hardware_work_orders', 'work_order_number'),
    'repair_ids':      ('hardware_repairs',     'repair_number'),
}

_TABLE_LABELS = {
    'manufacturers':   'Manufacturer',
    'custodians':      'Custodian',
    'locations':       'Location',
    'media':           'Service Media',
    'part_numbers':    'Part Number',
    'ctns':            'CTN #',
    'ecns':            'ECN',
    'calibration_ids': 'Cal M-number',
    'other_specs':     'Other Spec',
    'a50_numbers':     'A50 Work Order',
    'repair_ids':      'Repair Ticket',
}

_TABLE_LIST_ENDPOINT = {
    'manufacturers':   'hardware.manufacturer_list',
    'custodians':      'hardware.custodian_list',
    'locations':       'hardware.location_list',
    'media':           'hardware.media_list',
    'part_numbers':    'hardware.part_number_list',
    'ctns':            'hardware.ctn_list',
    'ecns':            'hardware.ecn_list',
    'calibration_ids': 'hardware.calibration_id_list',
    'other_specs':     'hardware.other_specs_list',
    'a50_numbers':     'hardware.a50_number_list',
    'repair_ids':      'hardware.repair_id_list',
}

def _item_label(table_name):
    """Human-readable singular label for a config table."""
    if table_name in _TABLE_LABELS:
        return _TABLE_LABELS[table_name]
    label = table_name.replace('_', ' ').title()
    if label.endswith('s') and not label.endswith('ss'):
        label = label[:-1]
    return label

@bp.route("/quick-add/<table>", methods=["POST"])
def quick_add(table):
    if table not in _QUICK_ADD_TABLES:
        return jsonify({"success": False, "error": "Unknown list"}), 400
    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400
    db = get_db()
    try:
        db.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
        db.commit()
        return jsonify({"success": True, "name": name})
    except Exception:
        return jsonify({"success": False, "error": f'"{name}" already exists'}), 409


# --- TRACEABILITY ---

@bp.route("/traceability/<table>/<path:name>")
def traceability_view(table, name):
    if table not in _TRACEABLE:
        flash("Traceability not available for this list.", "error")
        return redirect(url_for("hardware.hardware_list"))

    db = get_db()
    source_table, source_col = _TRACEABLE[table]

    if source_table == 'hardware':
        hw_items = db.execute(
            f"SELECT * FROM hardware WHERE {source_col} = ? ORDER BY hardware_id",
            (name,)
        ).fetchall()
    else:
        hw_items = db.execute(
            f"""SELECT DISTINCT h.* FROM hardware h
                JOIN {source_table} t ON t.hardware_id = h.id
                WHERE t.{source_col} = ?
                ORDER BY h.hardware_id""",
            (name,)
        ).fetchall()

    logs = []
    if hw_items:
        hid_labels = [hw['hardware_id'] for hw in hw_items]
        placeholders = ','.join('?' * len(hid_labels))
        logs = db.execute(
            f"""SELECT hl.hardware_id, hl.timestamp, hl.action_type, hl.description,
                       h.id as hw_pk
                FROM hardware_log hl
                LEFT JOIN hardware h ON h.hardware_id = hl.hardware_id
                WHERE hl.hardware_id IN ({placeholders})
                ORDER BY hl.timestamp DESC""",
            hid_labels
        ).fetchall()

    label = _TABLE_LABELS.get(table, table.replace('_', ' ').title())
    back_endpoint = _TABLE_LIST_ENDPOINT.get(table)
    back_url = url_for(back_endpoint) if back_endpoint else url_for('hardware.hardware_list')

    return render_template("traceability.html",
        hw_items=hw_items, logs=logs,
        label=label, name=name,
        back_url=back_url)


# --- CATEGORY FIELDS ---

_KNOWN_CATEGORIES = ['Valve', 'Regulator', 'Sensor', 'Tank', 'Fitting', 'Tool', 'Electronics', 'Other']

@bp.route("/category-fields/<category>/json")
def category_fields_json(category):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM category_fields WHERE category = ? ORDER BY sort_order, id",
        (category,)
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get('options'):
            try:
                d['options'] = json.loads(d['options'])
            except (ValueError, TypeError):
                d['options'] = []
        else:
            d['options'] = []
        result.append(d)
    return jsonify(result)

@bp.route("/category-fields")
def category_fields_config():
    db = get_db()
    selected = request.args.get("category", "").strip()
    managed = [r[0] for r in db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    hw_cats = [r[0] for r in db.execute(
        "SELECT DISTINCT category FROM hardware WHERE category IS NOT NULL AND category != ''"
    ).fetchall()]
    all_cats = sorted(set(managed) | set(hw_cats))
    fields = []
    if selected:
        fields = db.execute(
            "SELECT * FROM category_fields WHERE category = ? ORDER BY sort_order, id",
            (selected,)
        ).fetchall()
    return render_template("category_fields.html",
                           categories=all_cats, selected=selected, fields=fields)

@bp.route("/category-fields/add", methods=["POST"])
def category_fields_add():
    db = get_db()
    category = request.form.get("category", "").strip()
    raw_key = request.form.get("field_key", "").strip()
    field_key = raw_key.lower().replace(" ", "_")
    label = request.form.get("label", "").strip()
    field_type = request.form.get("field_type", "text").strip()
    unit = request.form.get("unit", "").strip() or None
    placeholder = request.form.get("placeholder", "").strip() or None
    options_raw = request.form.get("options", "").strip()
    options = None
    if options_raw and field_type in ("select", "multicheck"):
        opts = [o.strip() for o in options_raw.splitlines() if o.strip()]
        options = json.dumps(opts) if opts else None
    if not category or not field_key or not label:
        flash("Category, field key, and label are required.", "error")
        return redirect(url_for("hardware.category_fields_config", category=category))
    max_row = db.execute(
        "SELECT MAX(sort_order) FROM category_fields WHERE category = ?", (category,)
    ).fetchone()
    sort_order = (max_row[0] or 0) + 1
    try:
        db.execute(
            "INSERT INTO category_fields (category, field_key, label, field_type, options, unit, placeholder, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (category, field_key, label, field_type, options, unit, placeholder, sort_order)
        )
        db.commit()
        flash(f"Added field '{label}'.", "success")
    except Exception:
        flash(f"Field key '{field_key}' already exists for this category.", "error")
    return redirect(url_for("hardware.category_fields_config", category=category))

@bp.route("/category-fields/<int:field_id>/edit", methods=["POST"])
def category_fields_edit(field_id):
    db = get_db()
    row = db.execute("SELECT * FROM category_fields WHERE id = ?", (field_id,)).fetchone()
    if not row:
        flash("Field not found.", "error")
        return redirect(url_for("hardware.category_fields_config"))
    label = request.form.get("label", "").strip()
    unit = request.form.get("unit", "").strip() or None
    placeholder = request.form.get("placeholder", "").strip() or None
    options_raw = request.form.get("options", "").strip()
    options = row['options']
    if row['field_type'] in ("select", "multicheck"):
        if options_raw:
            opts = [o.strip() for o in options_raw.splitlines() if o.strip()]
            options = json.dumps(opts) if opts else None
        else:
            options = None
    db.execute(
        "UPDATE category_fields SET label=?, unit=?, placeholder=?, options=? WHERE id=?",
        (label, unit, placeholder, options, field_id)
    )
    db.commit()
    flash("Field updated.", "success")
    return redirect(url_for("hardware.category_fields_config", category=row['category']))

@bp.route("/category-fields/<int:field_id>/delete", methods=["POST"])
def category_fields_delete(field_id):
    db = get_db()
    row = db.execute("SELECT category FROM category_fields WHERE id = ?", (field_id,)).fetchone()
    if row:
        db.execute("DELETE FROM category_fields WHERE id = ?", (field_id,))
        db.commit()
        flash("Field deleted.", "success")
        return redirect(url_for("hardware.category_fields_config", category=row['category']))
    return redirect(url_for("hardware.category_fields_config"))

@bp.route("/category-fields/<int:field_id>/move", methods=["POST"])
def category_fields_move(field_id):
    db = get_db()
    row = db.execute("SELECT * FROM category_fields WHERE id = ?", (field_id,)).fetchone()
    if not row:
        return redirect(url_for("hardware.category_fields_config"))
    direction = request.form.get("direction", "down")
    all_fields = db.execute(
        "SELECT id, sort_order FROM category_fields WHERE category = ? ORDER BY sort_order, id",
        (row['category'],)
    ).fetchall()
    ids = [f['id'] for f in all_fields]
    try:
        idx = ids.index(field_id)
    except ValueError:
        return redirect(url_for("hardware.category_fields_config", category=row['category']))
    if direction == "up" and idx > 0:
        neighbor = all_fields[idx - 1]
    elif direction == "down" and idx < len(all_fields) - 1:
        neighbor = all_fields[idx + 1]
    else:
        return redirect(url_for("hardware.category_fields_config", category=row['category']))
    db.execute("UPDATE category_fields SET sort_order=? WHERE id=?", (neighbor['sort_order'], field_id))
    db.execute("UPDATE category_fields SET sort_order=? WHERE id=?", (row['sort_order'], neighbor['id']))
    db.commit()
    return redirect(url_for("hardware.category_fields_config", category=row['category']))


# --- GENERIC LIST HELPERS ---

@bp.route("/config/<table>/delete", methods=["POST"])
def config_item_delete(table):
    if table not in _QUICK_ADD_TABLES:
        flash("Unknown list.", "error")
        return redirect(url_for("hardware.hardware_list"))
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(request.referrer or url_for("hardware.hardware_list"))
    db = get_db()
    if table in _TRACEABLE:
        source_table, source_col = _TRACEABLE[table]
        if source_table == 'hardware':
            count = db.execute(
                f"SELECT COUNT(*) FROM hardware WHERE {source_col} = ?", (name,)
            ).fetchone()[0]
        else:
            count = db.execute(
                f"SELECT COUNT(DISTINCT hardware_id) FROM {source_table} WHERE {source_col} = ?",
                (name,)
            ).fetchone()[0]
        if count > 0:
            flash(f'Cannot delete "{name}" — assigned to {count} hardware item(s).', "error")
            return redirect(request.referrer or url_for("hardware.hardware_list"))
    db.execute(f"DELETE FROM {table} WHERE name = ?", (name,))
    db.commit()
    flash(f'Deleted "{name}".', "success")
    return redirect(request.referrer or url_for("hardware.hardware_list"))

@bp.route("/custodians", methods=["GET", "POST"])
def custodian_list():
    return handle_simple_list("custodians", "Manage Custodians")

@bp.route("/locations", methods=["GET", "POST"])
def location_list():
    return handle_simple_list("locations", "Manage Locations")

@bp.route("/media", methods=["GET", "POST"])
def media_list():
    return handle_simple_list("media", "Manage Service Media")

@bp.route("/port_configs", methods=["GET", "POST"])
def port_config_list():
    return handle_simple_list("port_configs", "Manage Port Configs")

@bp.route("/ctns", methods=["GET", "POST"])
def ctn_list():
    return handle_simple_list("ctns", "Manage CTN Numbers")

@bp.route("/ecns", methods=["GET", "POST"])
def ecn_list():
    return handle_simple_list("ecns", "Manage ECN Numbers")

@bp.route("/calibration-ids", methods=["GET", "POST"])
def calibration_id_list():
    return handle_simple_list("calibration_ids", "Manage Calibration IDs")

@bp.route("/repair-ids", methods=["GET", "POST"])
def repair_id_list():
    return handle_simple_list("repair_ids", "Manage Repair / Ticket IDs")

@bp.route("/part-numbers", methods=["GET", "POST"])
def part_number_list():
    return handle_simple_list("part_numbers", "Manage Part Numbers")

@bp.route("/other-specs", methods=["GET", "POST"])
def other_specs_list():
    return handle_simple_list("other_specs", "Manage Other Specifications")

@bp.route("/a50-numbers", methods=["GET", "POST"])
def a50_number_list():
    return handle_simple_list("a50_numbers", "Manage A50 Work Order Numbers")

def handle_simple_list(table_name, page_title):
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            try:
                db.execute(f"INSERT INTO {table_name} (name) VALUES (?)", (name,))
                db.commit()
                flash(f'Added "{name}".', "success")
            except:
                flash("Item already exists.", "error")

    traceable = table_name in _TRACEABLE

    # --- pagination ---
    valid_per_page = (10, 25, 50, 100, 0)
    try:
        per_page = int(request.args.get('per_page', 25))
        if per_page not in valid_per_page:
            per_page = 25
    except (ValueError, TypeError):
        per_page = 25

    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    total = db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    if per_page > 0:
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page
        rows = db.execute(
            f"SELECT * FROM {table_name} ORDER BY name LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
    else:
        total_pages = 1
        page = 1
        rows = db.execute(f"SELECT * FROM {table_name} ORDER BY name").fetchall()

    if total_pages <= 7:
        page_list = list(range(1, total_pages + 1))
    else:
        visible = sorted({1, total_pages} | set(range(max(1, page - 2), min(total_pages, page + 2) + 1)))
        page_list = []
        for i, p in enumerate(visible):
            if i > 0 and p > visible[i - 1] + 1:
                page_list.append(None)
            page_list.append(p)

    # --- usage counts for current page ---
    items = []
    for row in rows:
        count = None
        if traceable:
            source_table, source_col = _TRACEABLE[table_name]
            if source_table == 'hardware':
                count = db.execute(
                    f"SELECT COUNT(*) FROM hardware WHERE {source_col} = ?", (row['name'],)
                ).fetchone()[0]
            else:
                count = db.execute(
                    f"SELECT COUNT(DISTINCT hardware_id) FROM {source_table} WHERE {source_col} = ?",
                    (row['name'],)
                ).fetchone()[0]
        items.append({'name': row['name'], 'count': count})

    # --- operational history ---
    valid_log_limits = (10, 25, 50, 100)
    try:
        log_limit = int(request.args.get('log_limit', 25))
        if log_limit not in valid_log_limits:
            log_limit = 25
    except (ValueError, TypeError):
        log_limit = 25

    history = []
    if traceable:
        source_table, source_col = _TRACEABLE[table_name]
        if source_table == 'hardware':
            history = db.execute(
                f"""SELECT hl.hardware_id, hl.timestamp, hl.action_type, hl.description,
                           h.id as hw_pk
                    FROM hardware_log hl
                    LEFT JOIN hardware h ON h.hardware_id = hl.hardware_id
                    WHERE h.{source_col} IN (SELECT name FROM {table_name})
                    ORDER BY hl.timestamp DESC LIMIT ?""",
                (log_limit,)
            ).fetchall()
        else:
            history = db.execute(
                f"""SELECT hl.hardware_id, hl.timestamp, hl.action_type, hl.description,
                           h.id as hw_pk
                    FROM hardware_log hl
                    LEFT JOIN hardware h ON h.hardware_id = hl.hardware_id
                    WHERE h.id IN (
                        SELECT DISTINCT hardware_id FROM {source_table}
                    )
                    ORDER BY hl.timestamp DESC LIMIT ?""",
                (log_limit,)
            ).fetchall()

    return render_template("simple_list.html", items=items, title=page_title,
                           table_name=table_name, traceable=traceable,
                           item_label=_item_label(table_name),
                           total=total, page=page, per_page=per_page,
                           total_pages=total_pages, page_list=page_list,
                           history=history, log_limit=log_limit)