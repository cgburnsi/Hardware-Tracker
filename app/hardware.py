from datetime import datetime
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from app.db import get_db

bp = Blueprint('hardware', __name__, url_prefix='/hardware')

def generate_new_hardware_id(db):
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
        try:
            # H25001 -> take last 3 chars -> int
            seq = int(row["hardware_id"][-3:]) + 1
        except ValueError:
            seq = 1
            
    return f"H{yy}{seq:03d}"

@bp.route('/')
def hardware_list():
    db = get_db()
    # ... logic for searching ...
    # Simplified for brevity, paste your search logic here
    items = db.execute("SELECT * FROM hardware").fetchall()
    return render_template('hardware_list.html', items=items)

@bp.route('/new', methods=('GET', 'POST'))
def hardware_new():
    if request.method == 'POST':
        description = request.form['description']
        # ... fetch other fields ...
        
        db = get_db()
        hw_id = generate_new_hardware_id(db)
        # ... Insert Logic ...
        
        # NOTE: When redirecting inside a blueprint, use 'blueprint_name.view_name'
        # return redirect(url_for('hardware.hardware_detail', id=...))
        
    return render_template('hardware_form.html')

@bp.route('/<int:id>')
def hardware_detail(id):
    item = get_db().execute('SELECT * FROM hardware WHERE id = ?', (id,)).fetchone()
    return render_template('hardware_detail.html', item=item)

# ... Add hardware_edit route here ...