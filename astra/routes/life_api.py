"""Private JSON API for the personal OS sections: Tasks, Journaling, Medicines,
Expenses and Exhibit Management. Every route is admin-only (server-side)."""
from flask import Blueprint, jsonify, request

from ..security import admin_required
from ..services import exhibit, finance, medicines, personal, public_data
from ..utils import ValidationError, client_today

bp = Blueprint("life_api", __name__, url_prefix="/api/admin")


@bp.before_request
@admin_required
def _guard():
    return None


@bp.after_request
def _after(response):
    if request.method != "GET" and response.status_code < 400:
        public_data.invalidate()
        if "/exhibit" in request.path:
            from ..ai import public_bot

            public_bot.invalidate()
    return response


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError({"_": "JSON object body required"})
    return data


def today():
    return client_today(request.args.get("today") or (request.get_json(silent=True) or {}).get("today"))


def found(obj):
    return (jsonify(obj), 200) if obj else (jsonify(error="Not found"), 404)


# ---------------------------------------------------------------- Tasks
@bp.get("/todos")
def todos():
    a = request.args
    return jsonify(personal.todo_list(view=a.get("view", "all"), q=a.get("q"), priority=a.get("priority"),
                                      sort=a.get("sort", "smart"), today=today()))


@bp.post("/todos")
def todo_create():
    return jsonify(personal.todo_create(body())), 201


@bp.route("/todos/<int:tid>", methods=["PUT", "PATCH"])
def todo_update(tid):
    return found(personal.todo_update(tid, body()))


@bp.delete("/todos/<int:tid>")
def todo_delete(tid):
    return found({"ok": True} if personal.todo_delete(tid) else None)


@bp.get("/todos/stats")
def todo_stats():
    return jsonify(personal.todo_stats(today()))


# ---------------------------------------------------------------- Journaling
@bp.get("/diary")
def diary_list():
    a = request.args
    return jsonify(personal.diary_list(q=a.get("q"), month=a.get("month"), on_date=a.get("date"),
                                       limit=a.get("limit", 60, type=int), offset=a.get("offset", 0, type=int)))


@bp.post("/diary")
def diary_create():
    return jsonify(personal.diary_create(body())), 201


@bp.get("/diary/<int:eid>")
def diary_get(eid):
    return found(personal.diary_get(eid))


@bp.route("/diary/<int:eid>", methods=["PUT", "PATCH"])
def diary_update(eid):
    return found(personal.diary_update(eid, body()))


@bp.delete("/diary/<int:eid>")
def diary_delete(eid):
    return found({"ok": True} if personal.diary_delete(eid) else None)


@bp.get("/diary/calendar")
def diary_calendar():
    return jsonify(personal.diary_calendar(request.args.get("month") or today()[:7]))


@bp.get("/diary/stats")
def diary_stats():
    return jsonify(personal.diary_stats(today()))


# ---------------------------------------------------------------- Medicines
@bp.get("/medicines")
def med_list():
    return jsonify(medicines.list_medicines(request.args.get("status"), request.args.get("q")))


@bp.post("/medicines")
def med_create():
    return jsonify(medicines.create(body())), 201


@bp.get("/medicines/<int:mid>")
def med_get(mid):
    return found(medicines.get(mid))


@bp.route("/medicines/<int:mid>", methods=["PUT", "PATCH"])
def med_update(mid):
    return found(medicines.update(mid, body(), today()))


@bp.delete("/medicines/<int:mid>")
def med_delete(mid):
    return found({"ok": True} if medicines.delete(mid) else None)


@bp.post("/medicines/<int:mid>/stop")
def med_stop(mid):
    return found(medicines.stop(mid, today()))


@bp.post("/medicines/<int:mid>/resume")
def med_resume(mid):
    return found(medicines.resume(mid))


@bp.get("/medicines/grid")
def med_grid():
    a = request.args
    return jsonify(medicines.grid(start=a.get("start"), days=a.get("days", 14, type=int), status=a.get("status", "active"),
                                  today=today(), medicine_id=a.get("medicine_id", type=int)))


@bp.post("/medicines/dose")
def med_dose():
    d = body()
    return jsonify(medicines.set_dose(d.get("medicine_id"), d.get("date"), int(d.get("dose_index", 0)),
                                      bool(d.get("taken")), today()))


@bp.get("/medicines/stats")
def med_stats():
    return jsonify(medicines.stats(request.args.get("window", 30, type=int), today()))


@bp.get("/medicines/history")
def med_history():
    return jsonify(medicines.history(request.args.get("medicine_id", type=int)))


# ---------------------------------------------------------------- Expenses
@bp.get("/finance/tx")
def tx_list():
    a = request.args
    return jsonify(finance.list_tx(sort=a.get("sort", "newest"), limit=a.get("limit", 100, type=int),
                                   offset=a.get("offset", 0, type=int), kind=a.get("kind"), category=a.get("category"),
                                   q=a.get("q"), date_from=a.get("from"), date_to=a.get("to"), month=a.get("month")))


@bp.post("/finance/tx")
def tx_create():
    return jsonify(finance.create(body())), 201


@bp.route("/finance/tx/<int:tid>", methods=["PUT", "PATCH"])
def tx_update(tid):
    return found(finance.update(tid, body()))


@bp.delete("/finance/tx/<int:tid>")
def tx_delete(tid):
    return found({"ok": True} if finance.delete(tid) else None)


@bp.get("/finance/stats")
def fin_stats():
    return jsonify(finance.stats(today()))


@bp.get("/finance/monthly")
def fin_monthly():
    return jsonify(finance.monthly())


@bp.get("/finance/categories")
def fin_categories():
    return jsonify(finance.categories())


@bp.post("/finance/categories")
def fin_category_save():
    d = body()
    return jsonify(finance.save_category(d.get("kind"), d.get("name"), d.get("old_name")))


@bp.delete("/finance/categories")
def fin_category_delete():
    d = body()
    return jsonify(finance.delete_category(d.get("kind"), d.get("name")))


# ---------------------------------------------------------------- Exhibit Management
@bp.get("/projects/<int:pid>/exhibit")
def exhibit_get(pid):
    return found(exhibit.get(pid))


@bp.put("/projects/<int:pid>/exhibit")
def exhibit_save(pid):
    return found(exhibit.save_draft(pid, body()))


@bp.post("/projects/<int:pid>/exhibit/publish")
def exhibit_publish(pid):
    return found(exhibit.publish(pid, request.get_json(silent=True) or None))


@bp.post("/projects/<int:pid>/exhibit/unpublish")
def exhibit_unpublish(pid):
    return found(exhibit.unpublish(pid))


@bp.post("/projects/<int:pid>/exhibit/discard")
def exhibit_discard(pid):
    return found(exhibit.discard_draft(pid))


@bp.post("/projects/<int:pid>/exhibit/generate")
def exhibit_generate(pid):
    return found(exhibit.generate(pid))
