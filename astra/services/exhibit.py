"""Exhibit Management: what the public exhibition shows for a project.

* The DRAFT lives in `project_exhibits.draft` (JSON) and is never public.
* PUBLISH copies the draft into the project's live columns and sets
  `exhibit_published=1`. The public site shows full details only when the
  project is `completed` AND its exhibit is published (see public_data).
* GENERATE asks Gemini to write the draft from the project's private journal.
  The result only ever lands in the draft, for review.
"""
import json
import logging
import re

from ..db import db
from ..utils import ValidationError, clean_tags, clean_url, jdumps, jloads, now_iso, truncate
from . import projects as projects_svc

log = logging.getLogger("astra.exhibit")

# key -> (label, kind, hint). Keys match project columns (except links handled via projects service).
FIELDS = [
    ("name", "Project title", "str", ""),
    ("tagline", "Short description", "str", "One line shown on cards."),
    ("category", "Category", "str", ""),
    ("technologies", "Technologies used", "tags", "Comma separated."),
    ("description", "Detailed overview", "md", ""),
    ("problem", "Problem / purpose", "md", ""),
    ("features", "Features", "md", ""),
    ("architecture", "How it works", "md", ""),
    ("process", "Development process", "md", ""),
    ("challenges", "Challenges faced", "md", ""),
    ("solutions", "Solutions implemented", "md", ""),
    ("learnings", "What I learned", "md", ""),
    ("achievements", "Outcomes", "md", ""),
    ("future", "Future improvements", "md", ""),
    ("cover_image", "Cover image URL", "url", ""),
    ("gallery", "Screenshots (one URL per line)", "urls", ""),
    ("github_url", "GitHub repository", "url", ""),
    ("live_url", "Live deployment", "url", ""),
    ("youtube_url", "Video / demo link", "url", ""),
    ("links", "Other links (Label | URL per line)", "links", ""),
]
KEYS = [f[0] for f in FIELDS]
GENERATED_KEYS = ["name", "tagline", "category", "technologies", "description", "problem", "features",
                  "architecture", "process", "challenges", "solutions", "learnings", "achievements", "future"]


def _from_project(p):
    return {k: p.get(k) if k in p else "" for k in KEYS}


def _clean(data):
    out = {}
    for key, label, kind, _ in FIELDS:
        if key not in data:
            continue
        v = data[key]
        if kind == "tags":
            out[key] = clean_tags(v)
        elif kind == "url":
            out[key] = clean_url(v, key)
        elif kind == "urls":
            items = v.splitlines() if isinstance(v, str) else (v or [])
            out[key] = [clean_url(x.strip(), key) for x in items if x and str(x).strip()][:30]
        elif kind == "links":
            rows = v.splitlines() if isinstance(v, str) else (v or [])
            links = []
            for row in rows:
                if isinstance(row, dict):
                    lab, url = row.get("label", ""), row.get("url", "")
                else:
                    lab, _, url = str(row).partition("|")
                    if not url:
                        lab, url = "", lab
                url = clean_url(url.strip(), key)
                if url:
                    links.append({"label": (lab.strip() or url)[:80], "url": url})
            out[key] = links[:20]
        else:
            v = "" if v is None else str(v)
            limit = 240 if key == "tagline" else 160 if key in ("name", "category") else 100000
            if len(v) > limit:
                raise ValidationError({key: f"max {limit} characters"})
            out[key] = v.strip() if kind == "str" else v
    if "name" in out and not out["name"]:
        raise ValidationError({"name": "required"})
    return out


def get(pid):
    p = projects_svc.get_project(pid)
    if not p:
        return None
    row = db.one("SELECT * FROM project_exhibits WHERE project_id=?", (int(pid),))
    draft = jloads(row["draft"], {}) if row else {}
    if not draft:
        draft = _from_project(p)
    live = _from_project(p)
    return {
        "project": {"id": p["id"], "name": p["name"], "slug": p["slug"], "status": p["status"],
                    "exhibit_published": bool(p["exhibit_published"]), "is_public": bool(p["is_public"])},
        "draft": {k: draft.get(k, live.get(k)) for k in KEYS},
        "fields": [{"key": k, "label": lab, "kind": kind, "hint": hint} for k, lab, kind, hint in FIELDS],
        "generated_at": row["generated_at"] if row else None,
        "published_at": row["published_at"] if row else None,
        "draft_differs": bool(row) and any(draft.get(k) != live.get(k) for k in KEYS),
        "journal_entries": int(db.scalar("SELECT COUNT(*) FROM journals WHERE project_id=?", (int(pid),), default=0)),
    }


def save_draft(pid, data, generated=False):
    if not projects_svc.get_project(pid):
        return None
    current = get(pid)["draft"]
    current.update(_clean(data))
    ts = now_iso()
    db.execute(
        "INSERT INTO project_exhibits(project_id, draft, generated_at, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(project_id) DO UPDATE SET draft=excluded.draft, updated_at=excluded.updated_at"
        + (", generated_at=excluded.generated_at" if generated else ""),
        (int(pid), jdumps(current), ts if generated else None, ts))
    return get(pid)


