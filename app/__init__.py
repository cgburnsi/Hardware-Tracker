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

    @app.route('/')
    def index():
        from .db import get_db
        conn = get_db()

        status_rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM hardware GROUP BY status"
        ).fetchall()
        status_counts = {(row['status'] or '').lower(): row['count'] for row in status_rows}
        total_hw = sum(status_counts.values())

        recent_runs = conn.execute("""
            SELECT pr.run_id, pr.timestamp, pr.status, pr.operator,
                   p.proc_id, p.title, h.hardware_id
            FROM procedure_runs pr
            JOIN procedures p ON pr.procedure_id = p.id
            JOIN hardware h ON pr.hardware_id = h.id
            ORDER BY pr.timestamp DESC LIMIT 5
        """).fetchall()

        proc_count = conn.execute("SELECT COUNT(*) as c FROM procedures").fetchone()['c']

        return render_template('home.html',
            status_counts=status_counts,
            total_hw=total_hw,
            recent_runs=recent_runs,
            proc_count=proc_count,
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