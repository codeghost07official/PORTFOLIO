"""Private REST API (JSON). Every route is protected server-side."""
import base64
import json
import secrets

from flask import Blueprint, Response, current_app, jsonify, request, session

from ..ai import public_bot
from ..db import db
from ..markdown_render import render_markdown
from ..rag import indexer
from ..security import admin_required
from ..services import constants as C
from ..services import activity, entities, export, focus, projects
from ..services import search as search_svc
from ..services import settings as settings_svc
from ..utils import ValidationError, now_iso

bp = Blueprint("api", __name__, url_prefix="/api/admin")


@bp.before_request
@admin_required
def _guard():
    return None


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError({"_": "JSON object body required"})
    return data


def _public_changed():
    public_bot.invalidate()
    from ..services import public_data

    public_data.invalidate()


@bp.after_request
def _invalidate_after_write(response):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 400:
        _public_changed()
    return response


# ---------------------------------------------------------------------------
# Meta / dashboard
# ---------------------------------------------------------------------------
@bp.post("/alive")
def alive():
    """Heartbeat from an open admin tab (see security.is_fresh_visit)."""
    from ..security import note_alive

    note_alive()
    return "", 204


@bp.get("/meta")
def meta():
    plist = db.query("SELECT id, name, status, slug FROM projects ORDER BY CASE WHEN status='archived' THEN 1 ELSE 0 END,"
                     " updated_at DESC")
    return jsonify(enums=C.ENUMS, projects=plist, categories=projects.categories(),
                   labels={v: C.label(v) for vals in C.ENUMS.values() for v in vals})


@bp.get("/activity")
def activity_list():
    return jsonify(activity.recent(min(int(request.args.get("limit", 100)), 500),
                                   project_id=request.args.get("project_id", type=int),
                                   kind=request.args.get("kind") or None))


@bp.get("/search")
def search():
    return jsonify(search_svc.search(request.args.get("q", "")))


@bp.post("/markdown")
def markdown_preview():
    return jsonify(html=str(render_markdown(str(body().get("text", ""))[:300000])))


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@bp.get("/projects")
def project_list():
    a = request.args
    return jsonify(projects.list_projects(q=a.get("q"), status=a.get("status"), category=a.get("category"),
                                          visibility=a.get("visibility"), featured=a.get("featured"),
                                          sort=a.get("sort", "updated")))


@bp.post("/projects")
def project_create():
    data = body()
    defaults = settings_svc.get("defaults")
    for k in ("status", "priority", "is_public", "show_journal"):
        data.setdefault(k, defaults.get(k))
    if data.get("template_id"):
        p = projects.create_from_template(data.pop("template_id"), data)
    else:
        p = projects.create_project(data)
    _public_changed()
    return jsonify(p), 201


@bp.get("/projects/<int:pid>")
def project_get(pid):
    p = projects.get_project(pid)
    return (jsonify(p), 200) if p else (jsonify(error="Not found"), 404)


@bp.route("/projects/<int:pid>", methods=["PUT", "PATCH"])
def project_update(pid):
    p = projects.update_project(pid, body())
    _public_changed()
    return (jsonify(p), 200) if p else (jsonify(error="Not found"), 404)


@bp.delete("/projects/<int:pid>")
def project_delete(pid):
    ok = projects.delete_project(pid)
    _public_changed()
    return (jsonify(ok=True), 200) if ok else (jsonify(error="Not found"), 404)


@bp.post("/projects/<int:pid>/archive")
def project_archive(pid):
    _public_changed()
    return jsonify(projects.archive_project(pid))


@bp.post("/projects/<int:pid>/restore")
def project_restore(pid):
    _public_changed()
    return jsonify(projects.restore_project(pid))


@bp.get("/projects/<int:pid>/summary")
def project_summary(pid):
    p = projects.get_project(pid)
    if not p:
        return jsonify(error="Not found"), 404
    counts = {
        "tasks": db.query("SELECT status, COUNT(*) AS n FROM tasks WHERE project_id=? GROUP BY status", (pid,)),
        "bugs_open": db.scalar("SELECT COUNT(*) FROM bugs WHERE project_id=? AND status IN ('open','investigating')",
                               (pid,), default=0),
        "journals": db.scalar("SELECT COUNT(*) FROM journals WHERE project_id=?", (pid,), default=0),
        "notes": db.scalar("SELECT COUNT(*) FROM notes WHERE project_id=?", (pid,), default=0),
        "resources": db.scalar("SELECT COUNT(*) FROM resources WHERE project_id=?", (pid,), default=0),
        "milestones": db.scalar("SELECT COUNT(*) FROM milestones WHERE project_id=?", (pid,), default=0),
    }
    minutes = next((t["minutes"] for t in focus.time_by_project() if t["project_id"] == pid), 0)
    return jsonify(project=p, counts=counts, minutes=minutes, activity=activity.recent(15, project_id=pid))


