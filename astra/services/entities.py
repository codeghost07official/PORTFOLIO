"""Generic, whitelist-driven CRUD for workspace entities.

Every entity declares its columns and validation rules here. Only declared
columns can ever be written, values are validated/coerced, and all SQL is
parameterised. Both the REST API and the AI action executor go through these
functions, so there is exactly one validated write path.
"""
from ..db import db
from ..utils import (
    ValidationError, clean_date, clean_tags, clean_url, jdumps, jloads, now_iso, to_bool, today_iso,
)
from . import constants as C
from .activity import log_event

# field spec: (type, options)
#   str: max length | text: max length | enum: values | int: (min, max)
#   date | bool | url | tags | project (nullable fk)
ENTITIES = {
    "tasks": {
        "table": "tasks", "label": "Task", "title_field": "title",
        "fields": {
            "title": ("str", 200), "description": ("text", 20000), "status": ("enum", C.TASK_STATUSES),
            "priority": ("enum", C.PRIORITIES), "due_date": ("date", None), "notes": ("text", 20000),
            "project_id": ("project", None), "sort_order": ("int", (0, 10 ** 9)),
        },
        "required": ["title"], "defaults": {"status": "todo", "priority": "medium"},
        "search": ["title", "description", "notes"],
        "filters": ["status", "priority"],
        "sorts": {"due": "CASE WHEN x.due_date IS NULL THEN 1 ELSE 0 END, x.due_date", "priority":
                  "CASE x.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END",
                  "created": "x.created_at DESC", "updated": "x.updated_at DESC", "manual": "x.sort_order, x.id"},
        "default_sort": "manual",
    },
    "milestones": {
        "table": "milestones", "label": "Milestone", "title_field": "title",
        "fields": {
            "title": ("str", 200), "description": ("text", 20000), "target_date": ("date", None),
            "status": ("enum", C.MILESTONE_STATUSES), "project_id": ("project", None),
        },
        "required": ["title", "project_id"], "defaults": {"status": "planned"},
        "search": ["title", "description"], "filters": ["status"],
        "sorts": {"date": "CASE WHEN x.target_date IS NULL THEN 1 ELSE 0 END, x.target_date, x.id"},
        "default_sort": "date",
    },
    "journals": {
        "table": "journals", "label": "Journal entry", "title_field": "title",
        "fields": {
            "title": ("str", 200), "content": ("text", 300000), "tags": ("tags", None),
            "entry_date": ("date", None), "status": ("enum", C.JOURNAL_STATUSES),
            "visibility": ("enum", C.VISIBILITIES), "project_id": ("project", None),
        },
        "required": ["title"],
        "defaults": {"status": "draft", "visibility": "private"},
        "search": ["title", "content", "tags"], "filters": ["status", "visibility"],
        "sorts": {"date": "x.entry_date DESC, x.id DESC", "updated": "x.updated_at DESC"},
        "default_sort": "date",
    },
    "notes": {
        "table": "notes", "label": "Note", "title_field": "title",
        "fields": {
            "title": ("str", 200), "content": ("text", 50000), "category": ("enum", C.NOTE_CATEGORIES),
            "pinned": ("bool", None), "project_id": ("project", None),
        },
        "required": [], "defaults": {"category": "general", "pinned": 0},
        "search": ["title", "content"], "filters": ["category"],
        "sorts": {"pinned": "x.pinned DESC, x.updated_at DESC", "created": "x.created_at DESC"},
        "default_sort": "pinned",
    },
    "resources": {
        "table": "resources", "label": "Resource", "title_field": "title",
        "fields": {
            "title": ("str", 200), "url": ("url", None), "category": ("enum", C.RESOURCE_CATEGORIES),
            "description": ("text", 10000), "project_id": ("project", None),
        },
        "required": ["title"], "defaults": {"category": "reference"},
        "search": ["title", "url", "description"], "filters": ["category"],
        "sorts": {"created": "x.created_at DESC", "title": "x.title COLLATE NOCASE"},
        "default_sort": "created",
    },
    "bugs": {
        "table": "bugs", "label": "Bug", "title_field": "title",
        "fields": {
            "title": ("str", 200), "description": ("text", 50000), "severity": ("enum", C.BUG_SEVERITIES),
            "status": ("enum", C.BUG_STATUSES), "solution": ("text", 50000),
            "reported_at": ("date", None), "project_id": ("project", None),
        },
        "required": ["title"], "defaults": {"severity": "medium", "status": "open"},
        "search": ["title", "description", "solution"], "filters": ["status", "severity"],
        "sorts": {"reported": "x.reported_at DESC, x.id DESC", "severity":
                  "CASE x.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"},
        "default_sort": "reported",
    },
    "ideas": {
        "table": "ideas", "label": "Idea", "title_field": "name",
        "fields": {
            "name": ("str", 200), "description": ("text", 50000), "category": ("str", 80),
            "tags": ("tags", None), "priority": ("enum", C.PRIORITIES), "status": ("enum", C.IDEA_STATUSES),
            "project_id": ("project", None),
        },
        "required": ["name"], "defaults": {"priority": "medium", "status": "new"},
        "search": ["name", "description", "category", "tags"], "filters": ["status", "priority"],
        "sorts": {"created": "x.created_at DESC", "priority":
                  "CASE x.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"},
        "default_sort": "created",
    },
    "snippets": {
        "table": "snippets", "label": "Snippet", "title_field": "title",
        "fields": {
            "title": ("str", 200), "language": ("str", 40), "code": ("text", 100000),
            "description": ("text", 10000), "tags": ("tags", None),
        },
        "required": ["title", "code"], "defaults": {"language": "plaintext"},
        "search": ["title", "code", "description", "tags", "language"], "filters": ["language"],
        "sorts": {"updated": "x.updated_at DESC", "title": "x.title COLLATE NOCASE"},
        "default_sort": "updated", "no_project": True,
    },
    "memories": {
        "table": "memory_records", "label": "Memory", "title_field": "content",
        "fields": {"kind": ("enum", C.MEMORY_KINDS), "content": ("text", 2000), "project_id": ("project", None)},
        "required": ["content"], "defaults": {"kind": "fact"},
        "search": ["content"], "filters": ["kind"],
        "sorts": {"created": "x.created_at DESC"}, "default_sort": "created", "timestamps": "created",
    },
}

