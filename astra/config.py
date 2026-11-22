"""Central configuration. Every value comes from environment variables so that
secrets never live in source code. See `.env.example` for documentation."""
import os
import secrets
from datetime import timedelta


def _bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    ENV = os.environ.get("ASTRA_ENV", "development").lower()
    IS_PRODUCTION = ENV == "production"

    # --- Flask / sessions -------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY") or ""
    SESSION_COOKIE_NAME = "astra_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_LIFETIME_HOURS", 8))
    SESSION_IDLE_MINUTES = _int("SESSION_IDLE_MINUTES", 120)
    MAX_CONTENT_LENGTH = _int("MAX_UPLOAD_MB", 4) * 1024 * 1024
    PREFERRED_URL_SCHEME = "https" if IS_PRODUCTION else "http"

    # --- Admin credentials (single administrator) -------------------------
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")  # dev convenience only
    ADMIN_LOGIN_PATH = "/" + os.environ.get("ADMIN_LOGIN_PATH", "gate").strip("/")
    LOGIN_MAX_ATTEMPTS = _int("LOGIN_MAX_ATTEMPTS", 5)
    LOGIN_WINDOW_MINUTES = _int("LOGIN_WINDOW_MINUTES", 15)

    # --- Database ----------------------------------------------------------
    TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "").strip()
    TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    TURSO_DRIVER = os.environ.get("TURSO_DRIVER", "http").strip().lower()  # http | libsql
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SEED_SAMPLE_DATA = _bool("SEED_SAMPLE_DATA", True)

    # --- Gemini -------------------------------------------------------------
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
    GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.7-flash,gemini-flash-latest").strip()
    GEMINI_PUBLIC_MODEL = os.environ.get("GEMINI_PUBLIC_MODEL", "").strip()  # optional cheaper model
    GEMINI_API_BASE = os.environ.get(
        "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    GEMINI_TIMEOUT = _int("GEMINI_TIMEOUT_SECONDS", 60)

    # --- Retrieval / embeddings --------------------------------------------
    EMBEDDINGS_PROVIDER = os.environ.get("EMBEDDINGS_PROVIDER", "gemini").strip().lower()  # gemini | none
    GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001").strip()
    EMBEDDING_DIM = _int("EMBEDDING_DIM", 768)

    # --- Public chatbot abuse protection -----------------------------------
    PUBLIC_CHAT_PER_IP_10MIN = _int("PUBLIC_CHAT_PER_IP_10MIN", 12)
    PUBLIC_CHAT_PER_IP_DAY = _int("PUBLIC_CHAT_PER_IP_DAY", 60)
    PUBLIC_CHAT_GLOBAL_DAY = _int("PUBLIC_CHAT_GLOBAL_DAY", 600)
    PUBLIC_CHAT_MAX_CHARS = _int("PUBLIC_CHAT_MAX_CHARS", 600)

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    @classmethod
    def finalize(cls, app_logger=None):
        """Fill development defaults and report misconfiguration."""
        warnings = []
        if not cls.SECRET_KEY:
            cls.SECRET_KEY = secrets.token_hex(32)
            warnings.append(
                "SECRET_KEY is not set: a random key was generated, sessions reset on restart."
            )
        if not cls.TURSO_DATABASE_URL or not cls.TURSO_AUTH_TOKEN:
            warnings.append("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN missing: ASTRA cannot start without Turso.")
        if not cls.ADMIN_USERNAME or not (cls.ADMIN_PASSWORD_HASH or cls.ADMIN_PASSWORD):
            warnings.append("Admin credentials are not configured: login is disabled.")
        if cls.ADMIN_PASSWORD and cls.IS_PRODUCTION:
            warnings.append("ADMIN_PASSWORD (plain text) is set in production; prefer ADMIN_PASSWORD_HASH.")
        if not cls.GEMINI_API_KEY:
            warnings.append("GEMINI_API_KEY is not set: AI features are offline.")
        if app_logger:
            for w in warnings:
                app_logger.warning(w)
        return warnings
