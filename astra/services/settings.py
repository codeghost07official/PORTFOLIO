"""Key/value settings stored as JSON in the `settings` table.

Secrets are never stored here - they stay in environment variables.
"""
import copy
import time

from ..db import db
from ..utils import ValidationError, clean_url, jdumps, jloads, now_iso

DEFAULTS = {
    "profile": {
        "name": "Jai Verma",
        "title": "Curious by nature · Builder by choice · Creator of ASTRA",
        "intro": (
            "I like figuring out how things work, then building my own version to find out what I missed. "
            "ASTRA is where my software work lives."
        ),
        "about": (
            "I'm **Jai Verma**. I'm not just a software developer. I'm someone who can't leave a question alone. "
            "When something catches my attention, I want to know how it works, why it works that way, and "
            "whether I can build it myself.\n\n"
            "That curiosity isn't limited to code. I'm interested in making all kinds of things, and I learn best "
            "by experimenting, breaking things, and sticking with a problem until it gives in.\n\n"
            "**ASTRA** is the part of that story that's about software. It's my platform for the projects I build, "
            "the skills I'm sharpening, the experiments I run, and the notes I keep along the way. Everything "
            "here is real work, documented as it happens."
        ),
        "avatar": "",
        "location": "",
        "email": "codeghost07.official@gmail.com",
        "email2": "vermajai.official@gmail.com",
        "phone": "+91 8920279457",
        "github": "https://github.com/codeghost07official",
        "youtube": "",
        "linkedin": "",
        "twitter": "",
        "website": "",
        "interests": ["Understanding how things work", "Building things, software and beyond",
                      "Experimenting and learning by doing", "Software development"],
        "skills": [
            {"group": "Languages", "items": ["Python", "JavaScript", "HTML/CSS", "SQL"]},
            {"group": "Backend", "items": ["Flask", "REST APIs", "Turso / libSQL"]},
            {"group": "AI", "items": ["Gemini API", "Retrieval-augmented generation (RAG)"]},
            {"group": "Tools", "items": ["Git", "GitHub"]},
        ],
        "achievements": [
            {"title": "Built ASTRA", "detail": "Designed and developed this portfolio and private project workspace.",
             "date": ""},
        ],
        "journey": [
            {"year": "Now", "title": "Building ASTRA", "detail": "A home for my software projects, experiments and notes."},
        ],
        "footer_note": "Designed & built by Jai Verma.",
    },
    "appearance": {
        "accent": "cyan",          # cyan | blue | violet | emerald | amber
        "effects": "full",         # full | lite | off
        "hero_kicker": "PERSONAL SYSTEMS EXHIBITION",
    },
    "visibility": {
        "show_skills": True, "show_journey": True, "show_achievements": True,
        "show_interests": True, "show_contact": True, "show_chatbot": True,
    },
    "chatbot": {
        "public_enabled": True,
        "public_greeting": "Hello — I'm the ASTRA guide. Ask me about any project, technology, or where to start.",
        "public_temperature": 0.5,
        "private_temperature": 0.6,
        "public_model": "",
        "private_model": "",
        "public_daily_limit": 0,   # 0 = use env PUBLIC_CHAT_GLOBAL_DAY
        "assistant_name": "ASTRA",
    },
    "login": {"entry_point": "footer_glyph"},  # footer_glyph | logo_dblclick | keyboard | none
    "defaults": {"status": "in_progress", "priority": "medium", "is_public": False, "show_journal": False},
    "dashboard": {
        "widgets": ["focus", "stats", "progress", "charts", "deadlines", "activity", "journals", "bugs"],
    },
    "finance": {
        "currency": "₹",
        "expense_categories": ["Food", "Transport", "Bills", "Shopping", "Health", "Education", "Entertainment",
                               "Subscriptions", "Rent", "Other"],
        "income_categories": ["Salary", "Freelance", "Gift", "Refund", "Other"],
    },
    "assistant": {
        "name": "ASTRA",
        "personality": ("Calm, intelligent and quietly witty, in the spirit of a classic AI butler. Efficient, "
                        "respectful and natural. Never robotic, never over-enthusiastic."),
        "about_me": "",
        "instructions": "",
        "max_sentences": 2,
        "model": "",
        "temperature": 0.6,
        "context": {"projects": True, "project_journals": True, "tasks": True, "diary": False,
                    "medicines": False, "expenses": False, "conversations": True, "memory": True},
        "voice": {"enabled": True, "autospeak": True, "voice_name": "", "lang": "en-GB", "rate": 1.0,
                  "pitch": 1.0, "volume": 1.0},
    },
}

ACCENTS = {"cyan", "blue", "violet", "emerald", "amber"}
ENTRY_POINTS = {"footer_glyph", "logo_dblclick", "keyboard", "none"}
_cache = {"at": 0.0, "data": None}


def _merge(default, stored):
    if isinstance(default, dict) and isinstance(stored, dict):
        out = copy.deepcopy(default)
        for k, v in stored.items():
            out[k] = _merge(default.get(k), v) if k in default else v
        return out
    return stored if stored is not None else copy.deepcopy(default)


