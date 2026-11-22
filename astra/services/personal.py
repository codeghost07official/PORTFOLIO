"""Personal OS: simple to-do list (Tasks) and personal daily journal (Journaling)."""
from datetime import date, timedelta

from ..db import db
from ..utils import ValidationError, clean_date, local_today, now_iso, to_bool

TODO_PRIORITIES = ["low", "medium", "high"]


def _reindex(kind, rid, delete=False):
    from ..rag import indexer

    indexer.remove(kind, rid) if delete else indexer.schedule(kind, rid)


# ===========================================================================
# Tasks (to-dos)
# ===========================================================================
def _todo_values(data, partial=False):
    out = {}
    if "title" in data or not partial:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValidationError({"title": "Give the task a title."})
        if len(title) > 200:
            raise ValidationError({"title": "max 200 characters"})
        out["title"] = title
    if "description" in data:
        out["description"] = str(data.get("description") or "")[:10000]
    if "priority" in data:
        pr = data.get("priority") or None
        if pr is not None and pr not in TODO_PRIORITIES:
            raise ValidationError({"priority": "choose low, medium, high or none"})
        out["priority"] = pr
    if "due_date" in data:
        out["due_date"] = clean_date(data.get("due_date"), "due_date")
    if "completed" in data:
        out["completed_at"] = now_iso() if to_bool(data["completed"]) else None
    return out


def todo_get(tid):
    return db.one("SELECT * FROM todos WHERE id=?", (int(tid),))


