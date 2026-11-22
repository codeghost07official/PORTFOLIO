"""Whitelisted actions the private assistant may *propose*. Nothing runs until Sir
confirms; execution goes through the same validated services the UI uses. No model-generated SQL."""
from ..db import db
from ..services import entities, finance, personal, projects
from ..services import constants as C
from ..utils import ValidationError, clean_tags, truncate

ACTIONS = {
    "create_task": {"label": "Add task", "fields": ["title", "description", "priority", "due_date"], "required": ["title"],
                    "doc": "title, description?, priority(low|medium|high)?, due_date(YYYY-MM-DD)?"},
    "complete_task": {"label": "Complete task", "fields": ["task_id"], "required": ["task_id"], "doc": "task_id"},
    "delete_task": {"label": "Delete task", "fields": ["task_id"], "required": ["task_id"], "destructive": True,
                    "doc": "task_id"},
    "create_journal_draft": {"label": "Project journal entry", "fields": ["project_id", "title", "content", "tags"],
                             "required": ["project_id", "title", "content"],
                             "doc": "project_id, title, content(Markdown), tags[]? — writes to that project's journal"},
    "set_project_status": {"label": "Project status", "fields": ["project_id", "status"], "required": ["project_id", "status"],
                           "doc": "project_id, status(in_progress|completed)"},
    "log_transaction": {"label": "Log transaction", "fields": ["kind", "amount", "category", "description", "occurred_at"],
                        "required": ["kind", "amount"],
                        "doc": "kind(income|expense), amount, category?, description?, occurred_at(YYYY-MM-DDTHH:MM)?"},
    "save_memory": {"label": "Remember", "fields": ["content", "kind"], "required": ["content"],
                    "doc": "content (a durable fact or preference Sir wants remembered), kind(fact|preference|decision|context)?"},
}


def prompt_reference():
    return "\n".join(f"- {n}: {s['doc']}" + (" (DESTRUCTIVE)" if s.get("destructive") else "") for n, s in ACTIONS.items())


def _int(v):
    if isinstance(v, str) and v[:1] in "PT" and v[1:].isdigit():
        v = v[1:]
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def normalise(raw, default_project_id=None):
    if not isinstance(raw, dict):
        return None
    name = raw.get("type") or raw.get("action")
    spec = ACTIONS.get(name)
    if not spec:
        return None
    params = raw.get("params") if isinstance(raw.get("params"), dict) else raw
    clean = {}
    for f in spec["fields"]:
        v = params.get(f)
        if v in (None, ""):
            continue
        if f.endswith("_id"):
            v = _int(v)
            if v is None:
                continue
        elif f == "tags":
            v = clean_tags(v)
        else:
            v = str(v)[:20000]
        clean[f] = v
    if "project_id" in spec["fields"] and "project_id" not in clean and default_project_id:
        clean["project_id"] = default_project_id
    for f, table in (("task_id", "todos"), ("project_id", "projects")):
        if f in clean and not db.scalar(f"SELECT id FROM {table} WHERE id=?", (clean[f],)):
            return None
    if name == "set_project_status" and clean.get("status") not in C.PROJECT_STATUSES:
        return None
    if name == "log_transaction" and clean.get("kind") not in ("income", "expense"):
        return None
    if any(f not in clean for f in spec["required"]):
        return None
    return {"type": name, "label": spec["label"], "params": clean, "destructive": bool(spec.get("destructive")),
            "summary": describe(name, clean), "status": "pending"}


def describe(name, p):
    if name == "create_task":
        return f"New task “{truncate(p['title'], 80)}”" + (f", due {p['due_date']}" if p.get("due_date") else "")
    if name in ("complete_task", "delete_task"):
        t = db.scalar("SELECT title FROM todos WHERE id=?", (p["task_id"],), default=f"#{p['task_id']}")
        return ("Mark done: " if name == "complete_task" else "Permanently delete task ") + f"“{truncate(t, 70)}”"
    pname = db.scalar("SELECT name FROM projects WHERE id=?", (p.get("project_id"),), default="") if p.get("project_id") else ""
    if name == "create_journal_draft":
        return f"Journal entry “{truncate(p['title'], 70)}” in {pname}"
    if name == "set_project_status":
        return f"{pname} → {C.label(p['status'])}"
    if name == "log_transaction":
        return f"{p['kind'].capitalize()} {p['amount']}" + (f" · {p['category']}" if p.get("category") else "") \
               + (f" · {truncate(p['description'], 40)}" if p.get("description") else "")
    if name == "save_memory":
        return f"Remember: “{truncate(p['content'], 100)}”"
    return name


def execute(action, conversation_id=None):
    name, p = action["type"], dict(action["params"])
    if name == "create_task":
        if p.get("priority") not in personal.TODO_PRIORITIES:
            p.pop("priority", None)
        t = personal.todo_create(p)
        return {"message": f"Task added: {t['title']}", "link": "/admin/tasks/all"}
    if name == "complete_task":
        t = personal.todo_update(p["task_id"], {"completed": True})
        return {"message": f"Completed: {t['title']}", "link": "/admin/tasks/completed"}
    if name == "delete_task":
        personal.todo_delete(p["task_id"])
        return {"message": "Task deleted", "link": None}
    if name == "create_journal_draft":
        j = entities.create_item("journals", {**p, "status": "draft", "visibility": "private"}, source="ai")
        return {"message": f"Journal entry added: {j['title']}", "link": f"/admin/projects/{p['project_id']}/journal"}
    if name == "set_project_status":
        pr = projects.update_project(p["project_id"], {"status": p["status"]})
        return {"message": f"{pr['name']} is now {C.label(pr['status'])}", "link": f"/admin/projects/{pr['id']}"}
    if name == "log_transaction":
        from datetime import datetime

        p.setdefault("occurred_at", datetime.now().strftime("%Y-%m-%dT%H:%M"))
        t = finance.create(p)
        return {"message": f"Logged {t['kind']} of {t['amount']:,.2f}", "link": "/admin/expenses/transactions"}
    if name == "save_memory":
        if p.get("kind") not in C.MEMORY_KINDS:
            p["kind"] = "fact"
        item = entities.create_item("memories", p, source="ai")
        if conversation_id:
            db.execute("UPDATE memory_records SET conversation_id=? WHERE id=?", (conversation_id, item["id"]))
        return {"message": "Memory saved", "link": "/admin/assistant/memory"}
    raise ValidationError({"action": "unsupported"})

