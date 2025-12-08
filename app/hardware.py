from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.db import get_db

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
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/")
def hardware_list():
    db = get_db()
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    status = request.args.get("status", "").strip()

    query = "SELECT * FROM hardware WHERE 1=1"
    params = []

    if q:
        query += " AND (hardware_id LIKE ? OR description LIKE ? OR part_number LIKE ? OR ecn LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])

    if category:
        query += " AND category = ?"
        params.append(category)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY hardware_id DESC"

    cur = db.execute(query, params)
    items = cur.fetchall()

    # Get distinct categories and statuses for filters
    cats = db.execute("SELECT DISTINCT category FROM hardware WHERE category IS NOT NULL ORDER BY category").fetchall()
    stats = db.execute("SELECT DISTINCT status FROM hardware WHERE status IS NOT NULL ORDER BY status").fetchall()

    return render_template(
        "hardware_list.html",
        items=items,
        q=q,
        category=category,
        status=status,
        categories=[c["category"] for c in cats if c["category"]],
        statuses=[s["status"] for s in stats if s["status"]],
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
                
    items = db.execute("SELECT * FROM manufacturers ORDER BY name").fetchall()
    return render_template("manufacturer_list.html", items=items)

@bp.route("/<int:id>")
def hardware_detail(id):
    db = get_db()
    
    # 1. Get the Item
    cur = db.execute("SELECT * FROM hardware WHERE id = ?", (id,))
    item = cur.fetchone()
    
    # 2. Get the History Log
    log_cur = db.execute("SELECT * FROM hardware_log WHERE hardware_id = ? ORDER BY timestamp DESC", (id,))
    logs = log_cur.fetchall()

    if item is None:
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))
        
    # Pass 'logs' to the template
    return render_template("hardware_detail.html", item=item, logs=logs)

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
        ecn = request.form.get("ecn", "").strip()
        calibration_id = request.form.get("calibration_id", "").strip()
        repair_id = request.form.get("repair_id", "").strip()
        work_order_id = request.form.get("work_order_id", "").strip()
        
        # 3. Technical Specs
        port_configuration = request.form.get("port_configuration", "").strip()
        cv = request.form.get("cv", "").strip()
        orifice_diameter = request.form.get("orifice_diameter", "").strip()

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

        if not description:
            flash("Description is required.", "error")
            return render_template("hardware_form.html", item=None, **get_dropdown_data(db))

        hardware_id = generate_new_hardware_id(db)
        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """
            INSERT INTO hardware (
                hardware_id, description, category, classification, manufacturer, 
                part_number, serial_number, 
                ecn, calibration_id, repair_id, work_order_id,
                port_configuration, cv, orifice_diameter,
                status, custodian, location, 
                safety_class, propellant_or_media, cleaning_spec, compliance_specs, 
                max_rated_pressure, max_rated_temperature,
                traveler_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hardware_id, description, category, classification, manufacturer,
                part_number, serial_number, 
                ecn, calibration_id, repair_id, work_order_id,
                port_configuration, cv or None, orifice_diameter or None,
                status, custodian, location,
                safety_class, propellant_or_media, cleaning_spec, compliance_specs, 
                max_pressure or None, max_temp or None,
                traveler_path, now, now
            )
        )
        db.commit()
        flash(f"Created hardware {hardware_id}.", "success")
        
        row = db.execute("SELECT id FROM hardware WHERE hardware_id = ?", (hardware_id,)).fetchone()
        return redirect(url_for("hardware.hardware_detail", id=row["id"]))

    return render_template("hardware_form.html", item=None, **get_dropdown_data(db))

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
        ecn = request.form.get("ecn", "").strip()
        calibration_id = request.form.get("calibration_id", "").strip()
        repair_id = request.form.get("repair_id", "").strip()
        work_order_id = request.form.get("work_order_id", "").strip()
        
        # 3. Technical Specs
        port_configuration = request.form.get("port_configuration", "").strip()
        cv = request.form.get("cv", "").strip()
        orifice_diameter = request.form.get("orifice_diameter", "").strip()
        
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

        if not description:
            flash("Description is required.", "error")
            return render_template("hardware_form.html", item=item, **get_dropdown_data(db))

        now = datetime.utcnow().isoformat(timespec="seconds")

        # --- HISTORY LOG LOGIC ---
        changes = []
        
        # Check for meaningful changes
        # (We use 'or ""' to handle None vs Empty String mismatches safely)
        old_status = item['status'] or ""
        old_location = item['location'] or ""
        old_custodian = item['custodian'] or ""

        if status != old_status:
            changes.append(f"Status: '{old_status}' -> '{status}'")
        if location != old_location:
            changes.append(f"Location: '{old_location}' -> '{location}'")
        if custodian != old_custodian:
            changes.append(f"Custodian: '{old_custodian}' -> '{custodian}'")

        if changes:
            log_desc = "; ".join(changes)
            db.execute(
                "INSERT INTO hardware_log (hardware_id, timestamp, action_type, description) VALUES (?, ?, ?, ?)",
                (id, now, "Update", log_desc)
            )

        # --- SAVE UPDATE ---
        db.execute(
            """
            UPDATE hardware SET
                description=?, category=?, classification=?, manufacturer=?, 
                part_number=?, serial_number=?, 
                ecn=?, calibration_id=?, repair_id=?, work_order_id=?,
                port_configuration=?, cv=?, orifice_diameter=?,
                status=?, custodian=?, location=?, 
                safety_class=?, propellant_or_media=?, cleaning_spec=?, compliance_specs=?,
                max_rated_pressure=?, max_rated_temperature=?,
                traveler_path=?, updated_at=?
            WHERE id=?
            """,
            (
                description, category, classification, manufacturer,
                part_number, serial_number, 
                ecn, calibration_id, repair_id, work_order_id,
                port_configuration, cv or None, orifice_diameter or None,
                status, custodian, location,
                safety_class, propellant_or_media, cleaning_spec, compliance_specs,
                max_pressure or None, max_temp or None,
                traveler_path, now, id
            )
        )
        db.commit()
        flash("Hardware updated.", "success")
        return redirect(url_for("hardware.hardware_detail", id=id))

    # GET Request: Render form with item data AND dropdown lists
    return render_template("hardware_form.html", item=item, **get_dropdown_data(db))




# ... existing code ...

# --- GENERIC LIST HELPERS ---

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

def handle_simple_list(table_name, page_title):
    """Generic handler for simple name-only tables."""
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            try:
                # Safe injection: table_name is hardcoded in our routes above, not user input
                db.execute(f"INSERT INTO {table_name} (name) VALUES (?)", (name,))
                db.commit()
                flash(f"Added {name}", "success")
            except:
                flash("Item already exists.", "error")
    
    items = db.execute(f"SELECT * FROM {table_name} ORDER BY name").fetchall()
    return render_template("simple_list.html", items=items, title=page_title)