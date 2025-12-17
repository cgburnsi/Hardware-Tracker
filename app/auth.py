import functools
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from app.db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        pin = request.form['pin']
        db = get_db()
        error = None
        
        user = db.execute(
            'SELECT * FROM personnel WHERE pin_code = ?', (pin,)
        ).fetchone()

        if user is None:
            error = 'Invalid PIN.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_initials'] = user['initials']
            
            # If they were trying to go somewhere specific, send them there
            # otherwise, go to hardware list
            return redirect(url_for('hardware.hardware_list'))

        flash(error, 'error')

    return render_template('login.html')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

# --- NEW: Add Teammate Route ---
@bp.route('/register', methods=('GET', 'POST'))
def register():
    # 1. Protect this route: Only logged-in users can add new people
    if g.user is None:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        initials = request.form['initials'].strip().upper()
        pin = request.form['pin'].strip()
        role = request.form['role']
        db = get_db()
        error = None

        if not name:
            error = 'Name is required.'
        elif not pin or len(pin) != 3:
            error = 'PIN must be exactly 3 digits.'
        elif not initials:
            error = 'Initials are required.'

        if error is None:
            try:
                db.execute(
                    "INSERT INTO personnel (name, initials, pin_code, role) VALUES (?, ?, ?, ?)",
                    (name, initials, pin, role)
                )
                db.commit()
                flash(f"Teammate {name} ({initials}) added successfully.", "success")
                return redirect(url_for('auth.register')) # Stay on page to add another?
            except db.IntegrityError:
                error = f"The PIN '{pin}' is already registered to someone else."

        flash(error, 'error')

    # Show list of current users below the form for reference
    db = get_db()
    users = db.execute("SELECT * FROM personnel ORDER BY name").fetchall()
    
    return render_template('register.html', users=users)

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM personnel WHERE id = ?', (user_id,)
        ).fetchone()

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view



@bp.route('/change-pin', methods=('GET', 'POST'))
def change_pin():
    if g.user is None:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        current_pin = request.form['current_pin'].strip()
        new_pin = request.form['new_pin'].strip()
        db = get_db()
        error = None

        # 1. Verify Current PIN
        if current_pin != g.user['pin_code']:
            error = "Current PIN is incorrect."
        
        # 2. Validate New PIN
        elif not new_pin or len(new_pin) != 3 or not new_pin.isdigit():
            error = "New PIN must be exactly 3 digits."
            
        # 3. Check Uniqueness (Optional but recommended)
        else:
            existing = db.execute("SELECT id FROM personnel WHERE pin_code = ? AND id != ?", (new_pin, g.user['id'])).fetchone()
            if existing:
                error = f"PIN '{new_pin}' is already in use by another user."

        if error is None:
            db.execute("UPDATE personnel SET pin_code = ? WHERE id = ?", (new_pin, g.user['id']))
            db.commit()
            flash("Your PIN has been updated.", "success")
            return redirect(url_for('auth.register'))

        flash(error, 'error')

    return render_template('change_pin.html')