def todo_create(data):
    v = _todo_values(data)
    ts = now_iso()
    v.update(created_at=ts, updated_at=ts)
    cols = list(v)
    tid = db.insert(f"INSERT INTO todos ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [v[c] for c in cols])
    _reindex("todo", tid)
    return todo_get(tid)


def todo_update(tid, data):
    if not todo_get(tid):
        return None
    v = _todo_values(data, partial=True)
    if v:
        v["updated_at"] = now_iso()
        db.execute(f"UPDATE todos SET {', '.join(f'{c}=?' for c in v)} WHERE id=?", [*v.values(), int(tid)])
        _reindex("todo", tid)
    return todo_get(tid)


def todo_delete(tid):
    if not todo_get(tid):
        return False
    db.execute("DELETE FROM todos WHERE id=?", (int(tid),))
    _reindex("todo", tid, delete=True)
    return True


PRIO_ORDER = "CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END"


def todo_list(view="all", q=None, priority=None, sort="smart", today=None):
    today = today or local_today()
    sql, params = "SELECT * FROM todos WHERE 1=1", []
    if view == "today":
        sql += " AND completed_at IS NULL AND due_date IS NOT NULL AND due_date <= ?"
        params.append(today)
    elif view == "upcoming":
        sql += " AND completed_at IS NULL AND due_date > ?"
        params.append(today)
    elif view == "completed":
        sql += " AND completed_at IS NOT NULL"
    elif view == "open":
        sql += " AND completed_at IS NULL"
    if priority == "none":
        sql += " AND priority IS NULL"
    elif priority in TODO_PRIORITIES:
        sql += " AND priority=?"
        params.append(priority)
    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        params += [f"%{q.strip()}%"] * 2
    orders = {
        "smart": f"CASE WHEN completed_at IS NULL THEN 0 ELSE 1 END, CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, "
                 f"due_date, {PRIO_ORDER}, created_at DESC",
        "due": "CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date, created_at DESC",
        "priority": f"{PRIO_ORDER}, created_at DESC",
        "newest": "created_at DESC",
        "oldest": "created_at",
    }
    if view == "completed":
        sql += " ORDER BY completed_at DESC"
    else:
        sql += f" ORDER BY {orders.get(sort, orders['smart'])}"
    return db.query(sql + " LIMIT 1000", params)


def todo_stats(today=None):
    today_d = date.fromisoformat(today or local_today())
    t = today_d.isoformat()
    week_end = (today_d + timedelta(days=7)).isoformat()
    day0 = today_d - timedelta(days=29)
    head, done_rows, created_rows, prio = db.many([
        ("SELECT COUNT(*) AS total, SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) AS done, "
         "SUM(CASE WHEN completed_at IS NULL AND due_date < ? THEN 1 ELSE 0 END) AS overdue, "
         "SUM(CASE WHEN completed_at IS NULL AND due_date = ? THEN 1 ELSE 0 END) AS due_today, "
         "SUM(CASE WHEN completed_at IS NULL AND due_date > ? AND due_date <= ? THEN 1 ELSE 0 END) AS due_week "
         "FROM todos", (t, t, t, week_end)),
        ("SELECT substr(completed_at,1,10) AS d, COUNT(*) AS n FROM todos WHERE completed_at >= ? GROUP BY 1",
         (day0.isoformat(),)),
        ("SELECT substr(created_at,1,10) AS d, COUNT(*) AS n FROM todos WHERE created_at >= ? GROUP BY 1",
         (day0.isoformat(),)),
        ("SELECT COALESCE(priority,'none') AS p, COUNT(*) AS n FROM todos WHERE completed_at IS NULL GROUP BY 1", ()),
    ])
    h = head[0]
    total, done = int(h["total"] or 0), int(h["done"] or 0)
    days = [(day0 + timedelta(days=i)).isoformat() for i in range(30)]
    dmap = {r["d"]: int(r["n"]) for r in done_rows}
    cmap = {r["d"]: int(r["n"]) for r in created_rows}
    return {
        "total": total, "completed": done, "pending": total - done, "overdue": int(h["overdue"] or 0),
        "due_today": int(h["due_today"] or 0), "due_week": int(h["due_week"] or 0),
        "completion_rate": round(100 * done / total) if total else 0,
        "days": [d[5:] for d in days], "completed_per_day": [dmap.get(d, 0) for d in days],
        "created_per_day": [cmap.get(d, 0) for d in days],
        "priority": {r["p"]: int(r["n"]) for r in prio},
    }


# ===========================================================================
# Journaling (personal diary)
# ===========================================================================
def _diary_values(data, partial=False):
    out = {}
    if "entry_date" in data or not partial:
        out["entry_date"] = clean_date(data.get("entry_date"), "entry_date") or local_today()
    if "title" in data:
        out["title"] = str(data.get("title") or "").strip()[:200]
    if "content" in data:
        c = str(data.get("content") or "")
        if len(c) > 300000:
            raise ValidationError({"content": "entry is too long"})
        out["content"] = c
    return out


def diary_get(eid):
    return db.one("SELECT * FROM diary_entries WHERE id=?", (int(eid),))


def diary_create(data):
    v = _diary_values(data)
    v.setdefault("title", "")
    v.setdefault("content", "")
    ts = now_iso()
    v.update(created_at=ts, updated_at=ts)
    cols = list(v)
    eid = db.insert(f"INSERT INTO diary_entries ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [v[c] for c in cols])
    _reindex("diary", eid)
    return diary_get(eid)


def diary_update(eid, data):
    if not diary_get(eid):
        return None
    v = _diary_values(data, partial=True)
    if v:
        v["updated_at"] = now_iso()
        db.execute(f"UPDATE diary_entries SET {', '.join(f'{c}=?' for c in v)} WHERE id=?", [*v.values(), int(eid)])
        _reindex("diary", eid)
    return diary_get(eid)


def diary_delete(eid):
    if not diary_get(eid):
        return False
    db.execute("DELETE FROM diary_entries WHERE id=?", (int(eid),))
    _reindex("diary", eid, delete=True)
    return True


def diary_list(q=None, month=None, on_date=None, limit=60, offset=0):
    sql, params = "SELECT id, entry_date, title, substr(content,1,400) AS preview, length(content) AS chars, " \
                  "created_at, updated_at FROM diary_entries WHERE 1=1", []
    if q:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        params += [f"%{q.strip()}%"] * 2
    if month:
        sql += " AND substr(entry_date,1,7)=?"
        params.append(month[:7])
    if on_date:
        sql += " AND entry_date=?"
        params.append(on_date)
    sql += " ORDER BY entry_date DESC, id DESC LIMIT ? OFFSET ?"
    params += [min(int(limit), 200), int(offset)]
    return db.query(sql, params)


def diary_calendar(month):
    """{date: count} for one month, for the browse-by-date calendar."""
    return {r["entry_date"]: int(r["n"]) for r in db.query(
        "SELECT entry_date, COUNT(*) AS n FROM diary_entries WHERE substr(entry_date,1,7)=? GROUP BY entry_date",
        (month[:7],))}


def diary_stats(today=None):
    rows, dates = db.many([
        ("SELECT COUNT(*) AS n, SUM(length(content) - length(replace(content, ' ', '')) + 1) AS words "
         "FROM diary_entries WHERE content != ''", ()),
        ("SELECT DISTINCT entry_date FROM diary_entries ORDER BY entry_date DESC LIMIT 400", ()),
    ])
    have = {r["entry_date"] for r in dates}
    streak, d = 0, date.fromisoformat(today or local_today())
    if d.isoformat() not in have:
        d -= timedelta(days=1)  # today not written yet doesn't break the streak
    while d.isoformat() in have:
        streak += 1
        d -= timedelta(days=1)
    month = (today or local_today())[:7]
    return {"entries": int(rows[0]["n"] or 0), "words": int(rows[0]["words"] or 0), "streak": streak,
            "this_month": sum(1 for x in have if x.startswith(month))}
