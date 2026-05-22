import os
from flask import Flask, render_template

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

    @app.route('/')
    def index():
        from .db import get_db
        conn = get_db()

        status_rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM hardware GROUP BY status"
        ).fetchall()
        status_counts = {row['status']: row['count'] for row in status_rows}
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

    return app