from flask import Flask, request

from .auth import require_staff
from .db import create_db
from .docs import bp as docs_bp
from .routes import bp


def create_app(db=None):
    app = Flask(__name__)
    app.config["DB"] = db if db is not None else create_db()

    # Swap require_staff for the portal's real auth when merging.
    @app.before_request
    def _auth():
        if request.blueprint == bp.name:
            return require_staff()

    app.register_blueprint(bp)
    app.register_blueprint(docs_bp)  # /docs, /openapi.json (no auth needed)
    return app
