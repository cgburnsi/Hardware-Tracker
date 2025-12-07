from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.db import get_db

bp = Blueprint('hardware', __name__, url_prefix='/hardware')

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

@bp.route("/")
def hardware_list():
    db = get_db()
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    status = request.args.get("status", "").strip()

    query = "SELECT * FROM hardware WHERE 1=1"
    params = []

    if q:
        query += " AND (hardware_id LIKE ? OR description LIKE ? OR part_number LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])

    if category:
        query += " AND category = ?"
        params.append(category)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY hardware_id DESC"

    cur = db.execute(query, params)
    items = cur.fetchall()

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

# --- NEW ROUTE: Manufacturer Management ---
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
    cur = db.execute("SELECT * FROM hardware WHERE id = ?", (id,))
    item = cur.fetchone()
    if item is None:
        flash("Hardware not found.", "error")
        return redirect(url_for("hardware.hardware_list"))
    return render_template("hardware_detail.html", item=item)

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
        
        # 2. Status
        status = request.form.get("status", "").strip()
        custodian = request.form.get("custodian", "").strip()
        location = request.form.get("location", "").strip()
        traveler_path = request.form.get("traveler_path", "").strip()
        
        # 3. Safety
        safety_class = request.form.get("safety_class", "").strip()
        propellant_or_media = request.form.get("propellant_or_media", "").strip()
        max_pressure = request.form.get("max_rated_pressure", "").strip()
        max_temp = request.form.get("max_rated_temperature", "").strip()

        if not description:
            flash("Description is required.", "error")
            # We must pass manufacturers here too in case of error!
            manufs = db.execute("SELECT name FROM manufacturers ORDER BY name").fetchall()
            return render_template("hardware_form.html", item=None, manufacturers=manufs)

        hardware_id = generate_new_hardware_id(db)
        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """
            INSERT INTO hardware (
                hardware_id, description, category, classification, manufacturer, 
                part_number, serial_number, status, custodian, location, 
                safety_class, propellant_or_media, max_rated_pressure, max_rated_temperature,
                traveler_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hardware_id, description, category, classification, manufacturer,
                part_number, serial_number, status, custodian, location,
                safety_class, propellant_or_media, max_pressure or None, max_temp or None,
                traveler_path, now, now
            )
        )
        db.commit()
        flash(f"Created hardware {hardware_id}.", "success")
        
        row = db.execute("SELECT id FROM hardware WHERE hardware_id = ?", (hardware_id,)).fetchone()
        return redirect(url_for("hardware.hardware_detail", id=row["id"]))

    # GET: Fetch manufacturers list
    manufs = db.execute("SELECT name FROM manufacturers ORDER BY name").fetchall()
    return render_template("hardware_form.html", item=None, manufacturers=manufs)

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
        
        # 2. Status
        status = request.form.get("status", "").strip()
        custodian = request.form.get("custodian", "").strip()
        location = request.form.get("location", "").strip()
        traveler_path = request.form.get("traveler_path", "").strip()
        
        # 3. Safety
        safety_class = request.form.get("safety_class", "").strip()
        propellant_or_media = request.form.get("propellant_or_media", "").strip()
        max_pressure = request.form.get("max_rated_pressure", "").strip()
        max_temp = request.form.get("max_rated_temperature", "").strip()

        if not description:
            flash("Description is required.", "error")
            manufs = db.execute("SELECT name FROM manufacturers ORDER BY name").fetchall()
            return render_template("hardware_form.html", item=item, manufacturers=manufs)

        now = datetime.utcnow().isoformat(timespec="seconds")

        db.execute(
            """
            UPDATE hardware SET
                description=?, category=?, classification=?, manufacturer=?, 
                part_number=?, serial_number=?, status=?, custodian=?, location=?, 
                safety_class=?, propellant_or_media=?, max_rated_pressure=?, max_rated_temperature=?,
                traveler_path=?, updated_at=?
            WHERE id=?
            """,
            (
                description, category, classification, manufacturer,
                part_number, serial_number, status, custodian, location,
                safety_class, propellant_or_media, max_pressure or None, max_temp or None,
                traveler_path, now, id
            )
        )
        db.commit()
        flash("Hardware updated.", "success")
        return redirect(url_for("hardware.hardware_detail", id=id))

    # GET: Fetch manufacturers list
    manufs = db.execute("SELECT name FROM manufacturers ORDER BY name").fetchall()
    return render_template("hardware_form.html", item=item, manufacturers=manufs)