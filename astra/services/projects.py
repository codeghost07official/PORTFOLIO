"""Projects: lifecycle, technologies, links, templates, idea conversion."""
from datetime import date, timedelta

from ..db import db
from ..utils import (
    ValidationError, clean_date, clean_tags, clean_url, jdumps, jloads, now_iso, slugify, to_bool, today_iso,
)
from . import constants as C
from .activity import log_event

TEXT_FIELDS = {
    "name": 160, "tagline": 240, "category": 80, "next_action": 400,
    "description": 100000, "objective": 20000, "problem": 50000, "motivation": 50000,
    "features": 100000, "architecture": 100000, "challenges": 100000, "future": 50000,
    "achievements": 50000, "documentation": 300000,
    "process": 100000, "solutions": 100000, "learnings": 50000,
}
URL_FIELDS = ["cover_image", "github_url", "live_url", "youtube_url"]
DATE_FIELDS = ["start_date", "target_date", "completed_date"]
BOOL_FIELDS = ["is_public", "is_featured", "show_journal", "exhibit_published"]

ADMIN_SORTS = {
    "updated": "p.updated_at DESC",
    "name": "p.name COLLATE NOCASE",
    "priority": "CASE p.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, p.updated_at DESC",
    "target": "CASE WHEN p.target_date IS NULL THEN 1 ELSE 0 END, p.target_date",
    "manual": "p.is_featured DESC, p.sort_order, p.updated_at DESC",
}


def _unique_slug(base, exclude_id=None):
    slug, n = base, 2
    while True:
        row = db.one("SELECT id FROM projects WHERE slug=?", (slug,))
        if not row or row["id"] == exclude_id:
            return slug
        slug = f"{base}-{n}"
        n += 1


def _validate(data, partial=False, exclude_id=None):
    out = {}
    for f, mx in TEXT_FIELDS.items():
        if f in data:
            val = "" if data[f] is None else str(data[f])
            val = val.strip() if mx <= 400 else val
            if len(val) > mx:
                raise ValidationError({f: f"max {mx} characters"})
            out[f] = val
    if not partial and not out.get("name"):
        raise ValidationError({"name": "required"})
    if partial and "name" in out and not out["name"]:
        raise ValidationError({"name": "required"})
    for f in URL_FIELDS:
        if f in data:
            out[f] = clean_url(data[f], f)
    for f in DATE_FIELDS:
        if f in data:
            out[f] = clean_date(data[f], f)
    for f in BOOL_FIELDS:
        if f in data:
            out[f] = 1 if to_bool(data[f]) else 0
    if "status" in data:
        if data["status"] not in C.PROJECT_STATUSES:
            raise ValidationError({"status": "invalid status"})
        out["status"] = data["status"]
    if "priority" in data:
        if data["priority"] not in C.PRIORITIES:
            raise ValidationError({"priority": "invalid priority"})
        out["priority"] = data["priority"]
    if "progress" in data:
        try:
            out["progress"] = max(0, min(100, int(data["progress"] or 0)))
        except (TypeError, ValueError):
            raise ValidationError({"progress": "must be 0-100"})
    if "sort_order" in data:
        try:
            out["sort_order"] = int(data["sort_order"] or 0)
        except (TypeError, ValueError):
            out["sort_order"] = 0
    if "tags" in data:
        out["tags"] = jdumps(clean_tags(data["tags"]))
    if "gallery" in data:
        gal = data["gallery"]
        if isinstance(gal, str):
            gal = [g for g in gal.replace(",", "\n").splitlines()]
        out["gallery"] = jdumps([clean_url(g.strip(), "gallery") for g in gal if g and g.strip()][:30])
    if "slug" in data or not partial:
        raw = data.get("slug") or out.get("name") or data.get("name") or ""
        out["slug"] = _unique_slug(slugify(raw), exclude_id)
    return out


def _clean_links(links):
    out = []
    for link in links or []:
        label = str(link.get("label", "")).strip()[:80]
        url = clean_url(link.get("url", ""), "links")
        if url:
            out.append({"label": label or url, "url": url})
    return out[:20]


