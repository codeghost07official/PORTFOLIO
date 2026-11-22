"""Authentication (single administrator), CSRF, rate limiting, headers.

Hiding the login entry point is cosmetic; the real protection lives here:
hashed credentials, signed+expiring sessions with server-side revocation,
CSRF tokens on every state-changing request and DB-backed rate limiting.
"""
import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db

log = logging.getLogger("astra.security")

_epoch_cache = {"value": None, "at": 0.0}
_password_hash_cache = {}


# ---------------------------------------------------------------------------
# Client identity & rate limiting
# ---------------------------------------------------------------------------
def client_key():
    """Anonymised client identifier (hash of IP + secret)."""
    ip = request.remote_addr or "unknown"
    secret = current_app.config["SECRET_KEY"].encode()
    return hmac.new(secret, ip.encode(), hashlib.sha256).hexdigest()[:24]


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def rate_count(bucket, key, window_seconds):
    cutoff = _iso(datetime.now(timezone.utc) - timedelta(seconds=window_seconds))
    return int(
        db.scalar(
            "SELECT COUNT(*) AS c FROM rate_events WHERE bucket=? AND key=? AND created_at>?",
            (bucket, key, cutoff),
            default=0,
        )
    )


def rate_record(bucket, key):
    db.execute(
        "INSERT INTO rate_events(bucket, key, created_at) VALUES (?,?,?)",
        (bucket, key, _iso(datetime.now(timezone.utc))),
    )
    if secrets.randbelow(50) == 0:  # opportunistic cleanup
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=2))
        db.execute("DELETE FROM rate_events WHERE created_at<?", (cutoff,))


def rate_allow(bucket, key, limit, window_seconds, record=True):
    if rate_count(bucket, key, window_seconds) >= limit:
        return False
    if record:
        rate_record(bucket, key)
    return True


# ---------------------------------------------------------------------------
# Credentials & sessions
# ---------------------------------------------------------------------------
def credentials_configured():
    cfg = current_app.config
    return bool(cfg["ADMIN_USERNAME"] and (cfg["ADMIN_PASSWORD_HASH"] or cfg["ADMIN_PASSWORD"]))


def _expected_hash():
    cfg = current_app.config
    if cfg["ADMIN_PASSWORD_HASH"]:
        return cfg["ADMIN_PASSWORD_HASH"]
    plain = cfg["ADMIN_PASSWORD"]
    if plain not in _password_hash_cache:
        _password_hash_cache.clear()
        _password_hash_cache[plain] = generate_password_hash(plain)
    return _password_hash_cache[plain]


def verify_credentials(username, password):
    if not credentials_configured():
        return False
    expected_user = current_app.config["ADMIN_USERNAME"]
    user_ok = hmac.compare_digest((username or "").encode(), expected_user.encode())
    try:
        pass_ok = check_password_hash(_expected_hash(), password or "")
    except (ValueError, TypeError):
        log.error("ADMIN_PASSWORD_HASH is malformed")
        pass_ok = False
    return user_ok and pass_ok


# ---------------------------------------------------------------------------
# 4-digit PIN (primary login). Stored only as a salted scrypt hash in Turso.
# Brute force is impractical: per-IP and GLOBAL failure caps with lockouts.
# ---------------------------------------------------------------------------
PIN_RE = __import__("re").compile(r"^\d{4}$")
PIN_LIMITS = [  # (bucket key, window seconds, max failures) — any exceeded => locked
    ("ip", 15 * 60, 5),
    ("all", 15 * 60, 10),
    ("all", 24 * 3600, 30),
]


def pin_configured():
    return bool(db.scalar("SELECT value FROM meta WHERE key='admin_pin_hash'"))


def pin_lock_seconds():
    """Seconds until PIN entry is allowed again (0 when not locked)."""
    key = client_key()
    for scope, window, limit in PIN_LIMITS:
        if rate_count("pin_fail", key if scope == "ip" else "all", window) >= limit:
            return window
    return 0


def verify_pin(pin):
    stored = db.scalar("SELECT value FROM meta WHERE key='admin_pin_hash'")
    if not stored or not PIN_RE.match(pin or ""):
        return False
    try:
        return check_password_hash(stored, pin)
    except (ValueError, TypeError):
        return False


def record_pin_failure():
    rate_record("pin_fail", client_key())
    rate_record("pin_fail", "all")


