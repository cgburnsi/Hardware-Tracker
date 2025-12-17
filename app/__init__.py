import os
from flask import Flask, redirect, url_for

def create_app():
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'hardware.db'),
    )

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Register Database Functions
    from . import db
    db.init_app(app)

    # Authentication Blueprint
    from . import auth
    app.register_blueprint(auth.bp)
    
    # Register Hardware Blueprint
    from . import hardware
    app.register_blueprint(hardware.bp)

    # Register Procedures Blueprint
    from . import procedures
    app.register_blueprint(procedures.bp)

    # Root route redirects to hardware list
    @app.route('/')
    def index():
        return redirect(url_for('hardware.hardware_list'))

    return app