def _save_children(pid, data):
    stmts = []
    if "technologies" in data:
        techs = clean_tags(data["technologies"])
        stmts.append(("DELETE FROM project_technologies WHERE project_id=?", (pid,)))
        stmts += [
            ("INSERT INTO project_technologies(project_id, name, sort_order) VALUES (?,?,?)", (pid, t, i))
            for i, t in enumerate(techs)
        ]
    if "links" in data:
        links = _clean_links(data["links"])
        stmts.append(("DELETE FROM project_links WHERE project_id=?", (pid,)))
        stmts += [
            ("INSERT INTO project_links(project_id, label, url, sort_order) VALUES (?,?,?,?)",
             (pid, l["label"], l["url"], i))
            for i, l in enumerate(links)
        ]
    if stmts:
        db.batch(stmts)


def _decorate(rows, with_children=True):
    if not rows:
        return rows
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    techs, links, stats = {}, {}, {}
    trows, lrows, srows, jrows, xrows = db.many([
        (f"SELECT project_id, name FROM project_technologies WHERE project_id IN ({marks}) ORDER BY sort_order", ids),
        (f"SELECT project_id, label, url FROM project_links WHERE project_id IN ({marks}) ORDER BY sort_order", ids),
        (f"SELECT project_id, COUNT(*) AS total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done "
         f"FROM tasks WHERE project_id IN ({marks}) GROUP BY project_id", ids),
        (f"SELECT project_id, COUNT(*) AS n, MAX(entry_date) AS last FROM journals WHERE project_id IN ({marks}) "
         f"GROUP BY project_id", ids),
        (f"SELECT project_id, generated_at, published_at, updated_at FROM project_exhibits WHERE project_id IN ({marks})", ids),
    ])
    jmap = {r["project_id"]: r for r in jrows}
    xmap = {r["project_id"]: r for r in xrows}
    if with_children:
        for t in trows:
            techs.setdefault(t["project_id"], []).append(t["name"])
        for l in lrows:
            links.setdefault(l["project_id"], []).append({"label": l["label"], "url": l["url"]})
    for st in srows:
        stats[st["project_id"]] = st
    for r in rows:
        j, x = jmap.get(r["id"]), xmap.get(r["id"])
        r["journal_count"], r["journal_last"] = (int(j["n"]), j["last"]) if j else (0, None)
        r["exhibit"] = {"has_draft": bool(x), "generated_at": x["generated_at"] if x else None,
                        "published_at": x["published_at"] if x else None, "draft_updated": x["updated_at"] if x else None}
        r["tags"] = jloads(r.get("tags"), [])
        r["gallery"] = jloads(r.get("gallery"), [])
        r["technologies"] = techs.get(r["id"], [])
        r["links"] = links.get(r["id"], [])
        s = stats.get(r["id"]) or {"total": 0, "done": 0}
        r["task_total"], r["task_done"] = int(s["total"] or 0), int(s["done"] or 0)
        r["computed_progress"] = (
            round(100 * r["task_done"] / r["task_total"]) if r["task_total"] else int(r.get("progress") or 0)
        )
        if r.get("status") == "completed":
            r["computed_progress"] = 100
    return rows


def list_projects(q=None, status=None, category=None, visibility=None, featured=None, sort="updated",
                  include_archived=True, limit=500):
    sql, params = "SELECT p.* FROM projects p WHERE 1=1", []
    if status:
        vals = [v for v in status.split(",") if v in C.PROJECT_STATUSES]
        if vals:
            sql += f" AND p.status IN ({','.join('?' * len(vals))})"
            params += vals
    elif not include_archived:
        sql += " AND p.status != 'archived'"
    if category:
        sql += " AND p.category=?"
        params.append(category)
    if visibility == "public":
        sql += " AND p.is_public=1"
    elif visibility == "private":
        sql += " AND p.is_public=0"
    if featured:
        sql += " AND p.is_featured=1"
    if q:
        like = f"%{q.strip()}%"
        sql += (" AND (p.name LIKE ? OR p.tagline LIKE ? OR p.description LIKE ? OR p.tags LIKE ? OR p.category LIKE ?"
                " OR p.id IN (SELECT project_id FROM project_technologies WHERE name LIKE ?))")
        params += [like] * 6
    sql += f" ORDER BY {ADMIN_SORTS.get(sort, ADMIN_SORTS['updated'])} LIMIT ?"
    params.append(int(limit))
    return _decorate(db.query(sql, params))


def get_project(pid):
    rows = _decorate(db.query("SELECT * FROM projects WHERE id=?", (int(pid),)))
    return rows[0] if rows else None


