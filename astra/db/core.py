"""Database access layer.

Turso is the ONLY persistent store. Two interchangeable Turso drivers expose the
same tiny API (query / one / scalar / execute / batch / many); all SQL is
parameterised with `?` placeholders.

* ``http``   – Turso's official HTTP (Hrana v2 pipeline) API. Pure Python. Default.
* ``libsql`` – Turso's official ``libsql`` Python SDK, if you install it.

There is deliberately no local/SQLite fallback: if Turso is not configured or not
reachable, every query raises DatabaseError with a clear message.
"""
import base64
import logging
import threading

log = logging.getLogger("astra.db")


class DatabaseError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------
class _HttpDriver:
    """Turso / libSQL server over HTTP: POST {url}/v2/pipeline."""

    name = "turso-http"

    def __init__(self, url, token):
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        elif url.startswith("wss://"):
            url = "https://" + url[len("wss://"):]
        elif url.startswith("ws://"):
            url = "http://" + url[len("ws://"):]
        self.endpoint = url.rstrip("/") + "/v2/pipeline"
        self.token = token
        self._local = threading.local()

    def _session(self):
        sess = getattr(self._local, "session", None)
        if sess is None:
            import requests

            sess = requests.Session()
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            sess.headers.update(headers)
            self._local.session = sess
        return sess

    @staticmethod
    def _encode(value):
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "integer", "value": "1" if value else "0"}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        if isinstance(value, (bytes, bytearray, memoryview)):
            return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode().rstrip("=")}
        return {"type": "text", "value": str(value)}

    @staticmethod
    def _decode(cell):
        kind = cell.get("type")
        if kind == "null":
            return None
        if kind == "integer":
            return int(cell["value"])
        if kind == "float":
            return float(cell["value"])
        if kind == "blob":
            data = cell.get("base64", "")
            return base64.b64decode(data + "=" * (-len(data) % 4))
        return cell.get("value")

    def run(self, statements):
        requests_payload = [
            {
                "type": "execute",
                "stmt": {"sql": sql, "args": [self._encode(p) for p in (params or ())]},
            }
            for sql, params in statements
        ]
        requests_payload.append({"type": "close"})
        import requests

        resp = None
        for attempt in (1, 2):
            try:
                resp = self._session().post(self.endpoint, json={"requests": requests_payload}, timeout=30)
                break
            except requests.ConnectionError as exc:
                # a pooled keep-alive socket went stale (sleep/Wi-Fi change): reconnect once
                self._local.session = None
                if attempt == 2:
                    raise DatabaseError(f"Turso connection failed: {exc}") from exc
            except Exception as exc:  # timeout or other network failure
                self._local.session = None
                raise DatabaseError(f"Turso connection failed: {exc}") from exc
        if resp.status_code >= 400:
            raise DatabaseError(f"Turso HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        results = []
        for item in data.get("results", [])[: len(statements)]:
            if item.get("type") != "ok":
                msg = (item.get("error") or {}).get("message", "unknown error")
                raise DatabaseError(msg)
            res = item["response"]["result"]
            cols = [c.get("name") for c in res.get("cols", [])]
            rows = [
                {cols[i]: self._decode(cell) for i, cell in enumerate(row)}
                for row in res.get("rows", [])
            ]
            last_id = res.get("last_insert_rowid")
            results.append(
                (rows, int(last_id) if last_id not in (None, "") else None, res.get("affected_row_count", 0))
            )
        return results


class _LibsqlDriver:
    name = "turso-libsql"

    def __init__(self, url, token):
        try:
            import libsql  # type: ignore
        except ImportError:
            try:
                import libsql_experimental as libsql  # type: ignore
            except ImportError as exc:
                raise DatabaseError(
                    "TURSO_DRIVER=libsql but the 'libsql' package is not installed."
                ) from exc
        self._lib = libsql
        self.url, self.token = url, token
        self._local = threading.local()

    def _conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._lib.connect(self.url, auth_token=self.token)
            self._local.conn = conn
        return conn

    def run(self, statements):
        conn = self._conn()
        results = []
        try:
            for sql, params in statements:
                cur = conn.execute(sql, tuple(params or ()))
                rows = []
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                results.append((rows, getattr(cur, "lastrowid", None), getattr(cur, "rowcount", 0)))
            conn.commit()
        except Exception as exc:
            self._local.conn = None
            raise DatabaseError(str(exc)) from exc
        return results


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------
class Database:
    REMOTE_SCHEMES = ("libsql://", "https://", "http://", "wss://", "ws://")

    def __init__(self):
        self.driver = None
        self.config_error = "Database not initialised"

    def init(self, config):
        url = (config.TURSO_DATABASE_URL or "").strip()
        token = (config.TURSO_AUTH_TOKEN or "").strip()
        self.driver = None
        if not url:
            self.config_error = "TURSO_DATABASE_URL is not set in .env — ASTRA requires a Turso database."
        elif not url.startswith(self.REMOTE_SCHEMES):
            self.config_error = (f"TURSO_DATABASE_URL must be a Turso URL (libsql://…turso.io); "
                                 f"local/file databases are not supported.")
        elif not token:
            self.config_error = "TURSO_AUTH_TOKEN is not set in .env."
        else:
            self.config_error = ""
            if config.TURSO_DRIVER == "libsql":
                self.driver = _LibsqlDriver(url, token)
            else:
                self.driver = _HttpDriver(url, token)
            log.info("Database driver: %s", self.driver.name)
        if self.config_error:
            log.error("Database not configured: %s", self.config_error)

    @property
    def driver_name(self):
        return self.driver.name if self.driver else "uninitialised"

    def _run(self, statements):
        if self.driver is None:
            raise DatabaseError(self.config_error or "Database not initialised")
        is_read = all(s[0].lstrip().upper().startswith(("SELECT", "WITH", "PRAGMA")) for s in statements)
        try:
            return self.driver.run(statements)
        except DatabaseError:
            if not is_read:
                raise
            log.warning("Read failed, retrying once")
            return self.driver.run(statements)  # one retry for idempotent reads

    def query(self, sql, params=()):
        return self._run([(sql, params)])[0][0]

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql, params=(), default=None):
        row = self.one(sql, params)
        if not row:
            return default
        val = next(iter(row.values()))
        return default if val is None else val

    def execute(self, sql, params=()):
        """Run a write statement. Returns (lastrowid, rowcount)."""
        _, last_id, count = self._run([(sql, params)])[0]
        return last_id, count

    def insert(self, sql, params=()):
        return self.execute(sql, params)[0]

    def many(self, statements):
        """Run several read queries in ONE round trip (one HTTP request on Turso).
        Returns a list of row-lists in the same order."""
        statements = [(s, p) for s, p in statements]
        if not statements:
            return []
        return [r[0] for r in self._run(statements)]

    def batch(self, statements):
        statements = [(s, p) for s, p in statements]
        if not statements:
            return []
        return self._run(statements)


db = Database()


def split_sql(script):
    """Split a schema script into statements (no semicolons inside literals)."""
    parts = [p.strip() for p in script.split(";")]
    return [p for p in parts if p and not all(l.strip().startswith("--") for l in p.splitlines() if l.strip())]