# ---------------------------------------------------------------------------
# Generic entities
# ---------------------------------------------------------------------------
def _check(entity):
    if entity not in entities.ENTITIES:
        return jsonify(error="Unknown collection"), 404
    return None


@bp.get("/e/<entity>")
def entity_list(entity):
    err = _check(entity)
    if err:
        return err
    a = request.args
    spec = entities.spec_for(entity)
    filters = {k: a.get(k) for k in spec.get("filters", [])}
    return jsonify(entities.list_items(entity, project_id=a.get("project_id", type=int), q=a.get("q"),
                                       sort=a.get("sort"), limit=a.get("limit", 300, type=int),
                                       offset=a.get("offset", 0, type=int), unassigned=a.get("unassigned") == "1",
                                       **filters))


@bp.post("/e/<entity>")
def entity_create(entity):
    err = _check(entity)
    if err:
        return err
    data = body()
    source = "capture" if data.pop("_source", None) == "capture" else "manual"
    item = entities.create_item(entity, data, source=source)
    if entity == "journals":
        _public_changed()
    return jsonify(item), 201


@bp.get("/e/<entity>/<int:item_id>")
def entity_get(entity, item_id):
    err = _check(entity)
    if err:
        return err
    item = entities.get_item(entity, item_id)
    return (jsonify(item), 200) if item else (jsonify(error="Not found"), 404)


@bp.route("/e/<entity>/<int:item_id>", methods=["PUT", "PATCH"])
def entity_update(entity, item_id):
    err = _check(entity)
    if err:
        return err
    item = entities.update_item(entity, item_id, body())
    if entity == "journals":
        _public_changed()
    return (jsonify(item), 200) if item else (jsonify(error="Not found"), 404)


@bp.delete("/e/<entity>/<int:item_id>")
def entity_delete(entity, item_id):
    err = _check(entity)
    if err:
        return err
    ok = entities.delete_item(entity, item_id)
    if entity == "journals":
        _public_changed()
    return (jsonify(ok=True), 200) if ok else (jsonify(error="Not found"), 404)


@bp.post("/tasks/reorder")
def tasks_reorder():
    """Body: {status: "todo", ids: [3, 8, 1]} - moves tasks into a column in that order."""
    data = body()
    status = data.get("status")
    if status not in C.TASK_STATUSES:
        raise ValidationError({"status": "invalid"})
    ids = [int(i) for i in data.get("ids", [])][:500]
    changed = [r["id"] for r in db.query(
        f"SELECT id FROM tasks WHERE status!=? AND id IN ({','.join('?' * len(ids))})", [status, *ids])] if ids else []
    for tid in changed:
        entities.update_item("tasks", tid, {"status": status})
    db.batch([("UPDATE tasks SET sort_order=? WHERE id=?", (i, tid)) for i, tid in enumerate(ids)])
    return jsonify(ok=True, moved=changed)


@bp.post("/ideas/<int:iid>/convert")
def idea_convert(iid):
    p = projects.convert_idea(iid, request.get_json(silent=True) or {})
    return (jsonify(p), 201) if p else (jsonify(error="Not found"), 404)


# ---------------------------------------------------------------------------
# Focus
# ---------------------------------------------------------------------------
@bp.get("/focus")
def focus_get():
    return jsonify(current=focus.current())


@bp.post("/focus")
def focus_set():
    d = body()
    return jsonify(current=focus.set_focus(d.get("project_id"), d.get("task_id"), d.get("note", "")))


@bp.delete("/focus")
def focus_clear():
    focus.clear_focus()
    return jsonify(current=None)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
@bp.get("/templates")
def templates_list():
    return jsonify(projects.list_templates())


@bp.post("/templates")
def template_create():
    return jsonify(id=projects.save_template(body())), 201


@bp.put("/templates/<int:tid>")
def template_update(tid):
    return jsonify(id=projects.save_template(body(), tid))


@bp.delete("/templates/<int:tid>")
def template_delete(tid):
    projects.delete_template(tid)
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@bp.get("/settings")
def settings_get():
    from ..ai.assistant import ai_status

    cfg = current_app.config
    return jsonify(
        settings=settings_svc.all_settings(fresh=True),
        system={
            "database": db.driver_name, "turso": bool(cfg["TURSO_DATABASE_URL"]), "ai": ai_status(),
            "login_path": cfg["ADMIN_LOGIN_PATH"], "session_hours": cfg["PERMANENT_SESSION_LIFETIME"].total_seconds() / 3600,
            "idle_minutes": cfg["SESSION_IDLE_MINUTES"], "warnings": cfg.get("CONFIG_WARNINGS", []),
            "environment": cfg["ENV"], "index": indexer.stats(),
            "sample_project": db.scalar("SELECT id FROM projects WHERE is_sample=1 LIMIT 1"),
            "limits": {k: cfg[k] for k in ("PUBLIC_CHAT_PER_IP_10MIN", "PUBLIC_CHAT_PER_IP_DAY",
                                           "PUBLIC_CHAT_GLOBAL_DAY", "PUBLIC_CHAT_MAX_CHARS")},
        },
    )


