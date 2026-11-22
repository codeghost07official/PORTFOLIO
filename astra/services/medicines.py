"""Medicine tracking (organisation only, not medical advice).

Schedules: daily | alternate (every other day from start_date) | weekdays (chosen days)
| interval (every N days from start_date). Each scheduled day has one checkbox per
dose (dose_times). A dose is MISSED only if it was scheduled on a past day and
not logged; unscheduled days never count. STOP keeps the medicine and its history
(schedule ends the day before stopping); DELETE removes medicine + logs.
"""
from datetime import date, timedelta

from ..db import db
from ..utils import ValidationError, clean_date, jdumps, jloads, local_today, now_iso

FREQUENCIES = ["daily", "alternate", "weekdays", "interval"]
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _d(s):
    return date.fromisoformat(s[:10]) if s else None


MAX_DOSES = 8


def _labels(labels, n):
    labels = [str(x).strip()[:30] for x in (labels or []) if str(x).strip()]
    return [labels[i] if i < len(labels) else f"Dose {i + 1}" for i in range(n)]


def _decode(m):
    if m:
        m["weekdays"] = jloads(m.get("weekdays"), [])
        raw = jloads(m.get("dose_times"), []) or []
        plan = sorted(jloads(m.get("dose_plan"), []) or [], key=lambda e: e["from"])
        if not plan:  # medicines created before dose plans: one plan from the start date
            plan = [{"from": m["start_date"], "count": max(1, len(raw))}]
        m["dose_plan"] = plan
        m["doses_per_day"] = plan[-1]["count"]
        m["dose_times"] = _labels(raw, max(e["count"] for e in plan))
        m["schedule_label"] = schedule_label(m)
    return m


def doses_on(m, day):
    """Number of scheduled doses on a given day, honouring changes over time."""
    iso = day.isoformat() if hasattr(day, "isoformat") else day
    count = m["dose_plan"][0]["count"]
    for e in m["dose_plan"]:
        if e["from"] <= iso:
            count = e["count"]
    return count


def schedule_label(m):
    f = m["frequency"]
    times = m["doses_per_day"]
    per = f"{times}× a day" if times > 1 else "once a day"
    if f == "daily":
        return f"Daily · {per}"
    if f == "alternate":
        return f"Alternate days · {per}"
    if f == "weekdays":
        return "Every " + ", ".join(WEEKDAY_NAMES[i] for i in sorted(m["weekdays"])) + f" · {per}"
    return f"Every {m['interval_days']} days · {per}"


def schedule_end(m):
    """Last day the medicine is scheduled (inclusive), or None if open-ended."""
    ends = [d for d in (_d(m.get("end_date")),) if d]
    if m.get("status") == "stopped" and m.get("stopped_at"):
        ends.append(_d(m["stopped_at"]) - timedelta(days=1))
    return min(ends) if ends else None


def is_scheduled(m, day):
    start = _d(m["start_date"])
    if day < start:
        return False
    end = schedule_end(m)
    if end and day > end:
        return False
    f, delta = m["frequency"], (day - start).days
    if f == "daily":
        return True
    if f == "alternate":
        return delta % 2 == 0
    if f == "interval":
        return delta % max(1, int(m["interval_days"] or 1)) == 0
    if f == "weekdays":
        return day.weekday() in m["weekdays"]
    return False


def _values(data, partial=False):
    out = {}
    if "name" in data or not partial:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "Enter the medicine name."})
        out["name"] = name[:120]
    for k, n in (("dosage", 120), ("notes", 4000)):
        if k in data:
            out[k] = str(data.get(k) or "").strip()[:n]
    if "frequency" in data or not partial:
        f = data.get("frequency") or "daily"
        if f not in FREQUENCIES:
            raise ValidationError({"frequency": "invalid frequency"})
        out["frequency"] = f
    if "weekdays" in data:
        days = sorted({int(x) for x in (data.get("weekdays") or []) if str(x).isdigit() and 0 <= int(x) <= 6})
        out["weekdays"] = jdumps(days)
    if "interval_days" in data:
        try:
            out["interval_days"] = max(1, min(60, int(data.get("interval_days") or 1)))
        except (TypeError, ValueError):
            raise ValidationError({"interval_days": "enter a number of days"})
    if "dose_times" in data or "doses_per_day" in data:
        raw = data.get("dose_times")
        items = raw.split(",") if isinstance(raw, str) else (raw or [])
        labels = [str(t).strip()[:30] for t in items if str(t).strip()][:MAX_DOSES]
        try:
            n = int(data.get("doses_per_day") or len(labels) or 1)
        except (TypeError, ValueError):
            raise ValidationError({"doses_per_day": "enter a number of doses"})
        if not 1 <= n <= MAX_DOSES:
            raise ValidationError({"doses_per_day": f"between 1 and {MAX_DOSES} doses per day"})
        out["_count"] = n
        out["dose_times"] = jdumps(_labels(labels, n))
    if "start_date" in data or not partial:
        out["start_date"] = clean_date(data.get("start_date"), "start_date") or local_today()
    if "end_date" in data:
        out["end_date"] = clean_date(data.get("end_date"), "end_date") if data.get("has_end", True) else None
    if out.get("frequency") == "weekdays" and "weekdays" in out and not jloads(out["weekdays"], []):
        raise ValidationError({"weekdays": "pick at least one day"})
    return out