def publish(pid, data=None):
    if data:
        save_draft(pid, data)
    ex = get(pid)
    if not ex:
        return None
    payload = dict(ex["draft"])
    payload.update(exhibit_published=True, is_public=True)
    projects_svc.update_project(pid, payload)
    db.execute("UPDATE project_exhibits SET published_at=? WHERE project_id=?", (now_iso(), int(pid)))
    return get(pid)


def unpublish(pid):
    projects_svc.update_project(pid, {"exhibit_published": False})
    return get(pid)


def discard_draft(pid):
    db.execute("DELETE FROM project_exhibits WHERE project_id=?", (int(pid),))
    return get(pid)


# ---------------------------------------------------------------------------
# Gemini generation from the private project journal
# ---------------------------------------------------------------------------
GEN_SYSTEM = """You are a meticulous technical writer documenting a software project for its creator's public
portfolio exhibition. You receive the project's PRIVATE development journal (chronological) and its current
metadata. Read EVERYTHING first, understand how the project actually evolved, then write the exhibition fields.

Strict rules:
- Use ONLY facts present in the journal and metadata. Never invent features, technologies, metrics, users,
  achievements or results. If the material doesn't support a field, return "" for it and list the field in
  "needs_input".
- Write like authentic technical documentation: specific, concrete, first-person-neutral, no hype, no filler
  phrases ("cutting-edge", "seamless", "robust solution", "in today's world").
- Preserve technical details exactly (names of libraries, APIs, algorithms, errors, decisions).
- Use Markdown inside long fields (short paragraphs, bullet lists, `code`). Keep "tagline" under 140 characters.
- "process" should follow the chronology of the journal. "challenges" and "solutions" must correspond.
- Never copy private personal details unrelated to the project.

Return ONLY a JSON object with these keys:
name, tagline, category, technologies (array of strings), description, problem, features, architecture,
process, challenges, solutions, learnings, achievements, future, needs_input (array of field keys)."""


def generate(pid):
    from ..ai import gemini

    p = projects_svc.get_project(pid)
    if not p:
        return None
    entries = db.query("SELECT title, entry_date, content, tags FROM journals WHERE project_id=? "
                       "ORDER BY entry_date, id", (int(pid),))
    if not entries:
        raise ValidationError({"journal": "This project has no journal entries yet. Write some first."})
    budget, parts = 150000, []
    for e in entries:
        block = f"### {e['entry_date']} — {e['title']}\nTags: {', '.join(jloads(e['tags'], []))}\n{truncate(e['content'], 20000)}"
        budget -= len(block)
        if budget < 0:
            parts.append("(older entries omitted for length)")
            break
        parts.append(block)
    current = get(pid)["draft"]
    meta = {k: current.get(k) for k in GENERATED_KEYS}
    prompt = (f"PROJECT METADATA (may be incomplete):\n{json.dumps(meta, ensure_ascii=False)[:8000]}\n\n"
              f"INTERNAL STATUS: {p['status']}\n\nDEVELOPMENT JOURNAL ({len(entries)} entries, oldest first):\n\n"
              + "\n\n".join(parts))
    contents = [{"role": "user", "text": prompt}]
    text, model = gemini.generate(GEN_SYSTEM, contents, temperature=0.3, max_tokens=16384, json_mode=True, timeout=120)
    try:
        data = _parse_json(text)
    except ValidationError:
        log.warning("Exhibit JSON unparsable from %s (%d chars): %r … %r", model, len(text), text[:160], text[-160:])
        contents += [{"role": "model", "text": text[:4000]},
                     {"role": "user", "text": "That was not valid JSON. Return ONLY the complete JSON object with the "
                                              "required keys, no prose and no code fences. Keep long fields concise."}]
        text, model = gemini.generate(GEN_SYSTEM, contents, temperature=0.2, max_tokens=16384, json_mode=True, timeout=120)
        data = _parse_json(text)
    generated = {}
    for k in GENERATED_KEYS:
        v = data.get(k)
        if k == "technologies":
            v = [str(x) for x in v] if isinstance(v, list) else clean_tags(v or "")
            if v:
                generated[k] = v
        elif isinstance(v, str) and v.strip():
            generated[k] = v.strip()
    if not generated.get("name"):
        generated.pop("name", None)
    ex = save_draft(pid, generated, generated=True)
    needs = [n for n in (data.get("needs_input") or []) if n in KEYS]
    return {"exhibit": ex, "needs_input": needs, "model": model, "entries_used": len(entries)}


def _parse_json(text):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = t.find("{")
    if start < 0:
        raise ValidationError({"ai": "Gemini did not return structured content. Try regenerating."})
    try:
        obj, _ = json.JSONDecoder().raw_decode(t[start:])  # tolerates trailing text after the object
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    raise ValidationError({"ai": "Gemini returned malformed content (often a temporary model overload). Try regenerating."})