INDEXED = {"tasks": "task", "milestones": "milestone", "journals": "journal", "notes": "note",
           "resources": "resource", "bugs": "bug", "ideas": "idea", "snippets": "snippet"}


def spec_for(entity):
    spec = ENTITIES.get(entity)
    if not spec:
        raise KeyError(entity)
    return spec


def _clean_value(name, kind, opt, value):
    if kind == "str":
        value = "" if value is None else str(value).strip()
        if len(value) > opt:
            raise ValidationError({name: f"max {opt} characters"})
        return value
    if kind == "text":
        value = "" if value is None else str(value)
        if len(value) > opt:
            raise ValidationError({name: f"max {opt} characters"})
        return value
    if kind == "enum":
        if value not in opt:
            raise ValidationError({name: f"must be one of {', '.join(opt)}"})
        return value
    if kind == "int":
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError({name: "must be a number"})
        lo, hi = opt
        return max(lo, min(hi, value))
    if kind == "date":
        return clean_date(value, name)
    if kind == "bool":
        return 1 if to_bool(value) else 0
    if kind == "url":
        return clean_url(value, name)
    if kind == "tags":
        return jdumps(clean_tags(value))
    if kind == "project":
        if value in (None, "", 0, "0"):
            return None
        try:
            pid = int(value)
        except (TypeError, ValueError):
            raise ValidationError({name: "invalid project"})
        if not db.scalar("SELECT id FROM projects WHERE id=?", (pid,)):
            raise ValidationError({name: "project not found"})
        return pid
    raise ValidationError({name: "unsupported field"})


def validate(spec, data, partial=False):
    out = {}
    for name, (kind, opt) in spec["fields"].items():
        if name not in data:
            continue
        out[name] = _clean_value(name, kind, opt, data[name])
    if not partial:
        for k, v in spec.get("defaults", {}).items():
            out.setdefault(k, v)
        missing = [f for f in spec.get("required", []) if out.get(f) in (None, "")]
        if missing:
            raise ValidationError({f: "required" for f in missing})
    else:
        empty = [f for f in spec.get("required", []) if f in out and out[f] in (None, "")]
        if empty:
            raise ValidationError({f: "required" for f in empty})
    return out


def decode(row, entity):
    if not row:
        return row
    for name, (kind, _) in spec_for(entity)["fields"].items():
        if kind == "tags" and name in row:
            row[name] = jloads(row[name], [])
    return row


def _select(spec):
    if spec.get("no_project"):
        return f"SELECT x.* FROM {spec['table']} x"
    return (
        f"SELECT x.*, p.name AS project_name, p.slug AS project_slug FROM {spec['table']} x "
        "LEFT JOIN projects p ON p.id = x.project_id"
    )


def list_items(entity, project_id=None, q=None, sort=None, limit=200, offset=0, unassigned=False, **filters):
    spec = spec_for(entity)
    sql, params = _select(spec) + " WHERE 1=1", []
    if project_id and not spec.get("no_project"):
        sql += " AND x.project_id=?"
        params.append(int(project_id))
    if unassigned and not spec.get("no_project"):
        sql += " AND x.project_id IS NULL"
    for key in spec.get("filters", []):
        val = filters.get(key)
        if val:
            vals = [v for v in str(val).split(",") if v]
            sql += f" AND x.{key} IN ({','.join('?' * len(vals))})"
            params.extend(vals)
    if q:
        like = f"%{q.strip()}%"
        sql += " AND (" + " OR ".join(f"x.{c} LIKE ?" for c in spec["search"]) + ")"
        params.extend([like] * len(spec["search"]))
    order = spec["sorts"].get(sort) or spec["sorts"][spec["default_sort"]]
    sql += f" ORDER BY {order} LIMIT ? OFFSET ?"
    params.extend([min(int(limit), 1000), int(offset)])
    return [decode(r, entity) for r in db.query(sql, params)]