def get_by_slug(slug):
    rows = _decorate(db.query("SELECT * FROM projects WHERE slug=?", (slug,)))
    return rows[0] if rows else None


def create_project(data, source="manual"):
    values = _validate(data)
    ts = now_iso()
    values.setdefault("status", "in_progress")
    values.setdefault("priority", "medium")
    values["created_at"] = values["updated_at"] = ts
    if values["status"] == "completed" and not values.get("completed_date"):
        values["completed_date"] = today_iso()
    cols = list(values)
    pid = db.insert(
        f"INSERT INTO projects ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [values[c] for c in cols],
    )
    _save_children(pid, data)
    prefix = "AI: " if source == "ai" else ""
    log_event("project_created", f"{prefix}Project created: {values['name']}", pid, "projects", pid)
    _reindex(pid)
    return get_project(pid)


def update_project(pid, data):
    before = get_project(pid)
    if not before:
        return None
    values = _validate(data, partial=True, exclude_id=int(pid))
    if "slug" in values and "slug" not in data:
        values.pop("slug")  # only re-slug on explicit request
    if values.get("status") == "completed" and before["status"] != "completed" and not values.get("completed_date") \
            and not before.get("completed_date"):
        values["completed_date"] = today_iso()
    if values.get("status") == "archived" and before["status"] != "archived":
        values["archived_from"] = before["status"]
    if values:
        values["updated_at"] = now_iso()
        sets = ", ".join(f"{c}=?" for c in values)
        db.execute(f"UPDATE projects SET {sets} WHERE id=?", [*values.values(), int(pid)])
    _save_children(int(pid), data)
    after = get_project(pid)
    if before["status"] != after["status"]:
        log_event(
            "project_status", f"{after['name']}: {C.label(before['status'])} → {C.label(after['status'])}",
            after["id"], "projects", after["id"],
        )
    elif values or "technologies" in data or "links" in data:
        if any(k in values for k in ("description", "features", "architecture", "documentation", "next_action")):
            log_event("project_updated", f"Project updated: {after['name']}", after["id"], "projects", after["id"])
    _reindex(pid)
    return after


def archive_project(pid):
    return update_project(pid, {"status": "archived"})


def restore_project(pid):
    p = get_project(pid)
    if not p:
        return None
    target = p.get("archived_from") or "paused"
    if target == "archived":
        target = "paused"
    return update_project(pid, {"status": target})


def delete_project(pid):
    p = get_project(pid)
    if not p:
        return False
    pid = int(pid)
    # explicit cleanup (works even where FK cascades are not enforced)
    db.batch([
        ("DELETE FROM project_exhibits WHERE project_id=?", (pid,)),
        ("DELETE FROM project_technologies WHERE project_id=?", (pid,)),
        ("DELETE FROM project_links WHERE project_id=?", (pid,)),
        ("DELETE FROM tasks WHERE project_id=?", (pid,)),
        ("DELETE FROM milestones WHERE project_id=?", (pid,)),
        ("DELETE FROM journals WHERE project_id=?", (pid,)),
        ("DELETE FROM notes WHERE project_id=?", (pid,)),
        ("DELETE FROM resources WHERE project_id=?", (pid,)),
        ("DELETE FROM bugs WHERE project_id=?", (pid,)),
        ("DELETE FROM memory_records WHERE project_id=?", (pid,)),
        ("UPDATE ideas SET project_id=NULL WHERE project_id=?", (pid,)),
        ("UPDATE activity SET project_id=NULL WHERE project_id=?", (pid,)),
        ("UPDATE focus_sessions SET project_id=NULL, task_id=NULL WHERE project_id=?", (pid,)),
        ("UPDATE ai_conversations SET project_id=NULL WHERE project_id=?", (pid,)),
        ("DELETE FROM doc_chunks WHERE project_id=?", (pid,)),
        ("DELETE FROM projects WHERE id=?", (pid,)),
    ])
    log_event("project_deleted", f"Project deleted: {p['name']}")
    from ..rag import indexer

    indexer.bump_version()
    return True


def categories():
    return [r["category"] for r in db.query(
        "SELECT DISTINCT category FROM projects WHERE category != '' ORDER BY category COLLATE NOCASE")]


