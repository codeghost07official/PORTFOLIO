"""Keeps `doc_chunks` in sync with workspace data.

Every write in the services layer calls `schedule(kind, id)`, which rebuilds the
chunks for that one record (cheap, synchronous). Embeddings are computed in a
background thread and lazily at query time, re-using vectors whose content
hash did not change, so the Gemini embedding quota is barely touched.
"""
import base64
import hashlib
import logging
import queue
import struct
import threading

from ..db import db
from ..utils import jloads, now_iso
from .chunking import chunk_text

log = logging.getLogger("astra.rag")
_app = None
_embed_lock = threading.Lock()

KINDS = ["project", "task", "milestone", "journal", "note", "resource", "bug", "idea", "snippet", "conversation",
         "todo", "diary"]


def init(app):
    global _app
    _app = app


# ---------------------------------------------------------------------------
# Vector encoding (float16, base64) - ~2 KB per 768-d vector
# ---------------------------------------------------------------------------
def pack_vector(vec):
    return "f16:" + base64.b64encode(struct.pack(f"<{len(vec)}e", *vec)).decode()


def unpack_vector(text):
    if not text or not text.startswith("f16:"):
        return None
    raw = base64.b64decode(text[4:])
    return list(struct.unpack(f"<{len(raw) // 2}e", raw))


