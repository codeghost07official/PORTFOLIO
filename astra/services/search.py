"""Global admin search across every workspace collection."""
from ..db import db
from ..markdown_render import markdown_excerpt

SOURCES = [
    ("project", "Projects", "SELECT id, name AS title, tagline AS body, id AS project_id FROM projects "
     "WHERE name LIKE ? OR tagline LIKE ? OR description LIKE ? OR documentation LIKE ? OR tags LIKE ?", 5),
    ("task", "Tasks", "SELECT id, title, description AS body, project_id FROM tasks "
     "WHERE title LIKE ? OR description LIKE ? OR notes LIKE ?", 3),
    ("journal", "Journal", "SELECT id, title, content AS body, project_id FROM journals "
     "WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?", 3),
    ("note", "Notes", "SELECT id, title, content AS body, project_id FROM notes WHERE title LIKE ? OR content LIKE ?", 2),
    ("idea", "Ideas", "SELECT id, name AS title, description AS body, project_id FROM ideas "
     "WHERE name LIKE ? OR description LIKE ? OR tags LIKE ?", 3),
    ("snippet", "Snippets", "SELECT id, title, description AS body, NULL AS project_id FROM snippets "
     "WHERE title LIKE ? OR code LIKE ? OR description LIKE ? OR tags LIKE ?", 4),
    ("resource", "Resources", "SELECT id, title, COALESCE(description,'') || ' ' || url AS body, project_id "
     "FROM resources WHERE title LIKE ? OR url LIKE ? OR description LIKE ?", 3),
    ("bug", "Bugs", "SELECT id, title, description AS body, project_id FROM bugs "
     "WHERE title LIKE ? OR description LIKE ? OR solution LIKE ?", 3),
    ("milestone", "Milestones", "SELECT id, title, description AS body, project_id FROM milestones "
     "WHERE title LIKE ? OR description LIKE ?", 2),
]


def link_for(kind, rid, project_id=None):
    """Canonical URL of every kind of item (used by search, the assistant's sources, the palette)."""
    if kind == "project":
        return f"/admin/projects/{rid}"
    if kind == "task":
        return f"/admin/tasks/{rid}"
    if kind == "journal":
        return f"/admin/journal/{rid}"
    if kind == "milestone":
        return f"/admin/projects/{project_id}/milestones#m-{rid}" if project_id else "/admin/roadmap"
    if kind == "conversation":
        return f"/admin/assistant/{rid}"
    plural = {"note": "notes", "idea": "ideas", "snippet": "snippets", "resource": "resources", "bug": "bugs"}
    return f"/admin/{plural[kind]}/{rid}" if kind in plural else "/admin/"


def search(q, limit_per=8):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    groups = []
    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM projects")}
    for kind, label, sql, n in SOURCES:
        rows = db.query(sql + f" ORDER BY id DESC LIMIT {int(limit_per)}", [like] * n)
        if rows:
            groups.append({"kind": kind, "label": label, "items": [{
                "id": r["id"], "title": r["title"] or "(untitled)",
                "excerpt": markdown_excerpt(r["body"] or "", 140),
                "project": names.get(r["project_id"]) if kind != "project" else None,
                "url": link_for(kind, r["id"], r["project_id"]),
            } for r in rows]})
    convs = db.query("SELECT DISTINCT c.id, c.title FROM ai_conversations c JOIN ai_messages m ON m.conversation_id=c.id "
                     "WHERE c.title LIKE ? OR m.content LIKE ? ORDER BY c.updated_at DESC LIMIT ?",
                     (like, like, limit_per))
    if convs:
        groups.append({"kind": "conversation", "label": "AI conversations", "items": [
            {"id": c["id"], "title": c["title"], "excerpt": "", "project": None, "url": link_for("conversation", c["id"])}
            for c in convs]})
    return groups