def _reindex(pid):
    from ..rag import indexer

    indexer.schedule("project", int(pid))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def list_templates():
    rows = db.query("SELECT * FROM project_templates ORDER BY builtin DESC, name")
    for r in rows:
        r["technologies"] = jloads(r["technologies"], [])
        r["tasks"] = jloads(r["tasks"], [])
        r["milestones"] = jloads(r["milestones"], [])
    return rows


def save_template(data, tid=None):
    name = str(data.get("name", "")).strip()[:120]
    if not name:
        raise ValidationError({"name": "required"})
    tasks = [str(t).strip()[:200] for t in (data.get("tasks") or []) if str(t).strip()][:100]
    miles = []
    for m in data.get("milestones") or []:
        title = str(m.get("title", "")).strip()[:200] if isinstance(m, dict) else str(m).strip()[:200]
        if title:
            try:
                offset = int(m.get("offset_days", 14)) if isinstance(m, dict) else 14
            except (TypeError, ValueError):
                offset = 14
            miles.append({"title": title, "offset_days": max(0, min(3650, offset))})
    values = (
        name, str(data.get("description", ""))[:2000], str(data.get("category", ""))[:80],
        jdumps(clean_tags(data.get("technologies"))), jdumps(tasks), jdumps(miles[:50]), now_iso(),
    )
    if tid:
        db.execute(
            "UPDATE project_templates SET name=?, description=?, category=?, technologies=?, tasks=?, milestones=?, "
            "updated_at=? WHERE id=?", (*values, int(tid)))
        return int(tid)
    key = slugify(name) + "-" + now_iso()[-9:-1].replace(":", "")
    return db.insert(
        "INSERT INTO project_templates(key, name, description, category, technologies, tasks, milestones, builtin,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)",
        (key, *values[:-1], values[-1], values[-1]),
    )


def delete_template(tid):
    db.execute("DELETE FROM project_templates WHERE id=?", (int(tid),))


def create_from_template(template_id, data):
    tpl = next((t for t in list_templates() if t["id"] == int(template_id)), None)
    if not tpl:
        raise ValidationError({"template": "template not found"})
    payload = dict(data)
    payload.setdefault("category", tpl["category"])
    if not payload.get("technologies"):
        payload["technologies"] = tpl["technologies"]
    payload.setdefault("start_date", today_iso())
    project = create_project(payload)
    ts = now_iso()
    start = date.fromisoformat(project.get("start_date") or today_iso())
    stmts = [
        ("INSERT INTO tasks(project_id, title, status, priority, sort_order, created_at, updated_at) "
         "VALUES (?,?,?,?,?,?,?)", (project["id"], t, "backlog" if i > 4 else "todo", "medium", i, ts, ts))
        for i, t in enumerate(tpl["tasks"])
    ]
    stmts += [
        ("INSERT INTO milestones(project_id, title, target_date, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
         (project["id"], m["title"], (start + timedelta(days=m["offset_days"])).isoformat(), "planned", ts, ts))
        for m in tpl["milestones"]
    ]
    db.batch(stmts)
    log_event("project_template", f"Created from template “{tpl['name']}”: {project['name']}", project["id"])
    from ..rag import indexer

    indexer.schedule_project_children(project["id"])
    return get_project(project["id"])


# ---------------------------------------------------------------------------
# Ideas -> projects
# ---------------------------------------------------------------------------
def convert_idea(idea_id, overrides=None):
    idea = db.one("SELECT * FROM ideas WHERE id=?", (int(idea_id),))
    if not idea:
        return None
    if idea["project_id"]:
        existing = get_project(idea["project_id"])
        if existing:
            return existing
    overrides = overrides or {}
    desc = idea["description"] or ""
    payload = {
        "name": overrides.get("name") or idea["name"],
        "description": desc + f"\n\n---\n*Converted from Idea Vault entry “{idea['name']}” "
                              f"(captured {idea['created_at'][:10]}).*",
        "objective": desc.split("\n")[0][:500] if desc else "",
        "category": idea["category"] or "",
        "tags": jloads(idea["tags"], []),
        "priority": idea["priority"],
        "status": overrides.get("status") or "in_progress",
    }
    project = create_project(payload)
    db.execute("UPDATE ideas SET status='converted', project_id=?, updated_at=? WHERE id=?",
               (project["id"], now_iso(), int(idea_id)))
    log_event("idea_converted", f"Idea promoted to project: {idea['name']}", project["id"], "ideas", idea["id"])
    from ..rag import indexer

    indexer.schedule("idea", int(idea_id))
    return project
