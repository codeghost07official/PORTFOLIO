"""ASTRA application factory."""
import logging
import os
import threading

from flask import Flask, jsonify, render_template, request

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

__version__ = "1.0.0"


def create_app():
    if load_dotenv:
        load_dotenv()
    from .config import Config

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    app = Flask(__name__, static_folder="static", template_folder="templates")
    warnings = Config.finalize(app.logger)
    app.config.from_object(Config)
    app.config["CONFIG_WARNINGS"] = warnings  # shown on the private settings page

    if app.config["IS_PRODUCTION"]:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    from .db import db
    from .db.schema import migrate
    from .db.seed import seed
    from .rag import indexer

    db.init(Config)
    indexer.init(app)
    app.config["DB_READY"] = False
    app.config["DB_ERROR"] = ""
    app.config["DB_LAST_TRY"] = 0.0
    init_database(app)

    _register_template_helpers(app)
    _register_blueprints(app)
    _register_hooks(app)
    _register_errors(app)

    if app.config["DB_READY"]:
        def warm_index():
            with app.app_context():
                try:
                    if not db.scalar("SELECT COUNT(*) FROM doc_chunks", default=0) and \
                            db.scalar("SELECT COUNT(*) FROM projects", default=0):
                        app.logger.info("Building retrieval index for the first time…")
                        indexer.rebuild_all()
                except Exception:
                    app.logger.exception("Initial index build failed")

        threading.Thread(target=warm_index, daemon=True).start()
    return app


def init_database(app):
    """Migrate + seed. On failure keep the error so it can be shown clearly (never a silent fallback)."""
    import time

    from .db.schema import migrate
    from .db.seed import seed
    from .diagnostics import explain_db_error

    app.config["DB_LAST_TRY"] = time.time()
    with app.app_context():
        try:
            migrate()
            seed()
            app.config["DB_READY"], app.config["DB_ERROR"] = True, ""
        except Exception as exc:
            app.config["DB_ERROR"] = str(exc)[:500]
            app.logger.error("DATABASE UNAVAILABLE: %s", exc)
            app.logger.error("Fix: %s", explain_db_error(str(exc)))
    return app.config["DB_READY"]


def _register_blueprints(app):
    from .routes.admin_pages import bp as admin_bp
    from .routes.ai_api import bp as ai_bp
    from .routes.api import bp as api_bp
    from .routes.auth import bp as auth_bp
    from .routes.life_api import bp as life_bp
    from .routes.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(life_bp)


def _register_template_helpers(app):
    from datetime import datetime

    from .markdown_render import markdown_excerpt, render_markdown
    from .security import csrf_token, is_admin
    from .services.constants import label

    app.jinja_env.filters["markdown"] = render_markdown
    app.jinja_env.filters["excerpt"] = markdown_excerpt
    app.jinja_env.filters["label"] = label

    def fmt_date(value, fmt="%d %b %Y"):
        if not value:
            return ""
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")[:19]).strftime(fmt)
        except ValueError:
            return value

    app.jinja_env.filters["date"] = fmt_date

    def _static_mtime():
        newest = 0.0
        for base, _, files in os.walk(app.static_folder):
            for f in files:
                newest = max(newest, os.path.getmtime(os.path.join(base, f)))
        return str(int(newest))

    static_version = {"v": _static_mtime()}  # cache-busting query string for CSS/JS

    if not app.config["IS_PRODUCTION"]:
        @app.before_request
        def _refresh_static_version():  # local dev: edits to CSS/JS show up on the next reload
            if not request.path.startswith("/static/"):
                static_version["v"] = _static_mtime()

    def site_appearance():
        from .services import settings as settings_svc

        try:
            return settings_svc.get("appearance")
        except Exception:
            return {"accent": "cyan", "effects": "lite"}

    def db_info():
        from .diagnostics import db_target

        return db_target(app.config)

    @app.context_processor
    def inject():
        return {
            "site_appearance": site_appearance,
            "csrf_token": csrf_token,
            "is_admin": is_admin,
            "login_path": app.config["ADMIN_LOGIN_PATH"],
            "asset_v": static_version["v"],
            "astra_version": __version__,
            "db_info": db_info,
            "debug_mode": app.debug or not app.config["IS_PRODUCTION"],
        }


def _register_hooks(app):
    from .security import apply_security_headers, csrf_protect

    @app.before_request
    def _before():
        if request.path.startswith("/static/") or request.path == "/healthz":
            return None
        if not app.config["DB_READY"] and request.endpoint not in ("public.health",):
            import time

            if time.time() - app.config["DB_LAST_TRY"] > 10:  # auto-retry, e.g. after Wi-Fi comes back
                init_database(app)
            if not app.config["DB_READY"]:
                from .diagnostics import db_target, explain_db_error

                if request.path.startswith("/api/"):
                    return jsonify(error=f"Database unavailable: {app.config['DB_ERROR']}"), 503
                return render_template(
                    "setup_error.html", error=app.config["DB_ERROR"] if not app.config["IS_PRODUCTION"] else "",
                    hint=explain_db_error(app.config["DB_ERROR"]), target=db_target(app.config),
                    show_target=not app.config["IS_PRODUCTION"]), 503
        return csrf_protect()

    app.after_request(apply_security_headers)


def _register_errors(app):
    from .ai.gemini import GeminiError
    from .db import DatabaseError
    from .utils import ValidationError

    def wants_json():
        return request.path.startswith("/api/")

    @app.errorhandler(ValidationError)
    def _validation(err):
        return jsonify(error="Please check the highlighted fields.", errors=err.errors), 400

    @app.errorhandler(GeminiError)
    def _gemini(err):
        status = err.status if err.status in (400, 401, 403, 404, 429, 503) else 502
        return jsonify(error=f"AI service: {err}"), status

    @app.errorhandler(DatabaseError)
    def _dberr(err):
        app.logger.exception("Database error")
        detail = "" if app.config["IS_PRODUCTION"] else f" ({err})"
        if wants_json():
            return jsonify(error=f"Database error{detail}. Please retry."), 500
        return render_template("error.html", code=500, message=f"A database error occurred{detail}."), 500

    for code, msg in ((400, "Bad request."), (403, "Forbidden."), (404, "This sector of the system does not exist."),
                      (405, "Method not allowed."), (413, "Upload too large."), (429, "Too many requests.")):
        def handler(err, code=code, msg=msg):
            desc = getattr(err, "description", None) or msg
            if wants_json():
                return jsonify(error=desc if code != 404 else "Not found"), code
            return render_template("error.html", code=code, message=desc if code == 400 else msg), code

        app.register_error_handler(code, handler)

    @app.errorhandler(500)
    def _server(err):
        original = getattr(err, "original_exception", None)
        detail = "" if app.config["IS_PRODUCTION"] or not original else f" ({original.__class__.__name__}: {original})"
        if wants_json():
            return jsonify(error=f"Internal server error{detail}"), 500
        return render_template("error.html", code=500, message=f"Something went wrong on our side{detail}."), 500
