"""Private personal OS pages. Six primary sections only:
Projects · Medicines · Tasks · Journaling · Expenses · AI Assistant
(+ a small System utility page in the sidebar footer).

Pages are served as full HTML (deep links and refresh work) and the admin shell
navigates between them client-side, so the assistant HUD persists."""
from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from ..db import db
from ..markdown_render import render_markdown
from ..security import admin_required, end_visit, is_fresh_visit
from ..services import entities, projects

bp = Blueprint("admin", __name__, url_prefix="/admin")

SECTIONS = {
    "projects": [("projects", "Projects"), ("exhibits", "Exhibit Management"), ("profile", "Public Profile")],
    "medicines": [("dashboard", "Overview"), ("tracking", "Tracking"), ("list", "Medicines"), ("history", "History")],
    "tasks": [("dashboard", "Overview"), ("all", "All"), ("today", "Today"), ("upcoming", "Upcoming"),
              ("completed", "Completed")],
    "journaling": [("write", "Write"), ("entries", "Entries")],
    "expenses": [("dashboard", "Overview"), ("transactions", "Transactions"), ("monthly", "Monthly"),
                 ("categories", "Categories")],
    "assistant": [("settings", "Personality"), ("voice", "Voice"), ("memory", "Memory"), ("history", "History")],
}
SYSTEM_SECTIONS = [("system", "System status", "pulse"), ("security", "Login & security", "settings"),
                   ("data", "Backup & data", "inbox")]


@bp.before_request
def _guard():
    # Entering the admin side always asks for the PIN; moving around inside it does not.
    if session.get("admin") and is_fresh_visit():
        end_visit()
    return _require_admin()


@admin_required
def _require_admin():
    return None


@bp.app_context_processor
def _nav_context():
    return {"nav_sections": SECTIONS} if request.path.startswith("/admin") else {}


def _section(name, view, template, **ctx):
    views = [v for v, _ in SECTIONS[name]]
    if view not in views:
        abort(404)
    label = dict(SECTIONS[name])[view]
    return render_template(template, page=name, view=view, view_label=label, subnav=SECTIONS[name], **ctx)


@bp.route("/")
def home():
    return redirect(url_for("admin.project_list"))


# ---------------------------------------------------------------- Projects
@bp.route("/projects")
def project_list():
    return _section("projects", "projects", "admin/projects.html")


@bp.route("/exhibits")
def exhibits():
    return _section("projects", "exhibits", "admin/exhibits.html")


@bp.route("/profile")
def profile():
    return _section("projects", "profile", "admin/profile.html")


@bp.route("/projects/<int:pid>")
@bp.route("/projects/<int:pid>/<any(journal, exhibit):tab>")
def workspace(pid, tab="overview"):
    project = projects.get_project(pid)
    if not project:
        abort(404)
    return render_template("admin/workspace.html", page="projects", view="projects", subnav=SECTIONS["projects"],
                           project=project, tab=tab)


@bp.route("/projects/<int:pid>/edit")
def project_edit(pid):  # editing happens in a dialog on the workspace
    return redirect(url_for("admin.workspace", pid=pid))


@bp.route("/journal/new")
def journal_new():
    pid = request.args.get("project_id", type=int)
    project = projects.get_project(pid) if pid else None
    if not project:
        abort(404)
    return render_template("admin/journal_editor.html", page="projects", entry_id=None, project=project)


@bp.route("/journal/<int:jid>")
def journal_read(jid):
    entry = entities.get_item("journals", jid)
    if not entry or not entry["project_id"]:
        abort(404)
    newer, older = db.many([
        ("SELECT id, title, entry_date FROM journals WHERE project_id=? AND (entry_date > ? OR (entry_date = ? AND id > ?)) "
         "ORDER BY entry_date, id LIMIT 1", (entry["project_id"], entry["entry_date"], entry["entry_date"], jid)),
        ("SELECT id, title, entry_date FROM journals WHERE project_id=? AND (entry_date < ? OR (entry_date = ? AND id < ?)) "
         "ORDER BY entry_date DESC, id DESC LIMIT 1", (entry["project_id"], entry["entry_date"], entry["entry_date"], jid)),
    ])
    words = len((entry["content"] or "").split())
    return render_template("admin/journal_read.html", page="projects", entry=entry, html=render_markdown(entry["content"]),
                           newer=newer[0] if newer else None, older=older[0] if older else None,
                           words=words, minutes=max(1, round(words / 220)))


@bp.route("/journal/<int:jid>/edit")
def journal_edit(jid):
    entry = entities.get_item("journals", jid)
    if not entry or not entry["project_id"]:
        abort(404)
    return render_template("admin/journal_editor.html", page="projects", entry_id=jid,
                           project=projects.get_project(entry["project_id"]))


# ---------------------------------------------------------------- Personal sections
@bp.route("/medicines")
@bp.route("/medicines/<view>")
def medicines(view="dashboard"):
    if view in ("active", "stopped"):  # merged into one list with a status filter
        return redirect(url_for("admin.medicines", view="list", status=view))
    return _section("medicines", view, "admin/medicines.html")


@bp.route("/tasks")
@bp.route("/tasks/<view>")
def tasks(view="dashboard"):
    return _section("tasks", view, "admin/tasks.html")


@bp.route("/journaling")
@bp.route("/journaling/<view>")
def journaling(view="write"):
    return _section("journaling", view, "admin/journaling.html", entry_id=request.args.get("entry", type=int))


@bp.route("/expenses")
@bp.route("/expenses/<view>")
def expenses(view="dashboard"):
    if view in ("income", "expenses"):  # merged into Transactions with a type filter
        return redirect(url_for("admin.expenses", view="transactions", kind="income" if view == "income" else "expense"))
    return _section("expenses", view, "admin/expenses.html")


@bp.route("/assistant")
@bp.route("/assistant/<view>")
@bp.route("/assistant/history/<int:cid>")
def assistant(view="settings", cid=None):
    if cid is not None:
        if not db.scalar("SELECT id FROM ai_conversations WHERE id=?", (cid,)):
            abort(404)
        view = "history"
    return _section("assistant", view, "admin/assistant.html", conversation_id=cid)


# ---------------------------------------------------------------- System (footer utility)
@bp.route("/settings")
@bp.route("/settings/<section>")
def settings(section="system"):
    if section not in [s[0] for s in SYSTEM_SECTIONS]:
        abort(404)
    return render_template("admin/settings.html", page="system", section=section, sections=SYSTEM_SECTIONS)
