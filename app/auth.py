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
        
        # Check if PIN exists
        user = db.execute(
            'SELECT * FROM personnel WHERE pin_code = ?', (pin,)
        ).fetchone()

        if user is None:
            error = 'Invalid PIN.'

        if error is None:
            # Success! Store user in session
            session.clear()
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_initials'] = user['initials']
            return redirect(url_for('hardware.hardware_list'))

        flash(error, 'error')

    return render_template('login.html')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

# --- HELPER: Decorator to protect routes ---
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

# --- LOAD USER BEFORE EVERY REQUEST ---
@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM personnel WHERE id = ?', (user_id,)
        ).fetchone()