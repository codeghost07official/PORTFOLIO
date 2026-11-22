"""Personal finance: income & expense ledger with real-data analytics.
Amounts are stored as integer minor units (paise/cents) to avoid float errors."""
import re
from datetime import date

from ..db import db
from ..utils import ValidationError, local_today, now_iso
from . import settings as settings_svc

KINDS = ["income", "expense"]
_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def _cents(value):
    try:
        s = str(value).replace(",", "").strip()
        if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
            raise ValueError
        cents = round(float(s) * 100)
    except (TypeError, ValueError):
        raise ValidationError({"amount": "Enter an amount like 250 or 1299.50"})
    if cents <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if cents > 10 ** 13:
        raise ValidationError({"amount": "Amount is too large."})
    return cents


def _decode(t):
    if t:
        t["amount"] = t["amount_cents"] / 100
    return t


def _values(data, partial=False):
    out = {}
    if "kind" in data or not partial:
        if data.get("kind") not in KINDS:
            raise ValidationError({"kind": "choose income or expense"})
        out["kind"] = data["kind"]
    if "amount" in data or not partial:
        out["amount_cents"] = _cents(data.get("amount"))
    if "description" in data:
        out["description"] = str(data.get("description") or "").strip()[:300]
    if "category" in data or not partial:
        out["category"] = (str(data.get("category") or "").strip() or "Other")[:60]
    if "occurred_at" in data or not partial:
        when = str(data.get("occurred_at") or "").strip()[:16]
        if not _WHEN.match(when):
            raise ValidationError({"occurred_at": "Pick a date and time."})
        try:
            date.fromisoformat(when[:10])
        except ValueError:
            raise ValidationError({"occurred_at": "Invalid date."})
        out["occurred_at"] = when
    return out


def get(tid):
    return _decode(db.one("SELECT * FROM transactions WHERE id=?", (int(tid),)))


def create(data):
    v = _values(data)
    ts = now_iso()
    v.update(created_at=ts, updated_at=ts)
    cols = list(v)
    tid = db.insert(f"INSERT INTO transactions ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [v[c] for c in cols])
    return get(tid)


def update(tid, data):
    if not get(tid):
        return None
    v = _values(data, partial=True)
    if v:
        v["updated_at"] = now_iso()
        db.execute(f"UPDATE transactions SET {', '.join(f'{c}=?' for c in v)} WHERE id=?", [*v.values(), int(tid)])
    return get(tid)


def delete(tid):
    if not get(tid):
        return False
    db.execute("DELETE FROM transactions WHERE id=?", (int(tid),))
    return True


def _where(kind=None, category=None, q=None, date_from=None, date_to=None, month=None):
    sql, params = " WHERE 1=1", []
    if kind in KINDS:
        sql += " AND kind=?"
        params.append(kind)
    if category:
        sql += " AND category=?"
        params.append(category)
    if q:
        sql += " AND (description LIKE ? OR category LIKE ?)"
        params += [f"%{q.strip()}%"] * 2
    if month:
        sql += " AND substr(occurred_at,1,7)=?"
        params.append(month[:7])
    if date_from:
        sql += " AND substr(occurred_at,1,10)>=?"
        params.append(date_from[:10])
    if date_to:
        sql += " AND substr(occurred_at,1,10)<=?"
        params.append(date_to[:10])
    return sql, params


SORTS = {"newest": "occurred_at DESC, id DESC", "oldest": "occurred_at, id",
         "amount_desc": "amount_cents DESC", "amount_asc": "amount_cents"}


def list_tx(sort="newest", limit=100, offset=0, **filters):
    where, params = _where(**filters)
    rows, summary = db.many([
        (f"SELECT * FROM transactions{where} ORDER BY {SORTS.get(sort, SORTS['newest'])} LIMIT ? OFFSET ?",
         [*params, min(int(limit), 500), int(offset)]),
        (f"SELECT COUNT(*) AS n, SUM(CASE WHEN kind='income' THEN amount_cents ELSE 0 END) AS inc, "
         f"SUM(CASE WHEN kind='expense' THEN amount_cents ELSE 0 END) AS exp FROM transactions{where}", params),
    ])
    s = summary[0]
    return {"items": [_decode(r) for r in rows], "count": int(s["n"] or 0),
            "income": (s["inc"] or 0) / 100, "expense": (s["exp"] or 0) / 100,
            "net": ((s["inc"] or 0) - (s["exp"] or 0)) / 100}


def _month_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7]) + n
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}-{m:02d}"


