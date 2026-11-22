"""Activity timeline: real events written by the services layer."""
import logging

from ..db import db
from ..utils import now_iso, truncate

log = logging.getLogger("astra.activity")


def log_event(kind, title, project_id=None, entity_type="", entity_id=None, detail=""):
    try:
        db.execute(
            "INSERT INTO activity(project_id, kind, title, detail, entity_type, entity_id, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (project_id, kind, truncate(title, 240), truncate(detail, 500), entity_type, entity_id, now_iso()),
        )
    except Exception:  # never break the main write because of the timeline
        log.exception("Could not record activity")


def recent(limit=30, project_id=None, since=None, kind=None):
    sql = (
        "SELECT a.*, p.name AS project_name, p.slug AS project_slug FROM activity a "
        "LEFT JOIN projects p ON p.id = a.project_id WHERE 1=1"
    )
    params = []
    if project_id:
        sql += " AND a.project_id=?"
        params.append(project_id)
    if since:
        sql += " AND a.created_at>=?"
        params.append(since)
    if kind:
        sql += " AND a.kind=?"
        params.append(kind)
    sql += " ORDER BY a.created_at DESC, a.id DESC LIMIT ?"
    params.append(int(limit))
    return db.query(sql, params)
