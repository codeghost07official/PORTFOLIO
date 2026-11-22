"""ASTRA entry point.

Local:       python app.py      (requires Turso credentials in .env)
Production:  gunicorn app:app   (Render; see render.yaml)
"""
import os

from astra import create_app

app = create_app()


def _startup_summary(host, port):
    from astra.diagnostics import db_target

    cfg = app.config
    target = db_target(cfg)
    db_state = "connected" if cfg["DB_READY"] else f"UNAVAILABLE — {cfg['DB_ERROR'][:120]}"
    shown_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    lines = [
        "",
        "=" * 64,
        "  ASTRA — local development server",
        "-" * 64,
        f"  Site        : http://{shown_host}:{port}/",
        f"  Admin login : http://{shown_host}:{port}{cfg['ADMIN_LOGIN_PATH']}"
        + ("" if cfg["ADMIN_USERNAME"] else "   (credentials NOT configured)"),
        f"  Database    : {target['label']}",
        f"  DB status   : {db_state}",
        f"  Gemini      : {'configured · ' + cfg['GEMINI_MODEL'] if cfg['GEMINI_API_KEY'] else 'not configured (AI offline)'}",
        f"  Environment : {cfg['ENV']}",
    ]
    if not cfg["DB_READY"]:
        lines.append("  ERROR       : Turso is unavailable — pages will show the error until it is fixed.")
    if cfg["IS_PRODUCTION"]:
        lines.append("  WARNING     : ASTRA_ENV=production uses Secure cookies; login will fail over plain http://")
    lines += ["  Diagnostics : python scripts/check_setup.py", "=" * 64, ""]
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1" if not app.config["IS_PRODUCTION"] else "0") == "1"
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _startup_summary(host, port)  # print once (the debug reloader starts the app twice)
    app.run(host=host, port=port, debug=debug, use_reloader=debug)