def get(mid):
    return _decode(db.one("SELECT * FROM medicines WHERE id=?", (int(mid),)))


def create(data):
    v = _values(data)
    v.setdefault("weekdays", "[]")
    n = v.pop("_count", 1)
    v.setdefault("dose_times", jdumps(_labels([], n)))
    v["dose_plan"] = jdumps([{"from": v["start_date"], "count": n}])
    if v.get("end_date") and v["end_date"] < v["start_date"]:
        raise ValidationError({"end_date": "end date is before the start date"})
    if v["frequency"] == "weekdays" and not jloads(v["weekdays"], []):
        raise ValidationError({"weekdays": "pick at least one day"})
    ts = now_iso()
    v.update(status="active", created_at=ts, updated_at=ts)
    cols = list(v)
    mid = db.insert(f"INSERT INTO medicines ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [v[c] for c in cols])
    return get(mid)


def update(mid, data, today=None):
    m = get(mid)
    if not m:
        return None
    v = _values(data, partial=True)
    n = v.pop("_count", None)
    if n is not None and n != m["doses_per_day"]:
        eff = max(today or local_today(), v.get("start_date", m["start_date"]))
        plan = [e for e in m["dose_plan"] if e["from"] < eff] + [{"from": eff, "count": n}]
        v["dose_plan"] = jdumps(plan)
    elif "start_date" in v and len(m["dose_plan"]) == 1:
        v["dose_plan"] = jdumps([{"from": v["start_date"], "count": m["doses_per_day"]}])
    start = v.get("start_date", m["start_date"])
    end = v["end_date"] if "end_date" in v else m["end_date"]
    if end and end < start:
        raise ValidationError({"end_date": "end date is before the start date"})
    if v:
        v["updated_at"] = now_iso()
        db.execute(f"UPDATE medicines SET {', '.join(f'{c}=?' for c in v)} WHERE id=?", [*v.values(), int(mid)])
    return get(mid)


def stop(mid, today=None):
    if not get(mid):
        return None
    db.execute("UPDATE medicines SET status='stopped', stopped_at=?, updated_at=? WHERE id=?",
               (today or local_today(), now_iso(), int(mid)))
    return get(mid)


def resume(mid):
    if not get(mid):
        return None
    db.execute("UPDATE medicines SET status='active', stopped_at=NULL, updated_at=? WHERE id=?", (now_iso(), int(mid)))
    return get(mid)


def delete(mid):
    if not get(mid):
        return False
    db.batch([("DELETE FROM medicine_logs WHERE medicine_id=?", (int(mid),)),
              ("DELETE FROM medicines WHERE id=?", (int(mid),))])
    return True


def list_medicines(status=None, q=None):
    sql, params = "SELECT * FROM medicines WHERE 1=1", []
    if status in ("active", "stopped"):
        sql += " AND status=?"
        params.append(status)
    if q:
        sql += " AND (name LIKE ? OR notes LIKE ? OR dosage LIKE ?)"
        params += [f"%{q.strip()}%"] * 3
    return [_decode(m) for m in db.query(sql + " ORDER BY status, name COLLATE NOCASE", params)]


def set_dose(mid, day, dose_index, taken, today=None):
    m = get(mid)
    if not m:
        raise ValidationError({"medicine": "not found"})
    d = _d(clean_date(day, "date"))
    if d > _d(today or local_today()):
        raise ValidationError({"date": "you can't log a future dose"})
    if not is_scheduled(m, d):
        raise ValidationError({"date": "this medicine isn't scheduled on that day"})
    if not (0 <= int(dose_index) < doses_on(m, d)):
        raise ValidationError({"dose": "invalid dose"})
    if taken:
        db.execute("INSERT INTO medicine_logs(medicine_id, log_date, dose_index, status, logged_at) VALUES (?,?,?,?,?) "
                   "ON CONFLICT(medicine_id, log_date, dose_index) DO UPDATE SET status='taken', logged_at=excluded.logged_at",
                   (int(mid), d.isoformat(), int(dose_index), "taken", now_iso()))
    else:
        db.execute("DELETE FROM medicine_logs WHERE medicine_id=? AND log_date=? AND dose_index=?",
                   (int(mid), d.isoformat(), int(dose_index)))
    return {"medicine_id": int(mid), "date": d.isoformat(), "dose_index": int(dose_index), "taken": bool(taken)}


def _logs(mids, start, end):
    if not mids:
        return set()
    marks = ",".join("?" * len(mids))
    return {(r["medicine_id"], r["log_date"], r["dose_index"]) for r in db.query(
        f"SELECT medicine_id, log_date, dose_index FROM medicine_logs WHERE status='taken' AND medicine_id IN ({marks}) "
        "AND log_date BETWEEN ? AND ?", [*mids, start.isoformat(), end.isoformat()])}


def grid(start=None, days=14, status="active", today=None, medicine_id=None):
    """Spreadsheet data: medicines × dates × doses with a state per cell."""
    today_d = _d(today or local_today())
    days = max(1, min(62, int(days)))
    start_d = _d(start) if start else today_d - timedelta(days=days - 4)
    dates = [start_d + timedelta(days=i) for i in range(days)]
    meds = list_medicines(None if status == "all" else status)
    if medicine_id:
        meds = [m for m in meds if m["id"] == int(medicine_id)]
    taken = _logs([m["id"] for m in meds], dates[0], dates[-1])
    rows = []
    for m in meds:
        cells = []
        for d in dates:
            if not is_scheduled(m, d):
                cells.append({"state": "na"})
                continue
            doses = []
            for i in range(doses_on(m, d)):
                done = (m["id"], d.isoformat(), i) in taken
                state = "taken" if done else ("future" if d > today_d else "pending" if d == today_d else "missed")
                doses.append(state)
            cells.append({"state": "scheduled", "doses": doses})
        rows.append({"medicine": m, "cells": cells})
    return {"dates": [d.isoformat() for d in dates], "today": today_d.isoformat(), "rows": rows}


def stats(window=30, today=None):
    """Adherence analytics from real logs. Missed = scheduled past doses without a log."""
    today_d = _d(today or local_today())
    start = today_d - timedelta(days=window - 1)
    meds = list_medicines(None)
    taken = _logs([m["id"] for m in meds], start, today_d)
    per_med, daily = [], {(start + timedelta(days=i)).isoformat(): [0, 0] for i in range(window)}
    tot_sched = tot_taken = tot_missed = today_sched = today_taken = 0
    for m in meds:
        s = t = miss = 0
        for i in range(window):
            d = start + timedelta(days=i)
            if not is_scheduled(m, d):
                continue
            for k in range(doses_on(m, d)):
                done = (m["id"], d.isoformat(), k) in taken
                s += 1
                t += done
                if d < today_d and not done:
                    miss += 1
                if d == today_d:
                    today_sched += 1
                    today_taken += done
                if d < today_d or done:
                    daily[d.isoformat()][0] += done
                    daily[d.isoformat()][1] += 1
        tot_sched, tot_taken, tot_missed = tot_sched + s, tot_taken + t, tot_missed + miss
        if s:
            per_med.append({"id": m["id"], "name": m["name"], "status": m["status"], "scheduled": s, "taken": t,
                            "missed": miss, "adherence": round(100 * t / (t + miss)) if t + miss else None})
    recent = db.query("SELECT l.log_date, l.dose_index, l.logged_at, m.name, m.dose_times FROM medicine_logs l "
                      "JOIN medicines m ON m.id=l.medicine_id ORDER BY l.logged_at DESC LIMIT 10")
    for r in recent:
        times = jloads(r.pop("dose_times"), []) or ["Dose"]
        r["dose"] = times[r["dose_index"]] if r["dose_index"] < len(times) else f"Dose {r['dose_index'] + 1}"
    return {
        "window": window, "active": sum(1 for m in meds if m["status"] == "active"),
        "stopped": sum(1 for m in meds if m["status"] == "stopped"),
        "scheduled": tot_sched, "taken": tot_taken, "missed": tot_missed,
        "adherence": round(100 * tot_taken / (tot_taken + tot_missed)) if tot_taken + tot_missed else None,
        "today_scheduled": today_sched, "today_taken": today_taken,
        "per_medicine": sorted(per_med, key=lambda x: (x["adherence"] is None, x["adherence"] or 0)),
        "trend_days": [d[5:] for d in daily],
        "trend": [round(100 * a / b) if b else None for a, b in daily.values()],
        "recent": recent,
    }


def history(medicine_id=None, limit=200):
    sql = ("SELECT l.*, m.name, m.dose_times FROM medicine_logs l JOIN medicines m ON m.id=l.medicine_id")
    params = []
    if medicine_id:
        sql += " WHERE l.medicine_id=?"
        params.append(int(medicine_id))
    rows = db.query(sql + " ORDER BY l.log_date DESC, l.dose_index LIMIT ?", [*params, int(limit)])
    for r in rows:
        times = jloads(r.pop("dose_times"), []) or ["Dose"]
        r["dose"] = times[r["dose_index"]] if r["dose_index"] < len(times) else f"Dose {r['dose_index'] + 1}"
    return rows
