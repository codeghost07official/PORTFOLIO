"""Current mission / focus sessions. Doubles as lightweight time tracking."""
from ..db import db
from ..utils import ValidationError, now_iso, parse_iso
from .activity import log_event


def current():
    row = db.one(
        "SELECT f.*, p.name AS project_name, p.slug AS project_slug, p.status AS project_status, "
        "t.title AS task_title, t.status AS task_status FROM focus_sessions f "
        "LEFT JOIN projects p ON p.id=f.project_id LEFT JOIN tasks t ON t.id=f.task_id "
        "WHERE f.ended_at IS NULL ORDER BY f.id DESC LIMIT 1"
    )
    return row


def _end_open():
    db.execute("UPDATE focus_sessions SET ended_at=? WHERE ended_at IS NULL", (now_iso(),))


def set_focus(project_id=None, task_id=None, note=""):
    project_id = int(project_id) if project_id else None
    task_id = int(task_id) if task_id else None
    if task_id:
        task = db.one("SELECT id, project_id, title FROM tasks WHERE id=?", (task_id,))
        if not task:
            raise ValidationError({"task_id": "task not found"})
        project_id = project_id or task["project_id"]
    if project_id and not db.scalar("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValidationError({"project_id": "project not found"})
    if not project_id and not task_id and not (note or "").strip():
        raise ValidationError({"project_id": "choose a project, task or describe the mission"})
    _end_open()
    db.insert("INSERT INTO focus_sessions(project_id, task_id, note, started_at) VALUES (?,?,?,?)",
              (project_id, task_id, (note or "")[:300], now_iso()))
    cur = current()
    label = cur.get("task_title") or cur.get("project_name") or note
    log_event("focus", f"Focus set: {label}", project_id, "focus", cur["id"])
    if task_id and cur.get("task_status") in ("backlog", "todo"):
        from . import entities

        entities.update_item("tasks", task_id, {"status": "in_progress"})
    return current()


def clear_focus():
    _end_open()


def time_by_project(since=None):
    sql = ("SELECT f.project_id, p.name, f.started_at, f.ended_at FROM focus_sessions f "
           "LEFT JOIN projects p ON p.id=f.project_id WHERE f.project_id IS NOT NULL")
    params = []
    if since:
        sql += " AND (f.ended_at IS NULL OR f.ended_at>=?)"
        params.append(since)
    return summarise_time(db.query(sql, params), since)


def summarise_time(rows, since=None):
    totals = {}
    now = parse_iso(now_iso())
    since_dt = parse_iso(since) if since else None
    for r in rows:
        start, end = parse_iso(r["started_at"]), parse_iso(r["ended_at"]) or now
        if since_dt and start < since_dt:
            start = since_dt
        minutes = max(0, (end - start).total_seconds() / 60)
        key = r["project_id"]
        totals.setdefault(key, {"project_id": key, "name": r["name"] or "?", "minutes": 0})
        totals[key]["minutes"] += minutes
    out = sorted(totals.values(), key=lambda x: x["minutes"], reverse=True)
    for o in out:
        o["minutes"] = round(o["minutes"])
    return out
