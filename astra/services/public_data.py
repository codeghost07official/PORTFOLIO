"""The ONLY data source for public pages and the public chatbot.

Every query here filters on public visibility, so private projects, private or
draft journals, notes, tasks, bugs and AI memories can never leak through the
public site or public API.
"""
import copy
import functools
import threading
import time

from ..db import db
from ..utils import jloads

_cache, _lock = {}, threading.Lock()
TTL = 120  # seconds; every admin write calls invalidate(), so this only bounds staleness from other processes


def invalidate():
    with _lock:
        _cache.clear()


def cached(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        key = (fn.__name__, args, tuple(sorted(kwargs.items())))
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return copy.deepcopy(hit[1])
        value = fn(*args, **kwargs)
        with _lock:
            _cache[key] = (time.time(), value)
        return copy.deepcopy(value)

    return wrapper

# Full exhibit: completed AND its exhibit explicitly published.
PUBLIC_PROJECT_WHERE = "p.status = 'completed' AND p.exhibit_published = 1"
# Teaser: in progress and allowed on the site -> ONLY title, category and an "In progress" badge.
TEASER_WHERE = "p.status = 'in_progress' AND p.is_public = 1"
TEASER_FIELDS = "p.id, p.slug, p.name, p.category, p.status, p.is_featured, p.created_at"


def _attach(rows):
    if not rows:
        return rows
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    techs, links = {}, {}
    trows, lrows = db.many([
        (f"SELECT project_id, name FROM project_technologies WHERE project_id IN ({marks}) ORDER BY sort_order", ids),
        (f"SELECT project_id, label, url FROM project_links WHERE project_id IN ({marks}) ORDER BY sort_order", ids),
    ])
    for t in trows:
        techs.setdefault(t["project_id"], []).append(t["name"])
    for l in lrows:
        links.setdefault(l["project_id"], []).append({"label": l["label"], "url": l["url"]})
    for r in rows:
        r["technologies"] = techs.get(r["id"], [])
        r["links"] = links.get(r["id"], [])
        r["tags"] = jloads(r.get("tags"), [])
        r["gallery"] = jloads(r.get("gallery"), [])
        r["teaser"] = False
    return rows


def _teaser(r):
    """Only what is intentionally public for an in-progress project."""
    return {"id": r["id"], "slug": r["slug"], "name": r["name"], "category": r["category"] or "", "status": "in_progress",
            "is_featured": 0, "teaser": True, "tagline": "", "description": "", "technologies": [], "tags": [],
            "cover_image": "", "gallery": [], "links": [], "github_url": "", "live_url": "", "youtube_url": "",
            "start_date": None, "completed_date": None, "created_at": r["created_at"]}


@cached
def projects(featured_only=False, limit=200):
    sql = f"SELECT p.* FROM projects p WHERE {PUBLIC_PROJECT_WHERE}"
    if featured_only:
        sql += " AND p.is_featured=1"
    sql += " ORDER BY p.is_featured DESC, p.sort_order, COALESCE(p.completed_date, p.start_date, p.created_at) DESC LIMIT ?"
    return _attach(db.query(sql, (limit,)))


@cached
def in_progress(limit=50):
    return [_teaser(r) for r in db.query(
        f"SELECT {TEASER_FIELDS} FROM projects p WHERE {TEASER_WHERE} ORDER BY p.updated_at DESC LIMIT ?", (limit,))]


@cached
def project(slug):
    rows = _attach(db.query(f"SELECT p.* FROM projects p WHERE p.slug=? AND {PUBLIC_PROJECT_WHERE}", (slug,)))
    return rows[0] if rows else None


@cached
def teaser(slug):
    r = db.one(f"SELECT {TEASER_FIELDS} FROM projects p WHERE p.slug=? AND {TEASER_WHERE}", (slug,))
    return _teaser(r) if r else None


def journals(project_id, limit=50):
    return []  # project journals are private by design; never served publicly


def all_public_journals(limit=200):
    return []


def milestones(project_id):
    return []  # internal planning data stays private


@cached
def stats():
    rows, trows, prog = db.many([
        (f"SELECT COUNT(*) AS total FROM projects p WHERE {PUBLIC_PROJECT_WHERE}", ()),
        (f"SELECT COUNT(DISTINCT t.name) AS n FROM project_technologies t JOIN projects p ON p.id=t.project_id "
         f"WHERE {PUBLIC_PROJECT_WHERE}", ()),
        (f"SELECT COUNT(*) AS n FROM projects p WHERE {TEASER_WHERE}", ()),
    ])
    done, ip = int(rows[0]["total"] or 0), int(prog[0]["n"] or 0)
    return {"projects": done + ip, "completed": done, "active": ip, "in_progress": ip,
            "technologies": int(trows[0]["n"] or 0), "entries": 0}


@cached
def technologies():
    return db.query(
        "SELECT t.name, COUNT(DISTINCT t.project_id) AS n FROM project_technologies t JOIN projects p "
        f"ON p.id=t.project_id WHERE {PUBLIC_PROJECT_WHERE} GROUP BY t.name ORDER BY n DESC, t.name LIMIT 40")
