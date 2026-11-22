"""Local setup diagnostics: database connectivity (non-destructive self-test),
credentials, Gemini availability. Used by the startup summary, the setup-error
page, Settings → System and `python scripts/check_setup.py`.
Secrets are never included in any output."""
import os
import time
from urllib.parse import urlparse

from .db import db


def db_target(cfg):
    """Human-readable description of where data is stored."""
    url = cfg.get("TURSO_DATABASE_URL") or ""
    if not url:
        return {"mode": "missing", "label": "Turso NOT configured (TURSO_DATABASE_URL is empty)", "host": ""}
    host = urlparse(url.replace("libsql://", "https://")).hostname or "?"
    return {"mode": "turso", "label": f"Turso cloud ({cfg.get('TURSO_DRIVER', 'http')}) · {host}", "host": host}


def explain_db_error(message):
    m = (message or "").lower()
    if "401" in m or "unauthorized" in m or "jwt" in m or "token" in m and "invalid" in m:
        return ("Turso rejected the auth token. Create a new one (dashboard → database → Create Token, or "
                "`turso db tokens create <db>`) and update TURSO_AUTH_TOKEN in .env.")
    if "404" in m or "not found" in m:
        return "The database URL was not found. Copy the exact libsql:// URL from the Turso dashboard into TURSO_DATABASE_URL."
    if any(k in m for k in ("getaddrinfo", "name or service", "failed to resolve", "nodename", "connection failed",
                            "max retries", "connection refused", "network")):
        return "Could not reach Turso. Check your internet connection, VPN/firewall, and the hostname in TURSO_DATABASE_URL."
    if "timeout" in m or "timed out" in m:
        return "Turso did not answer in time. Check your connection and try again."
    if "libsql" in m and "install" in m:
        return "Set TURSO_DRIVER=http (default) or install the optional `libsql` package."
    if "not set" in m or "must be a turso url" in m:
        return ("Add your Turso database URL (libsql://…turso.io) and auth token to .env as "
                "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN, then restart: python app.py")
    return "Check TURSO_DATABASE_URL / TURSO_AUTH_TOKEN in .env, then restart, or run: python scripts/check_setup.py"


def check_database():
    """Connect, measure latency, and run a write/read/delete self-test on a scratch table."""
    out = []
    try:
        t0 = time.perf_counter()
        db.scalar("SELECT 1")
        ms = round((time.perf_counter() - t0) * 1000)
        out.append({"name": "Database connection", "ok": True, "detail": f"{db.driver_name}, {ms} ms round trip"})
    except Exception as exc:
        out.append({"name": "Database connection", "ok": False, "detail": str(exc)[:300], "hint": explain_db_error(str(exc))})
        return out
    try:
        token = str(int(time.time() * 1000))
        db.batch([
            ("CREATE TABLE IF NOT EXISTS _astra_selftest (id INTEGER PRIMARY KEY, v TEXT)", ()),
            ("INSERT INTO _astra_selftest (v) VALUES (?)", (token,)),
        ])
        got = db.scalar("SELECT v FROM _astra_selftest WHERE v=?", (token,))
        db.batch([("DELETE FROM _astra_selftest WHERE v=?", (token,)), ("DROP TABLE IF EXISTS _astra_selftest", ())])
        out.append({"name": "Write / read / delete", "ok": got == token,
                    "detail": "self-test row written, read back and removed" if got == token else "read-back mismatch"})
    except Exception as exc:
        out.append({"name": "Write / read / delete", "ok": False, "detail": str(exc)[:300], "hint": explain_db_error(str(exc))})
    try:
        ver = db.scalar("SELECT value FROM meta WHERE key='schema_version'")
        counts = {t: db.scalar(f"SELECT COUNT(*) FROM {t}", default=0) for t in ("projects", "tasks", "journals", "media")}
        out.append({"name": "Schema", "ok": bool(ver), "detail": f"version {ver} · " + ", ".join(f"{k} {v}" for k, v in counts.items())})
    except Exception as exc:
        out.append({"name": "Schema", "ok": False, "detail": str(exc)[:200], "hint": "Restart the app to run migrations."})
    return out


def check_config(cfg):
    out = []
    env_path = os.path.join(cfg.get("PROJECT_ROOT", "."), ".env")
    out.append({"name": ".env file", "ok": os.path.exists(env_path),
                "detail": env_path if os.path.exists(env_path) else "not found",
                "hint": "Create .env next to app.py (copy .env.example) and fill in your values."})
    out.append({"name": "SECRET_KEY", "ok": bool(os.environ.get("SECRET_KEY")),
                "detail": "set" if os.environ.get("SECRET_KEY") else "missing — sessions reset on every restart",
                "hint": 'Add SECRET_KEY to .env: python -c "import secrets; print(secrets.token_hex(32))"'})
    has_user = bool(cfg.get("ADMIN_USERNAME"))
    has_pw = bool(cfg.get("ADMIN_PASSWORD_HASH") or cfg.get("ADMIN_PASSWORD"))
    out.append({"name": "Admin credentials", "ok": has_user and has_pw,
                "detail": ("hashed password" if cfg.get("ADMIN_PASSWORD_HASH") else "plain-text password (dev)")
                if has_user and has_pw else "ADMIN_USERNAME / ADMIN_PASSWORD_HASH missing — login disabled",
                "hint": "Run python scripts/hash_password.py and put the result in .env."})
    if cfg.get("ADMIN_PASSWORD_HASH"):
        h = cfg["ADMIN_PASSWORD_HASH"]
        ok = h.startswith(("scrypt:", "pbkdf2:")) and h.count("$") >= 2
        out.append({"name": "Password hash format", "ok": ok, "detail": "valid" if ok else "looks truncated or malformed",
                    "hint": "In .env wrap the hash in single quotes so no characters are lost."})
    target = db_target(cfg)
    out.append({"name": "Storage target", "ok": target["mode"] == "turso", "detail": target["label"],
                "hint": "Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in .env."})
    return out


def check_gemini(cfg):
    from .ai import gemini

    if not cfg.get("GEMINI_API_KEY"):
        return [{"name": "Gemini API", "ok": False, "detail": "GEMINI_API_KEY not set — AI features offline",
                 "hint": "Create a key at https://aistudio.google.com/apikey and add it to .env."}]
    out = []
    try:
        models = {m["id"] for m in gemini.list_models() if m["generate"]}
        out.append({"name": "Gemini API", "ok": True, "detail": f"key accepted, {len(models)} generation models available"})
        for key in ("GEMINI_MODEL", "GEMINI_FALLBACK_MODEL"):
            mid = cfg.get(key)
            if mid:
                ok = mid in models
                out.append({"name": key, "ok": ok, "warn": not ok and key == "GEMINI_MODEL",
                            "detail": f"{mid} " + ("available" if ok else "NOT available to this key"),
                            "hint": "Pick an ID from Settings → AI → List models." if not ok else ""})
    except Exception as exc:
        out.append({"name": "Gemini API", "ok": False, "detail": str(exc)[:300],
                    "hint": "Check GEMINI_API_KEY and your internet connection."})
    return out


def run_all(cfg, include_ai=True):
    checks = check_config(cfg) + check_database()
    if include_ai:
        checks += check_gemini(cfg)
    return checks