def bump_version():
    db.execute(
        "INSERT INTO meta(key, value) VALUES('index_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now_iso() + str(threading.get_ident() % 997),))


# ---------------------------------------------------------------------------
# Document builders: (title, body, project_id, parent_id, date)
# ---------------------------------------------------------------------------
def _project_name(pid):
    if not pid:
        return "no project"
    return db.scalar("SELECT name FROM projects WHERE id=?", (pid,), default="unknown project")


def _build(kind, rid):
    if kind == "project":
        p = db.one("SELECT * FROM projects WHERE id=?", (rid,))
        if not p:
            return []
        techs = ", ".join(r["name"] for r in db.query(
            "SELECT name FROM project_technologies WHERE project_id=? ORDER BY sort_order", (rid,)))
        head = (f"Project “{p['name']}” (id {p['id']}) — status {p['status']}, priority {p['priority']}, "
                f"category {p['category'] or 'n/a'}. Tagline: {p['tagline']}. Technologies: {techs or 'n/a'}. "
                f"Started {p['start_date'] or 'n/a'}, target {p['target_date'] or 'n/a'}. "
                f"Next action: {p['next_action'] or 'n/a'}. Tags: {', '.join(jloads(p['tags'], []))}.")
        sections = [("Overview", p["description"]), ("Objective", p["objective"]), ("Problem", p["problem"]),
                    ("Motivation", p["motivation"]), ("Features", p["features"]),
                    ("Architecture", p["architecture"]), ("Challenges", p["challenges"]),
                    ("Future", p["future"]), ("Achievements", p["achievements"]),
                    ("Documentation", p["documentation"])]
        body = head + "\n\n" + "\n\n".join(f"## {t}\n{v}" for t, v in sections if (v or "").strip())
        return [(f"Project: {p['name']}", body, rid, None, p["updated_at"])]
    if kind == "task":
        t = db.one("SELECT * FROM tasks WHERE id=?", (rid,))
        if not t:
            return []
        body = (f"Task #{t['id']} “{t['title']}” in project {_project_name(t['project_id'])} — status {t['status']}, "
                f"priority {t['priority']}, due {t['due_date'] or 'none'}, created {t['created_at'][:10]}"
                f"{', completed ' + t['completed_at'][:10] if t['completed_at'] else ''}.\n"
                f"{t['description'] or ''}\n{('Notes: ' + t['notes']) if t['notes'] else ''}")
        return [(f"Task: {t['title']}", body, t["project_id"], None, t["updated_at"])]
    if kind == "milestone":
        m = db.one("SELECT * FROM milestones WHERE id=?", (rid,))
        if not m:
            return []
        body = (f"Milestone #{m['id']} “{m['title']}” for project {_project_name(m['project_id'])} — status "
                f"{m['status']}, target {m['target_date'] or 'n/a'}.\n{m['description'] or ''}")
        return [(f"Milestone: {m['title']}", body, m["project_id"], None, m["updated_at"])]
    if kind == "journal":
        j = db.one("SELECT * FROM journals WHERE id=?", (rid,))
        if not j:
            return []
        head = (f"Journal entry #{j['id']} “{j['title']}” ({j['entry_date']}, project "
                f"{_project_name(j['project_id'])}, {j['status']}, {j['visibility']}). "
                f"Tags: {', '.join(jloads(j['tags'], []))}.")
        return [(f"Journal: {j['title']} ({j['entry_date']})", head + "\n" + c, j["project_id"], None,
                 j["entry_date"]) for c in (chunk_text(j["content"]) or [""])]
    if kind == "note":
        n = db.one("SELECT * FROM notes WHERE id=?", (rid,))
        if not n:
            return []
        head = f"Note #{n['id']} [{n['category']}] “{n['title'] or 'untitled'}” (project {_project_name(n['project_id'])})."
        return [(f"Note: {n['title'] or n['category']}", head + "\n" + c, n["project_id"], None, n["updated_at"])
                for c in (chunk_text(n["content"]) or [""])]
    if kind == "resource":
        r = db.one("SELECT * FROM resources WHERE id=?", (rid,))
        if not r:
            return []
        body = (f"Resource #{r['id']} [{r['category']}] “{r['title']}” {r['url']} "
                f"(project {_project_name(r['project_id'])}).\n{r['description'] or ''}")
        return [(f"Resource: {r['title']}", body, r["project_id"], None, r["updated_at"])]
    if kind == "bug":
        b = db.one("SELECT * FROM bugs WHERE id=?", (rid,))
        if not b:
            return []
        body = (f"Bug #{b['id']} “{b['title']}” in project {_project_name(b['project_id'])} — severity {b['severity']}, "
                f"status {b['status']}, reported {b['reported_at']}"
                f"{', resolved ' + b['resolved_at'][:10] if b['resolved_at'] else ''}.\n"
                f"Description: {b['description'] or 'n/a'}\nSolution: {b['solution'] or 'not solved yet'}")
        return [(f"Bug: {b['title']}", c, b["project_id"], None, b["updated_at"]) for c in chunk_text(body, 1400)]
    if kind == "idea":
        i = db.one("SELECT * FROM ideas WHERE id=?", (rid,))
        if not i:
            return []
        body = (f"Idea #{i['id']} “{i['name']}” — status {i['status']}, priority {i['priority']}, category "
                f"{i['category'] or 'n/a'}, tags {', '.join(jloads(i['tags'], []))}, captured {i['created_at'][:10]}.\n"
                f"{i['description'] or ''}")
        return [(f"Idea: {i['name']}", body, i["project_id"], None, i["updated_at"])]
    if kind == "snippet":
        s = db.one("SELECT * FROM snippets WHERE id=?", (rid,))
        if not s:
            return []
        body = (f"Code snippet #{s['id']} “{s['title']}” ({s['language']}). {s['description'] or ''}\n"
                f"```{s['language']}\n{(s['code'] or '')[:1500]}\n```")
        return [(f"Snippet: {s['title']}", body, None, None, s["updated_at"])]
    if kind == "todo":
        t = db.one("SELECT * FROM todos WHERE id=?", (rid,))
        if not t:
            return []
        body = (f"Personal task “{t['title']}” — {'completed ' + t['completed_at'][:10] if t['completed_at'] else 'open'}"
                f", priority {t['priority'] or 'none'}, due {t['due_date'] or 'no date'}, created {t['created_at'][:10]}."
                f"\n{t['description'] or ''}")
        return [(f"Task: {t['title']}", body, None, None, t["updated_at"])]
    if kind == "diary":
        e = db.one("SELECT * FROM diary_entries WHERE id=?", (rid,))
        if not e or not (e["content"] or "").strip():
            return []
        head = f"Personal journal entry ({e['entry_date']}){': ' + e['title'] if e['title'] else ''}."
        return [(f"Diary: {e['entry_date']} {e['title'] or ''}".strip(), head + "\n" + c, None, None, e["entry_date"])
                for c in chunk_text(e["content"])]
    if kind == "conversation":  # rid = assistant message id; pairs with the preceding user message
        a = db.one("SELECT m.*, c.title AS conv_title, c.project_id AS conv_project FROM ai_messages m "
                   "JOIN ai_conversations c ON c.id=m.conversation_id WHERE m.id=?", (rid,))
        if not a or a["role"] != "assistant":
            return []
        u = db.one("SELECT content FROM ai_messages WHERE conversation_id=? AND id<? AND role='user' "
                   "ORDER BY id DESC LIMIT 1", (a["conversation_id"], rid))
        body = (f"Past conversation “{a['conv_title']}” on {a['created_at'][:10]}.\n"
                f"Sir said: {(u or {}).get('content', '')[:1500]}\nAssistant replied: {a['content'][:2500]}")
        return [(f"Conversation: {a['conv_title']} ({a['created_at'][:10]})", c, a["conv_project"],
                 a["conversation_id"], a["created_at"]) for c in chunk_text(body, 1400)]
    return []


def reindex(kind, rid):
    rid = int(rid)
    docs = _build(kind, rid)
    old = {r["content_hash"]: r["embedding"] for r in db.query(
        "SELECT content_hash, embedding FROM doc_chunks WHERE source_type=? AND source_id=?", (kind, rid))}
    ts = now_iso()
    stmts = [("DELETE FROM doc_chunks WHERE source_type=? AND source_id=?", (kind, rid))]
    for i, (title, body, pid, parent, sdate) in enumerate(docs):
        h = hashlib.sha1((title + "\n" + body).encode()).hexdigest()
        stmts.append((
            "INSERT INTO doc_chunks(source_type, source_id, project_id, parent_id, chunk_index, title, content,"
            " content_hash, embedding, source_date, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (kind, rid, pid, parent, i, title[:200], body, h, old.get(h), sdate, ts)))
    db.batch(stmts)
    bump_version()
    return len(docs)


_queue = queue.Queue()
_worker = {"thread": None}


def _work():
    while True:
        kind, rid = _queue.get()
        try:
            reindex(kind, rid)
        except Exception:
            log.exception("Indexing %s %s failed", kind, rid)
        finally:
            _queue.task_done()
        if _queue.empty():
            embed_async()


def schedule(kind, rid):
    """Queue a record for re-indexing on a background thread, so saves stay fast
    even when the database is a remote round trip away."""
    if _app is None:  # no app (scripts/tests): index inline
        try:
            reindex(kind, rid)
        except Exception:
            log.exception("Indexing %s %s failed", kind, rid)
        return
    if _worker["thread"] is None or not _worker["thread"].is_alive():
        _worker["thread"] = threading.Thread(target=_work, name="astra-indexer", daemon=True)
        _worker["thread"].start()
    _queue.put((kind, int(rid)))


def flush(timeout=30):
    """Wait until queued indexing work is done (used before retrieval-sensitive operations/tests)."""
    import time

    end = time.time() + timeout
    while _queue.unfinished_tasks and time.time() < end:
        time.sleep(0.05)


def remove(kind, rid):
    try:
        db.execute("DELETE FROM doc_chunks WHERE source_type=? AND source_id=?", (kind, int(rid)))
        bump_version()
    except Exception:
        log.exception("Removing chunks failed")


def schedule_project_children(pid):
    for kind, table in (("task", "tasks"), ("milestone", "milestones")):
        for r in db.query(f"SELECT id FROM {table} WHERE project_id=?", (pid,)):
            schedule(kind, r["id"])


def rebuild_all():
    tables = {"project": "projects", "task": "tasks", "milestone": "milestones", "journal": "journals",
              "note": "notes", "resource": "resources", "bug": "bugs", "idea": "ideas", "snippet": "snippets",
              "todo": "todos", "diary": "diary_entries"}
    total = 0
    db.execute("DELETE FROM doc_chunks WHERE source_type NOT IN (" + ",".join("?" * len(KINDS)) + ")", KINDS)
    for kind, table in tables.items():
        ids = [r["id"] for r in db.query(f"SELECT id FROM {table}")]
        existing = {r["source_id"] for r in db.query("SELECT DISTINCT source_id FROM doc_chunks WHERE source_type=?",
                                                       (kind,))}
        for stale in existing - set(ids):
            db.execute("DELETE FROM doc_chunks WHERE source_type=? AND source_id=?", (kind, stale))
        for rid in ids:
            total += reindex(kind, rid)
    for r in db.query("SELECT id FROM ai_messages WHERE role='assistant'"):
        total += reindex("conversation", r["id"])
    embed_async()
    return total


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
def embed_pending(limit=96):
    """Embed chunks that have no vector yet. Needs an app context."""
    from ..ai import gemini

    if not gemini.embeddings_enabled():
        return 0
    if not _embed_lock.acquire(blocking=False):
        return 0
    try:
        rows = db.query("SELECT id, title, content FROM doc_chunks WHERE embedding IS NULL ORDER BY id DESC LIMIT ?",
                        (int(limit),))
        if not rows:
            return 0
        vectors = gemini.embed([f"{r['title']}\n{r['content']}" for r in rows], "RETRIEVAL_DOCUMENT")
        db.batch([("UPDATE doc_chunks SET embedding=? WHERE id=?", (pack_vector(v), r["id"]))
                  for r, v in zip(rows, vectors) if v])
        bump_version()
        return len(vectors)
    except Exception as exc:
        log.warning("Embedding batch failed: %s", exc)
        return 0
    finally:
        _embed_lock.release()


def embed_async():
    if _app is None or not _app.config.get("GEMINI_API_KEY") or _app.config.get("EMBEDDINGS_PROVIDER") != "gemini":
        return

    def run():
        with _app.app_context():
            embed_pending()

    threading.Thread(target=run, daemon=True).start()


def stats():
    return {
        "chunks": db.scalar("SELECT COUNT(*) FROM doc_chunks", default=0),
        "embedded": db.scalar("SELECT COUNT(*) FROM doc_chunks WHERE embedding IS NOT NULL", default=0),
        "by_type": db.query("SELECT source_type, COUNT(*) AS n FROM doc_chunks GROUP BY source_type ORDER BY n DESC"),
    }