def stats(today=None, months=12):
    cur = (today or local_today())[:7]
    first = _month_add(cur, -(months - 1))
    totals, monthly, cat_month, cat_all, recent = db.many([
        ("SELECT SUM(CASE WHEN kind='income' THEN amount_cents ELSE 0 END) AS inc, "
         "SUM(CASE WHEN kind='expense' THEN amount_cents ELSE 0 END) AS exp, COUNT(*) AS n FROM transactions", ()),
        ("SELECT substr(occurred_at,1,7) AS ym, SUM(CASE WHEN kind='income' THEN amount_cents ELSE 0 END) AS inc, "
         "SUM(CASE WHEN kind='expense' THEN amount_cents ELSE 0 END) AS exp, COUNT(*) AS n FROM transactions "
         "WHERE substr(occurred_at,1,7) >= ? GROUP BY 1", (first,)),
        ("SELECT category, SUM(amount_cents) AS c FROM transactions WHERE kind='expense' AND substr(occurred_at,1,7)=? "
         "GROUP BY category ORDER BY c DESC", (cur,)),
        ("SELECT kind, category, SUM(amount_cents) AS c, COUNT(*) AS n FROM transactions GROUP BY kind, category "
         "ORDER BY c DESC", ()),
        ("SELECT * FROM transactions ORDER BY occurred_at DESC, id DESC LIMIT 8", ()),
    ])
    t = totals[0]
    by_month = {r["ym"]: r for r in monthly}
    labels = [_month_add(first, i) for i in range(months)]
    this = by_month.get(cur, {})
    return {
        "currency": settings_svc.get("finance")["currency"],
        "total_income": (t["inc"] or 0) / 100, "total_expense": (t["exp"] or 0) / 100,
        "net": ((t["inc"] or 0) - (t["exp"] or 0)) / 100, "count": int(t["n"] or 0),
        "month": cur, "month_income": (this.get("inc") or 0) / 100, "month_expense": (this.get("exp") or 0) / 100,
        "months": labels,
        "income_series": [(by_month.get(m, {}).get("inc") or 0) / 100 for m in labels],
        "expense_series": [(by_month.get(m, {}).get("exp") or 0) / 100 for m in labels],
        "month_categories": [{"category": r["category"], "amount": r["c"] / 100} for r in cat_month],
        "categories": [{"kind": r["kind"], "category": r["category"], "amount": r["c"] / 100, "count": int(r["n"])}
                       for r in cat_all],
        "recent": [_decode(r) for r in recent],
    }


def monthly(limit=24):
    rows = db.query("SELECT substr(occurred_at,1,7) AS ym, SUM(CASE WHEN kind='income' THEN amount_cents ELSE 0 END) AS inc, "
                    "SUM(CASE WHEN kind='expense' THEN amount_cents ELSE 0 END) AS exp, COUNT(*) AS n "
                    "FROM transactions GROUP BY 1 ORDER BY 1 DESC LIMIT ?", (int(limit),))
    return [{"month": r["ym"], "income": (r["inc"] or 0) / 100, "expense": (r["exp"] or 0) / 100,
             "net": ((r["inc"] or 0) - (r["exp"] or 0)) / 100, "count": int(r["n"])} for r in rows]


def categories():
    cfg = settings_svc.get("finance")
    used = {(r["kind"], r["category"]): r for r in db.query(
        "SELECT kind, category, COUNT(*) AS n, SUM(amount_cents) AS c FROM transactions GROUP BY kind, category")}
    out = []
    for kind in KINDS:
        names = list(dict.fromkeys(cfg[f"{kind}_categories"] + [c for k, c in used if k == kind]))
        for name in names:
            u = used.get((kind, name))
            out.append({"kind": kind, "name": name, "count": int(u["n"]) if u else 0,
                        "amount": (u["c"] or 0) / 100 if u else 0, "custom": name in cfg[f"{kind}_categories"]})
    return {"currency": cfg["currency"], "items": out}


def save_category(kind, name, old_name=None):
    if kind not in KINDS:
        raise ValidationError({"kind": "invalid"})
    name = str(name or "").strip()[:60]
    if not name:
        raise ValidationError({"name": "required"})
    cfg = settings_svc.get("finance")
    key = f"{kind}_categories"
    lst = [c for c in cfg[key] if c != old_name]
    if name not in lst:
        lst.append(name)
    cfg[key] = lst
    settings_svc.save("finance", cfg)
    if old_name and old_name != name:  # rename everywhere
        db.execute("UPDATE transactions SET category=?, updated_at=? WHERE kind=? AND category=?",
                   (name, now_iso(), kind, old_name))
    return categories()


def delete_category(kind, name):
    """Removes the category from the list; existing transactions move to 'Other' (never deleted)."""
    cfg = settings_svc.get("finance")
    key = f"{kind}_categories"
    cfg[key] = [c for c in cfg[key] if c != name]
    settings_svc.save("finance", cfg)
    db.execute("UPDATE transactions SET category='Other', updated_at=? WHERE kind=? AND category=?", (now_iso(), kind, name))
    return categories()


def summary_for_assistant(today=None):
    s = stats(today)
    cats = ", ".join(f"{c['category']} {s['currency']}{c['amount']:,.0f}" for c in s["month_categories"][:6])
    return (f"Finances: all-time income {s['currency']}{s['total_income']:,.2f}, expenses {s['currency']}"
            f"{s['total_expense']:,.2f}, net {s['currency']}{s['net']:,.2f}. This month ({s['month']}): income "
            f"{s['currency']}{s['month_income']:,.2f}, expenses {s['currency']}{s['month_expense']:,.2f}"
            + (f"; top spending: {cats}." if cats else "."))
