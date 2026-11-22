"""Single-administrator login: a 4-digit PIN for everyday use.

Modes
* pin    — normal login with the PIN (rate limited per IP and globally).
* setup  — first run: confirm identity with ADMIN_USERNAME + password from .env, then choose a PIN.
* reset  — forgot PIN: same password check, then choose a new PIN.
The PIN is stored only as a scrypt hash in Turso and is never sent to the browser.
"""
import logging
from urllib.parse import urlparse

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from ..security import (
    admin_required, client_key, credentials_configured, end_visit, login_user, logout_user, pin_configured,
    pin_lock_seconds, rate_count, rate_record, record_pin_failure, set_pin, verify_credentials, verify_pin,
)
from ..services.activity import log_event

bp = Blueprint("auth", __name__)
log = logging.getLogger("astra.auth")


def _safe_next(target):
    if not target:
        return url_for("admin.home")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/admin"):
        return url_for("admin.home")
    return target


def _minutes(seconds):
    return max(1, round(seconds / 60))


def login():
    cfg = current_app.config
    if request.method == "GET" and session.get("admin"):
        end_visit()  # opening the login page never skips the PIN: it starts a new visit
    has_pin = pin_configured()
    mode = request.values.get("mode") or ("pin" if has_pin else "setup")
    if mode not in ("pin", "setup", "reset") or (mode == "pin" and not has_pin):
        mode = "setup"
    error, status = None, 200

    if mode == "pin":
        lock = pin_lock_seconds()
        if lock:
            error, status = f"Too many incorrect PINs. Try again in about {_minutes(lock)} minutes, or reset with your password.", 429
        elif request.method == "POST":
            if verify_pin(request.form.get("pin", "")):
                login_user()
                log_event("login", "Administrator signed in")
                return redirect(_safe_next(request.args.get("next")))
            record_pin_failure()
            log.warning("Failed PIN attempt")
            error, status = "Incorrect PIN.", 401
    else:  # setup / reset: prove identity with the .env credentials, then choose a PIN
        key, window = client_key(), cfg["LOGIN_WINDOW_MINUTES"] * 60
        if not credentials_configured():
            error = "ADMIN_USERNAME and ADMIN_PASSWORD_HASH must be set in .env to create a PIN."
        elif rate_count("login_fail", key, window) >= cfg["LOGIN_MAX_ATTEMPTS"]:
            error, status = f"Too many failed attempts. Try again in {cfg['LOGIN_WINDOW_MINUTES']} minutes.", 429
        elif request.method == "POST":
            pin, confirm = request.form.get("new_pin", ""), request.form.get("confirm_pin", "")
            if not verify_credentials(request.form.get("username", ""), request.form.get("password", "")):
                rate_record("login_fail", key)
                log.warning("Failed admin password check (%s)", mode)
                error, status = "Username or password is incorrect.", 401
            elif pin != confirm:
                error, status = "The two PINs don't match.", 400
            else:
                try:
                    set_pin(pin)
                except ValueError as exc:
                    error, status = str(exc), 400
                else:
                    login_user()
                    log_event("login", "Administrator PIN " + ("created" if mode == "setup" else "reset"))
                    return redirect(_safe_next(request.args.get("next")))
    return render_template("admin/login.html", mode=mode, error=error, has_pin=has_pin,
                           configured=credentials_configured()), status


@bp.route("/admin/logout", methods=["POST"])
@admin_required
def logout():
    logout_user()
    return redirect(url_for("public.index"))


def register_login_route(state):
    state.add_url_rule(state.app.config["ADMIN_LOGIN_PATH"], "login", login, methods=["GET", "POST"])


bp.record(register_login_route)