def get_item(entity, item_id):
    spec = spec_for(entity)
    return decode(db.one(_select(spec) + " WHERE x.id=?", (int(item_id),)), entity)


def _reindex(entity, item_id, delete=False):
    kind = INDEXED.get(entity)
    if not kind:
        return
    from ..rag import indexer

    if delete:
        indexer.remove(kind, item_id)
    else:
        indexer.schedule(kind, item_id)


def create_item(entity, data, source="manual"):
    spec = spec_for(entity)
    values = validate(spec, data)
    ts = now_iso()
    if spec.get("timestamps") == "created":
        values["created_at"] = ts
    else:
        values["created_at"] = values["updated_at"] = ts
    if entity == "journals":
        values.setdefault("entry_date", today_iso())
        if not values.get("entry_date"):
            values["entry_date"] = today_iso()
    if entity == "bugs" and not values.get("reported_at"):
        values["reported_at"] = today_iso()
    if entity == "tasks" and values.get("status") == "done":
        values["completed_at"] = ts
    if entity == "milestones" and values.get("status") == "done":
        values["completed_at"] = ts
    if entity == "bugs" and values.get("status") in ("fixed", "closed"):
        values["resolved_at"] = ts
    cols = list(values)
    new_id = db.insert(
        f"INSERT INTO {spec['table']} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [values[c] for c in cols],
    )
    item = get_item(entity, new_id)
    _after_create(entity, item, source)
    _reindex(entity, new_id)
    return item


def update_item(entity, item_id, data):
    spec = spec_for(entity)
    before = get_item(entity, item_id)
    if not before:
        return None
    values = validate(spec, data, partial=True)
    if not values:
        return before
    ts = now_iso()
    if spec.get("timestamps") != "created":
        values["updated_at"] = ts
    if entity == "tasks" and "status" in values and values["status"] != before["status"]:
        values["completed_at"] = ts if values["status"] == "done" else None
    if entity == "milestones" and "status" in values and values["status"] != before["status"]:
        values["completed_at"] = ts if values["status"] == "done" else None
    if entity == "bugs" and "status" in values and values["status"] != before["status"]:
        values["resolved_at"] = ts if values["status"] in ("fixed", "closed") else None
    sets = ", ".join(f"{c}=?" for c in values)
    db.execute(f"UPDATE {spec['table']} SET {sets} WHERE id=?", [*values.values(), int(item_id)])
    item = get_item(entity, item_id)
    _after_update(entity, before, item)
    _reindex(entity, item_id)
    return item


def delete_item(entity, item_id):
    spec = spec_for(entity)
    item = get_item(entity, item_id)
    if not item:
        return False
    db.execute(f"DELETE FROM {spec['table']} WHERE id=?", (int(item_id),))
    _reindex(entity, item_id, delete=True)
    return True


# ---------------------------------------------------------------------------
# Activity hooks
# ---------------------------------------------------------------------------
def _title(entity, item):
    return item.get(spec_for(entity)["title_field"]) or spec_for(entity)["label"]


def _after_create(entity, item, source):
    pid = item.get("project_id") if entity != "ideas" else None
    prefix = "Quick capture: " if source == "capture" else ("AI: " if source == "ai" else "")
    kinds = {
        "tasks": ("task_created", "Task added"),
        "milestones": ("milestone_created", "Milestone planned"),
        "journals": ("journal_written", "Journal entry written"),
        "bugs": ("bug_reported", "Bug reported"),
        "ideas": ("idea_captured", "Idea captured"),
        "resources": ("resource_added", "Resource saved"),
        "notes": ("note_added", "Note added"),
        "snippets": ("snippet_saved", "Snippet saved"),
    }
    if entity in kinds:
        kind, verb = kinds[entity]
        log_event(kind, f"{prefix}{verb}: {_title(entity, item)}", pid, entity, item["id"])


def _after_update(entity, before, item):
    pid = item.get("project_id") if entity != "ideas" else None
    title = _title(entity, item)
    if entity == "tasks" and before["status"] != item["status"]:
        if item["status"] == "done":
            log_event("task_completed", f"Task completed: {title}", pid, entity, item["id"])
        else:
            log_event("task_status", f"Task moved to {C.label(item['status'])}: {title}", pid, entity, item["id"])
    elif entity == "milestones" and before["status"] != item["status"] and item["status"] == "done":
        log_event("milestone_reached", f"Milestone reached: {title}", pid, entity, item["id"])
    elif entity == "bugs" and before["status"] != item["status"]:
        log_event("bug_status", f"Bug {item['status']}: {title}", pid, entity, item["id"])
    elif entity == "journals" and before["status"] != item["status"] and item["status"] == "published":
        log_event("journal_published", f"Journal published: {title}", pid, entity, item["id"])