@bp.put("/settings/<key>")
def settings_put(key):
    saved = settings_svc.save(key, body())
    _public_changed()
    return jsonify(saved)


@bp.get("/diagnostics")
def diagnostics():
    from ..diagnostics import run_all

    return jsonify(run_all(current_app.config))


@bp.post("/sessions/revoke")
def sessions_revoke():
    from ..security import login_user, revoke_all_sessions

    revoke_all_sessions()
    login_user()  # keep the current session alive with the new epoch
    return jsonify(ok=True, csrf=session["csrf"])


@bp.post("/security/pin")
def change_pin():
    """Change the login PIN. Requires the current PIN; failures count toward the PIN lockout."""
    from ..security import pin_lock_seconds, record_pin_failure, set_pin, verify_pin

    d = body()
    if pin_lock_seconds():
        return jsonify(error="Too many incorrect PINs. Try again later."), 429
    if not verify_pin(str(d.get("current", ""))):
        record_pin_failure()
        raise ValidationError({"current": "Current PIN is incorrect."})
    new, confirm = str(d.get("new", "")), str(d.get("confirm", ""))
    if new != confirm:
        raise ValidationError({"confirm": "The two PINs don't match."})
    try:
        set_pin(new)
    except ValueError as exc:
        raise ValidationError({"new": str(exc)})
    activity.log_event("security", "Login PIN changed")
    return jsonify(ok=True)


@bp.delete("/sample-data")
def sample_delete():
    ids = [r["id"] for r in db.query("SELECT id FROM projects WHERE is_sample=1")]
    for pid in ids:
        projects.delete_project(pid)
    _public_changed()
    return jsonify(ok=True, removed=len(ids))


# ---------------------------------------------------------------------------
# Media (images stored in the database - Render's disk is ephemeral)
# ---------------------------------------------------------------------------
_MAGIC = [(b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"),
          (b"GIF89a", "image/gif")]


def _sniff(data):
    for sig, mime in _MAGIC:
        if data.startswith(sig):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@bp.post("/media")
def media_upload():
    f = request.files.get("file")
    if not f:
        raise ValidationError({"file": "no file"})
    data = f.read()
    if len(data) > 3 * 1024 * 1024:
        raise ValidationError({"file": "max 3 MB"})
    mime = _sniff(data)
    if not mime:
        raise ValidationError({"file": "only PNG, JPEG, GIF or WebP images"})
    token = secrets.token_hex(16)
    db.insert("INSERT INTO media(token, filename, mime, size, data, created_at) VALUES (?,?,?,?,?,?)",
              (token, (f.filename or "")[:120], mime, len(data), base64.b64encode(data).decode(), now_iso()))
    return jsonify(url=f"/media/{token}", token=token), 201


@bp.get("/media")
def media_list():
    rows = db.query("SELECT id, token, filename, mime, size, created_at FROM media ORDER BY id DESC LIMIT 200")
    return jsonify([dict(r, url=f"/media/{r['token']}") for r in rows])


@bp.delete("/media/<int:mid>")
def media_delete(mid):
    db.execute("DELETE FROM media WHERE id=?", (mid,))
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Export & index
# ---------------------------------------------------------------------------
def _download(content, filename, mime):
    resp = Response(content, mimetype=mime)
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@bp.get("/export/json")
def export_json():
    include_ai = request.args.get("ai", "1") == "1"
    data = export.full_export(include_ai=include_ai)
    return _download(json.dumps(data, ensure_ascii=False, indent=1), f"astra-backup-{now_iso()[:10]}.json",
                     "application/json")


@bp.get("/export/csv/<table>")
def export_csv(table):
    try:
        content = export.csv_export(table)
    except KeyError:
        return jsonify(error="Unknown table"), 404
    return _download("﻿" + content, f"astra-{table}-{now_iso()[:10]}.csv", "text/csv")


@bp.get("/export/journals.md")
def export_journals():
    return _download(export.markdown_journals(), f"astra-journals-{now_iso()[:10]}.md", "text/markdown")


@bp.post("/index/rebuild")
def index_rebuild():
    n = indexer.rebuild_all()
    return jsonify(ok=True, chunks=n, stats=indexer.stats())


@bp.post("/index/embed")
def index_embed():
    n = indexer.embed_pending(limit=100)
    return jsonify(ok=True, embedded=n, stats=indexer.stats())