def set_pin(pin):
    if not PIN_RE.match(pin or ""):
        raise ValueError("The PIN must be exactly 4 digits.")
    db.execute("INSERT INTO meta(key, value) VALUES('admin_pin_hash', ?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (generate_password_hash(pin, method="scrypt"),))


def _current_epoch():
    if time.time() - _epoch_cache["at"] < 15 and _epoch_cache["value"] is not None:
        return _epoch_cache["value"]
    value = db.scalar("SELECT value FROM meta WHERE key='session_epoch'")
    if value is None:
        value = secrets.token_hex(8)
        db.execute(
            "INSERT INTO meta(key, value) VALUES('session_epoch', ?) ON CONFLICT(key) DO NOTHING",
            (value,),
        )
        value = db.scalar("SELECT value FROM meta WHERE key='session_epoch'")
    _epoch_cache.update(value=value, at=time.time())
    return value


def revoke_all_sessions():
    value = secrets.token_hex(8)
    db.execute(
        "INSERT INTO meta(key, value) VALUES('session_epoch', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (value,),
    )
    _epoch_cache.update(value=value, at=time.time())


def login_user():
    session.clear()  # prevent session fixation
    # Browser-session cookie (no Expires): never remembered across a browser restart.
    # The absolute lifetime is enforced server-side in is_admin() via "auth_at".
    session.permanent = False
    now = int(time.time())
    session["admin"] = True
    session["epoch"] = _current_epoch()
    session["auth_at"] = session["seen"] = session["alive"] = now
    session["csrf"] = secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# "Fresh visit" gate: the PIN is required whenever the admin side is ENTERED,
# not on every internal navigation.
# ---------------------------------------------------------------------------
HEARTBEAT_PATH = "/api/admin/alive"
ALIVE_GRACE_SECONDS = 180  # an open admin tab pings every 60 s; a longer silence means it was closed


def _internal_referrer():
    ref = request.referrer
    if not ref:
        return False
    p = urlparse(ref)
    return p.netloc == request.host and (p.path.startswith("/admin") or p.path == current_app.config["ADMIN_LOGIN_PATH"])


def is_fresh_visit():
    """True when this request ENTERS the admin side: a top-level page load typed in the address bar,
    opened from a bookmark, the public site or another site, a restored tab, or any page load after the
    admin tab has been closed for a while. Client-side router fetches and API calls are never visits."""
    if request.method != "GET":
        return False
    mode = request.headers.get("Sec-Fetch-Mode")
    if mode and mode != "navigate":
        return False  # fetch() from an already-open admin page
    if request.headers.get("Sec-Fetch-Site") not in (None, "same-origin"):
        return True
    if not _internal_referrer():
        return True
    return int(time.time()) - int(session.get("alive", 0)) > ALIVE_GRACE_SECONDS


def end_visit():
    """Drop this browser's admin authentication (other devices unaffected)."""
    session.clear()


def note_alive():
    session["alive"] = int(time.time())


def logout_user():
    revoke_all_sessions()
    session.clear()


def is_admin():
    if not session.get("admin"):
        return False
    idle = current_app.config["SESSION_IDLE_MINUTES"] * 60
    seen = int(session.get("seen", 0))
    now = int(time.time())
    lifetime = int(current_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds())
    if now - seen > idle or now - int(session.get("auth_at", 0)) > lifetime:
        session.clear()
        return False
    try:
        if session.get("epoch") != _current_epoch():
            session.clear()
            return False
    except Exception:  # DB unreachable: fail closed
        log.exception("Session epoch check failed")
        return False
    if now - seen > 60 and request.path != HEARTBEAT_PATH:  # the heartbeat isn't user activity
        session["seen"] = now
    return True


def _wants_json():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            if _wants_json():
                return jsonify(error="Authentication required"), 401
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
def csrf_token():
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


def csrf_protect():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    expected = session.get("csrf") or ""
    if not expected or not hmac.compare_digest(sent.encode(), expected.encode()):
        if _wants_json():
            return jsonify(error="Invalid or missing CSRF token. Reload the page."), 400
        abort(400, description="Invalid CSRF token. Reload the page and try again.")


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "media-src 'self' https:; "
    "frame-src https://www.youtube-nocookie.com https://www.youtube.com; "
    "connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def apply_security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if current_app.config.get("IS_PRODUCTION"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith(("/api/admin", "/admin")) or request.path == current_app.config["ADMIN_LOGIN_PATH"]:
        response.headers["Cache-Control"] = "no-store"
    return response
