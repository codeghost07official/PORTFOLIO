"""Private assistant API: conversations, messages, confirmed actions."""
from flask import Blueprint, jsonify, request

from ..ai import assistant, gemini
from ..db import db
from ..markdown_render import render_markdown
from ..rag import indexer
from ..security import admin_required
from ..utils import ValidationError, jloads, now_iso, truncate

bp = Blueprint("ai_api", __name__, url_prefix="/api/admin/ai")


@bp.before_request
@admin_required
def _guard():
    return None


def _render(m):
    m = dict(m)
    m["sources"] = jloads(m.get("sources"), []) if isinstance(m.get("sources"), str) else m.get("sources") or []
    m["actions"] = jloads(m.get("actions"), []) if isinstance(m.get("actions"), str) else m.get("actions") or []
    m["html"] = str(render_markdown(m["content"])) if m["role"] == "assistant" else None
    return m


@bp.after_request
def _invalidate_after_write(response):
    if request.method == "POST" and "/actions/" in request.path and response.status_code < 400:
        from ..services import public_data

        public_data.invalidate()
    return response


@bp.get("/status")
def status():
    return jsonify(assistant.ai_status())


@bp.get("/models")
def models():
    return jsonify(gemini.list_models())


@bp.get("/conversations")
def conversations():
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT c.*, p.name AS project_name, (SELECT COUNT(*) FROM ai_messages m WHERE m.conversation_id=c.id) "
           "AS message_count FROM ai_conversations c LEFT JOIN projects p ON p.id=c.project_id")
    params = []
    if q:
        sql += (" WHERE c.title LIKE ? OR c.id IN (SELECT conversation_id FROM ai_messages WHERE content LIKE ?)")
        params = [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY c.updated_at DESC LIMIT 200"
    return jsonify(db.query(sql, params))


@bp.post("/conversations")
def create_conversation():
    data = request.get_json(silent=True) or {}
    pid = data.get("project_id") or None
    if pid and not db.scalar("SELECT id FROM projects WHERE id=?", (int(pid),)):
        raise ValidationError({"project_id": "not found"})
    ts = now_iso()
    cid = db.insert("INSERT INTO ai_conversations(title, project_id, created_at, updated_at) VALUES (?,?,?,?)",
                    (truncate(str(data.get("title") or "New conversation"), 120), int(pid) if pid else None, ts, ts))
    return jsonify(db.one("SELECT * FROM ai_conversations WHERE id=?", (cid,))), 201


@bp.route("/conversations/<int:cid>", methods=["PATCH"])
def update_conversation(cid):
    data = request.get_json(silent=True) or {}
    if "title" in data:
        title = truncate(str(data["title"]).strip(), 120)
        if not title:
            raise ValidationError({"title": "required"})
        db.execute("UPDATE ai_conversations SET title=? WHERE id=?", (title, cid))
    if "project_id" in data:
        pid = data["project_id"] or None
        if pid and not db.scalar("SELECT id FROM projects WHERE id=?", (int(pid),)):
            raise ValidationError({"project_id": "not found"})
        db.execute("UPDATE ai_conversations SET project_id=? WHERE id=?", (int(pid) if pid else None, cid))
    return jsonify(db.one("SELECT * FROM ai_conversations WHERE id=?", (cid,)))


@bp.delete("/conversations/<int:cid>")
def delete_conversation(cid):
    ids = [r["id"] for r in db.query("SELECT id FROM ai_messages WHERE conversation_id=? AND role='assistant'", (cid,))]
    db.batch([("DELETE FROM ai_messages WHERE conversation_id=?", (cid,)),
              ("UPDATE memory_records SET conversation_id=NULL WHERE conversation_id=?", (cid,)),
              ("DELETE FROM ai_conversations WHERE id=?", (cid,)),
              ("DELETE FROM doc_chunks WHERE source_type='conversation' AND parent_id=?", (cid,))])
    if ids:
        indexer.bump_version()
    return jsonify(ok=True)


@bp.get("/conversations/<int:cid>/messages")
def messages(cid):
    conv = db.one("SELECT c.*, p.name AS project_name FROM ai_conversations c LEFT JOIN projects p ON p.id=c.project_id "
                  "WHERE c.id=?", (cid,))
    if not conv:
        return jsonify(error="Not found"), 404
    rows = db.query("SELECT * FROM ai_messages WHERE conversation_id=? ORDER BY id", (cid,))
    return jsonify(conversation=conv, messages=[_render(m) for m in rows])


@bp.post("/conversations/<int:cid>/messages")
def send(cid):
    data = request.get_json(silent=True) or {}
    text = str(data.get("message", "")).strip()
    if not text:
        raise ValidationError({"message": "required"})
    if len(text) > 12000:
        raise ValidationError({"message": "max 12000 characters"})
    pid = data.get("project_id", "keep")
    project_id = None if pid in (None, "", 0) else (int(pid) if pid != "keep" else None)
    if pid == "keep":
        project_id = db.scalar("SELECT project_id FROM ai_conversations WHERE id=?", (cid,))
    if not db.scalar("SELECT id FROM ai_conversations WHERE id=?", (cid,)):
        return jsonify(error="Conversation not found"), 404
    if pid not in ("keep", None, "", 0):
        if not db.scalar("SELECT id FROM projects WHERE id=?", (project_id,)):
            raise ValidationError({"project_id": "not found"})
    if pid in (None, "", 0):
        db.execute("UPDATE ai_conversations SET project_id=NULL WHERE id=?", (cid,))
    reply = assistant.chat(cid, text, project_id, today=data.get("today"))
    return jsonify(message=_render(reply), conversation_title=reply.get("conversation_title"), model=reply.get("model"))


@bp.post("/messages/<int:mid>/actions/<int:idx>")
def resolve(mid, idx):
    decision = (request.get_json(silent=True) or {}).get("decision")
    if decision not in ("confirm", "dismiss"):
        raise ValidationError({"decision": "confirm or dismiss"})
    try:
        action, result = assistant.resolve_action(mid, idx, decision)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(action=action, result=result)