def all_settings(fresh=False):
    if not fresh and _cache["data"] is not None and time.time() - _cache["at"] < 20:
        return copy.deepcopy(_cache["data"])
    stored = {r["key"]: jloads(r["value"], {}) for r in db.query("SELECT key, value FROM settings")}
    data = {k: _merge(v, stored.get(k)) for k, v in DEFAULTS.items()}
    _cache.update(at=time.time(), data=data)
    return copy.deepcopy(data)


def get(key):
    return all_settings()[key]


def _validate(key, value):
    if key not in DEFAULTS:
        raise ValidationError({"key": "unknown settings group"})
    if not isinstance(value, dict):
        raise ValidationError({key: "must be an object"})
    merged = _merge(DEFAULTS[key], {k: v for k, v in value.items() if k in DEFAULTS[key]})
    if key == "profile":
        for f in ("avatar", "github", "youtube", "linkedin", "twitter", "website"):
            merged[f] = clean_url(merged.get(f), f)
        for f in ("name", "title", "location", "email", "email2"):
            merged[f] = str(merged.get(f) or "")[:200]
        # phone: keep only characters that belong in a phone number
        merged["phone"] = "".join(ch for ch in str(merged.get("phone") or "") if ch.isdigit() or ch in "+ -()")[:30].strip()
        merged["intro"] = str(merged.get("intro") or "")[:1000]
        merged["about"] = str(merged.get("about") or "")[:20000]
        merged["interests"] = [str(i)[:60] for i in merged.get("interests") or [] if str(i).strip()][:20]
        merged["skills"] = [
            {"group": str(s.get("group", ""))[:60], "items": [str(i)[:60] for i in s.get("items", [])][:30]}
            for s in merged.get("skills") or [] if isinstance(s, dict)
        ][:12]
        merged["achievements"] = [
            {k: str(a.get(k, ""))[:400] for k in ("title", "detail", "date")}
            for a in merged.get("achievements") or [] if isinstance(a, dict)
        ][:30]
        merged["journey"] = [
            {k: str(j.get(k, ""))[:400] for k in ("year", "title", "detail")}
            for j in merged.get("journey") or [] if isinstance(j, dict)
        ][:30]
    if key == "appearance" and merged.get("accent") not in ACCENTS:
        merged["accent"] = "cyan"
    if key == "appearance" and merged.get("effects") not in ("full", "lite", "off"):
        merged["effects"] = "full"
    if key == "login" and merged.get("entry_point") not in ENTRY_POINTS:
        raise ValidationError({"entry_point": "invalid entry point"})
    if key == "chatbot":
        for t in ("public_temperature", "private_temperature"):
            try:
                merged[t] = max(0.0, min(1.5, float(merged[t])))
            except (TypeError, ValueError):
                merged[t] = DEFAULTS["chatbot"][t]
        for m in ("public_model", "private_model"):
            merged[m] = "".join(ch for ch in str(merged.get(m) or "") if ch.isalnum() or ch in "-._")[:80]
        merged["public_daily_limit"] = max(0, int(merged.get("public_daily_limit") or 0))
        merged["public_enabled"] = bool(merged.get("public_enabled"))
        merged["assistant_name"] = str(merged.get("assistant_name") or "ASTRA")[:40]
        merged["public_greeting"] = str(merged.get("public_greeting") or "")[:400]
    if key == "visibility":
        merged = {k: bool(v) for k, v in merged.items()}
    if key == "dashboard":
        allowed = DEFAULTS["dashboard"]["widgets"]
        merged["widgets"] = [w for w in merged.get("widgets", []) if w in allowed]
    if key == "finance":
        merged["currency"] = str(merged.get("currency") or "₹")[:4]
        for k in ("expense_categories", "income_categories"):
            seen = []
            for c in merged.get(k) or []:
                c = str(c).strip()[:60]
                if c and c not in seen:
                    seen.append(c)
            merged[k] = seen[:60] or ["Other"]
    if key == "assistant":
        merged["name"] = str(merged.get("name") or "ASTRA").strip()[:40] or "ASTRA"
        for f, n in (("personality", 2000), ("about_me", 8000), ("instructions", 8000)):
            merged[f] = str(merged.get(f) or "")[:n]
        try:
            merged["max_sentences"] = max(1, min(8, int(merged.get("max_sentences") or 2)))
            merged["temperature"] = max(0.0, min(1.5, float(merged.get("temperature"))))
        except (TypeError, ValueError):
            raise ValidationError({"assistant": "invalid number"})
        merged["model"] = "".join(ch for ch in str(merged.get("model") or "") if ch.isalnum() or ch in "-._")[:80]
        merged["context"] = {k: bool(merged["context"].get(k)) for k in DEFAULTS["assistant"]["context"]}
        v = merged["voice"]
        merged["voice"] = {
            "enabled": bool(v.get("enabled")), "autospeak": bool(v.get("autospeak")),
            "voice_name": str(v.get("voice_name") or "")[:120], "lang": str(v.get("lang") or "en-GB")[:12],
            "rate": max(0.5, min(2.0, float(v.get("rate") or 1))), "pitch": max(0.0, min(2.0, float(v.get("pitch") or 1))),
            "volume": max(0.0, min(1.0, float(v.get("volume") if v.get("volume") is not None else 1))),
        }
    return merged


def save(key, value):
    merged = _validate(key, value)
    db.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, jdumps(merged), now_iso()),
    )
    _cache["data"] = None
    if key == "profile":
        from ..rag import indexer

        indexer.bump_version()
    return merged
