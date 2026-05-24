import io
import os
import sqlite3 as _sqlite3
from datetime import datetime
from flask import Flask, render_template, send_file

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'hardware.db'),
    )

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import db
    db.init_app(app)

    from . import hardware
    app.register_blueprint(hardware.bp)

    from . import procedures
    app.register_blueprint(procedures.bp)

    from . import hazard_analyses
    app.register_blueprint(hazard_analyses.bp)

    from . import tps
    app.register_blueprint(tps.bp)

    @app.route('/')
    def index():
        from .db import get_db
        conn = get_db()

        open_tests = conn.execute("""
            SELECT pr.id, pr.run_id, pr.timestamp, pr.operator,
                   p.proc_id, p.title as proc_title, h.hardware_id
            FROM procedure_runs pr
            JOIN procedures p ON pr.procedure_id = p.id
            JOIN hardware h ON pr.hardware_id = h.id
            WHERE pr.status = 'In-Progress'
            ORDER BY pr.timestamp DESC
        """).fetchall()

        open_procedures = conn.execute("""
            SELECT id, proc_id, title, status, updated_at
            FROM procedures
            WHERE status = 'draft'
            ORDER BY updated_at DESC
        """).fetchall()

        open_tps = conn.execute("""
            SELECT id, tps_number, title, status, prepared_by, updated_at
            FROM tps
            WHERE status IN ('draft', 'in_progress')
            ORDER BY updated_at DESC
        """).fetchall()

        open_ha = conn.execute("""
            SELECT id, ha_id, title, status, updated_at
            FROM hazard_analyses
            WHERE status != 'approved'
            ORDER BY updated_at DESC
        """).fetchall()

        recent_activity = conn.execute("""
            SELECT hl.hardware_id, hl.timestamp, hl.action_type, hl.description,
                   h.id as hw_pk
            FROM hardware_log hl
            LEFT JOIN hardware h ON h.hardware_id = hl.hardware_id
            ORDER BY hl.timestamp DESC LIMIT 10
        """).fetchall()

        return render_template('home.html',
            open_tests=open_tests,
            open_procedures=open_procedures,
            open_tps=open_tps,
            open_ha=open_ha,
            recent_activity=recent_activity,
        )

    @app.route('/backup-db')
    def backup_db():
        db_path = app.config['DATABASE']
        tmp_path = os.path.join(app.instance_path, '_backup_tmp.db')
        # sqlite3.backup() gives a consistent snapshot even with concurrent writes
        src = _sqlite3.connect(db_path)
        dst = _sqlite3.connect(tmp_path)
        src.backup(dst)
        dst.close()
        src.close()
        buf = io.BytesIO()
        with open(tmp_path, 'rb') as f:
            buf.write(f.read())
        os.unlink(tmp_path)
        buf.seek(0)
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        return send_file(buf, as_attachment=True,
                         download_name=f'hardware_backup_{ts}.db',
                         mimetype='application/octet-stream')

    return app