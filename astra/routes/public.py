"""Public exhibition: pages, public JSON, media, public chatbot, health."""
import base64
import logging

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request

from ..ai import gemini, public_bot
from ..db import db
from ..security import client_key, rate_allow, rate_count, rate_record
from ..services import public_data
from ..services import settings as settings_svc
from ..utils import youtube_embed

bp = Blueprint("public", __name__)
log = logging.getLogger("astra.public")


def public_settings():
    s = settings_svc.all_settings()
    return {
        "profile": s["profile"], "appearance": s["appearance"], "visibility": s["visibility"],
        "login_entry": s["login"]["entry_point"],
        "chatbot": {"enabled": s["chatbot"]["public_enabled"] and s["visibility"].get("show_chatbot", True),
                    "greeting": s["chatbot"]["public_greeting"], "online": gemini.configured()},
    }


def _page(template, **extra):
    return render_template(template, **public_settings(), **extra)


@bp.route("/")
def index():
    projects = public_data.projects()
    featured = [p for p in projects if p["is_featured"]][:3] or projects[:3]
    return _page("public/index.html", featured=featured, projects=projects, stats=public_data.stats(),
                 technologies=public_data.technologies()[:12], latest_logs=[], workshop=public_data.in_progress(6))


@bp.route("/about")
def about():
    return _page("public/about.html", stats=public_data.stats(), technologies=public_data.technologies())


@bp.route("/achievements")
def achievements():
    completed = [p for p in public_data.projects() if p["status"] == "completed"]
    return _page("public/achievements.html", completed=completed, stats=public_data.stats())


@bp.route("/journey")
def journey():
    """Profile milestones merged with real project start/completion dates."""
    ctx = public_settings()
    events = [{"date": j.get("year", ""), "sort": str(j.get("year", "")), "title": j.get("title", ""),
               "detail": j.get("detail", ""), "kind": "milestone"} for j in ctx["profile"].get("journey", [])]
    for p in public_data.projects():
        if p.get("start_date"):
            events.append({"date": p["start_date"], "sort": p["start_date"], "title": f"Started {p['name']}",
                           "detail": p.get("tagline", ""), "kind": "start", "slug": p["slug"]})
        if p.get("completed_date"):
            events.append({"date": p["completed_date"], "sort": p["completed_date"], "title": f"Shipped {p['name']}",
                           "detail": p.get("tagline", ""), "kind": "ship", "slug": p["slug"]})
    return render_template("public/journey.html", **ctx, events=events, logs=[])


@bp.route("/contact")
def contact():
    return _page("public/contact.html")


@bp.route("/projects")
def projects():
    items = public_data.projects()
    cats = sorted({p["category"] for p in items if p["category"]})
    techs = sorted({t for p in items for t in p["technologies"]}, key=str.lower)
    featured = [p for p in items if p["is_featured"]][:3]
    return _page("public/projects.html", projects=items, categories=cats, techs=techs, featured=featured,
                 workshop=public_data.in_progress(),
                 current_category=request.args.get("category", ""), current_tech=request.args.get("tech", ""),
                 current_q=request.args.get("q", ""))


@bp.route("/projects/<slug>")
def project_detail(slug):
    project = public_data.project(slug)
    if not project:
        teaser = public_data.teaser(slug)  # in progress: only title + status, never details
        if not teaser:
            abort(404)
        return _page("public/in_progress.html", project=teaser)
    journals = public_data.journals(project["id"]) if project["show_journal"] else []
    allp = public_data.projects()
    idx = next((i for i, p in enumerate(allp) if p["id"] == project["id"]), 0)
    prev_p = allp[idx - 1] if len(allp) > 1 else None
    next_p = allp[(idx + 1) % len(allp)] if len(allp) > 1 else None
    related = [p for p in allp if p["id"] != project["id"] and (
        p["category"] == project["category"] or set(p["technologies"]) & set(project["technologies"]))][:3]
    return _page(
        "public/project.html", project=project, journals=journals, exhibit_no=idx + 1, exhibit_total=len(allp),
        milestones=public_data.milestones(project["id"]), youtube_embed=youtube_embed(project.get("youtube_url")),
        prev_p=prev_p, next_p=next_p, others=related or [p for p in allp if p["id"] != project["id"]][:3],
    )


@bp.route("/api/public/projects")
def api_projects():
    fields = ("slug", "name", "tagline", "category", "status", "technologies", "tags", "cover_image",
              "github_url", "live_url", "youtube_url", "start_date", "completed_date", "is_featured")
    return jsonify([{f: p.get(f) for f in fields} for p in public_data.projects()]
                   + [{"slug": t["slug"], "name": t["name"], "category": t["category"], "status": "in_progress"}
                      for t in public_data.in_progress()])


@bp.route("/media/<token>")
def media(token):
    if not token.isalnum() or len(token) > 64:
        abort(404)
    row = db.one("SELECT mime, data FROM media WHERE token=?", (token,))
    if not row:
        abort(404)
    resp = Response(base64.b64decode(row["data"]), mimetype=row["mime"])
    resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
    resp.headers["Content-Security-Policy"] = "default-src 'none'"
    return resp


@bp.route("/api/public/chat", methods=["POST"])
def public_chat():
    cfg = current_app.config
    chat_cfg = settings_svc.get("chatbot")
    if not chat_cfg["public_enabled"]:
        return jsonify(error="The guide is offline right now."), 503
    if not gemini.configured():
        return jsonify(error="The AI guide hasn't been connected yet. Please explore the projects directly."), 503
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify(error="Please type a question."), 400
    if len(message) > cfg["PUBLIC_CHAT_MAX_CHARS"]:
        return jsonify(error=f"Please keep questions under {cfg['PUBLIC_CHAT_MAX_CHARS']} characters."), 400
    key = client_key()
    if not rate_allow("pchat10", key, cfg["PUBLIC_CHAT_PER_IP_10MIN"], 600, record=False) or \
            not rate_allow("pchatday", key, cfg["PUBLIC_CHAT_PER_IP_DAY"], 86400, record=False):
        return jsonify(error="You've reached the question limit for now — please try again later."), 429
    global_cap = chat_cfg.get("public_daily_limit") or cfg["PUBLIC_CHAT_GLOBAL_DAY"]
    if rate_count("pchatglobal", "all", 86400) >= global_cap:
        return jsonify(error="The guide has answered its daily quota. Please come back tomorrow."), 429
    for bucket, k in (("pchat10", key), ("pchatday", key), ("pchatglobal", "all")):
        rate_record(bucket, k)
    history = []
    for h in (data.get("history") or [])[-6:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and isinstance(h.get("text"), str):
            history.append({"role": h["role"], "text": h["text"][:1000]})
    try:
        reply = public_bot.answer(message, history)
    except gemini.GeminiError as exc:
        log.warning("Public chat failed: %s", exc)
        return jsonify(error="The guide is having trouble answering right now. Please try again shortly."), 502
    from ..markdown_render import render_markdown

    return jsonify(reply=reply, html=str(render_markdown(reply)))


@bp.route("/robots.txt")
def robots():
    body = f"User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: {current_app.config['ADMIN_LOGIN_PATH']}\n"
    return Response(body, mimetype="text/plain")


@bp.route("/healthz")
def health():
    ok = current_app.config.get("DB_READY", False)
    if ok:
        try:
            db.scalar("SELECT 1")
        except Exception:
            ok = False
    return jsonify(status="ok" if ok else "degraded", database=db.driver_name), (200 if ok else 503)
