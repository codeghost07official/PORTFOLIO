"""Small shared helpers: time, slugs, JSON, validation."""
import json
import re
import unicodedata
from datetime import datetime, timezone, date
from urllib.parse import urlparse


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso():
    return datetime.now(timezone.utc).date().isoformat()


def local_today():
    """The owner's calendar day (server-local time). Personal features prefer the browser's date when sent."""
    return date.today().isoformat()


def client_today(value):
    """Validate a YYYY-MM-DD date sent by the browser; fall back to local_today()."""
    try:
        return date.fromisoformat(str(value)[:10]).isoformat() if value else local_today()
    except ValueError:
        return local_today()


def parse_iso(value):
    if not value:
        return None
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def slugify(text, max_len=80):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:max_len].strip("-")) or "project"


def jloads(value, default=None):
    if value is None or value == "":
        return [] if default is None else default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return [] if default is None else default


def jdumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors if isinstance(errors, dict) else {"_": str(errors)}
        super().__init__("; ".join(f"{k}: {v}" for k, v in self.errors.items()))


def clean_url(value, field="url"):
    """Accept only http(s) / mailto URLs or app-relative paths. Returns '' for empty."""
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return value
    if parsed.scheme == "mailto" and parsed.path:
        return value
    raise ValidationError({field: "must be an http(s) URL"})


def clean_date(value, field="date"):
    value = (value or "").strip() if isinstance(value, str) else value
    if not value:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        raise ValidationError({field: "must be a date (YYYY-MM-DD)"})


def clean_tags(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    tags = []
    for t in value:
        t = str(t).strip()[:40]
        if t and t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    return tags[:30]


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def truncate(text, n):
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def youtube_embed(url):
    """Return a privacy-friendly embed URL for a YouTube link, or ''."""
    if not url:
        return ""
    m = re.search(r"(?:youtu\.be/|v=|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url)
    return f"https://www.youtube-nocookie.com/embed/{m.group(1)}" if m else ""
