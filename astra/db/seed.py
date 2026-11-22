"""Initial data: built-in project templates (always) and one removable sample
project (only on a brand-new database when SEED_SAMPLE_DATA is true)."""
import logging

from .core import db
from ..utils import jdumps, now_iso, today_iso

log = logging.getLogger("astra.db")

BUILTIN_TEMPLATES = [
    {
        "key": "web-app", "name": "Web application", "category": "Web",
        "description": "Full-stack web app: planning, backend, frontend, deployment.",
        "technologies": ["Python", "Flask", "JavaScript", "HTML", "CSS"],
        "tasks": ["Define scope and user flows", "Design data model", "Set up repository and environment",
                  "Implement backend API", "Build frontend layout", "Authentication & security review",
                  "Write README", "Deploy to staging", "Performance & accessibility pass", "Launch"],
        "milestones": [{"title": "Architecture ready", "offset_days": 7}, {"title": "MVP functional", "offset_days": 30},
                       {"title": "Public launch", "offset_days": 45}],
    },
    {
        "key": "python-app", "name": "Python application", "category": "Python",
        "description": "CLI / desktop / automation tool written in Python.",
        "technologies": ["Python"],
        "tasks": ["Write problem statement", "Create virtual environment & packaging", "Implement core module",
                  "Add configuration handling", "Add logging & error handling", "Write tests",
                  "Write usage documentation", "Package and release"],
        "milestones": [{"title": "Core works end-to-end", "offset_days": 14}, {"title": "v1.0 release", "offset_days": 30}],
    },
    {
        "key": "ai-ml", "name": "AI / ML project", "category": "AI/ML",
        "description": "Data → model → evaluation → deployment workflow.",
        "technologies": ["Python", "NumPy", "Pandas"],
        "tasks": ["Define objective and success metric", "Collect dataset", "Exploratory data analysis",
                  "Build baseline model", "Feature engineering", "Train & tune model", "Evaluate on hold-out set",
                  "Write model card", "Build inference API / demo"],
        "milestones": [{"title": "Dataset ready", "offset_days": 10}, {"title": "Baseline beaten", "offset_days": 25},
                       {"title": "Demo deployed", "offset_days": 45}],
    },
    {
        "key": "hardware", "name": "Hardware / electronics", "category": "Hardware",
        "description": "Embedded / electronics build from schematic to enclosure.",
        "technologies": ["C++", "Arduino"],
        "tasks": ["Requirements & power budget", "Select components", "Draw schematic", "Breadboard prototype",
                  "Write firmware", "Design PCB", "Order parts / PCB", "Assemble & test", "Design enclosure",
                  "Document build"],
        "milestones": [{"title": "Prototype working", "offset_days": 21}, {"title": "PCB assembled", "offset_days": 45},
                       {"title": "Final build", "offset_days": 70}],
    },
    {
        "key": "research", "name": "Research project", "category": "Research",
        "description": "Question → literature → experiments → write-up.",
        "technologies": [],
        "tasks": ["Formulate research question", "Literature review", "Define methodology", "Run experiments",
                  "Analyse results", "Draft write-up", "Peer review / feedback", "Publish findings"],
        "milestones": [{"title": "Literature review done", "offset_days": 14},
                       {"title": "Experiments complete", "offset_days": 40}, {"title": "Paper published", "offset_days": 60}],
    },
]

SAMPLE_JOURNAL = """## Laying the foundations

Today I set up **ASTRA** — a portfolio and private command center in one.

### Decisions
- Flask for the backend: small, explicit, easy to deploy on Render.
- Turso (libSQL) for storage so data survives Render's ephemeral disk.
- Retrieval-augmented memory for the assistant instead of dumping the whole DB into prompts.

```python
def hello_astra():
    return "Systems online."
```

| Layer | Choice |
|-------|--------|
| Backend | Flask |
| Database | Turso |
| AI | Gemini |

- [x] Schema designed
- [ ] Deploy to Render

> Build the tool you wish you had.
"""


def seed():
    ts = now_iso()
    existing = {r["key"] for r in db.query("SELECT key FROM project_templates")}
    stmts = [
        (
            "INSERT INTO project_templates(key, name, description, category, technologies, tasks, milestones, builtin, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
            (t["key"], t["name"], t["description"], t["category"], jdumps(t["technologies"]), jdumps(t["tasks"]),
             jdumps(t["milestones"]), ts, ts),
        )
        for t in BUILTIN_TEMPLATES if t["key"] not in existing
    ]
    if stmts:
        db.batch(stmts)

    if db.scalar("SELECT value FROM meta WHERE key='seeded'"):
        return
    db.execute("INSERT INTO meta(key, value) VALUES('seeded', ?) ON CONFLICT(key) DO NOTHING", (ts,))
    from flask import current_app

    if not current_app.config.get("SEED_SAMPLE_DATA", True):
        return
    if db.scalar("SELECT COUNT(*) FROM projects", default=0):
        return
    log.info("Seeding sample project (removable from Settings → Data)")
    pid = db.insert(
        "INSERT INTO projects(slug, name, tagline, description, objective, problem, motivation, features, architecture,"
        " challenges, future, category, status, priority, progress, start_date, tags, is_public, is_featured,"
        " next_action, is_sample, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
        (
            "astra", "ASTRA", "Personal portfolio, project command center & AI workspace",
            "ASTRA is a futuristic portfolio for visitors and a private operating system for managing projects, "
            "journals, tasks and an AI assistant with retrieval-based memory.",
            "Manage my entire development journey from one place.",
            "Project knowledge was scattered across notes apps, repos and chat logs.",
            "I wanted a single place that shows my work publicly and remembers everything privately.",
            "- Exhibition-style public portfolio\n- Kanban task manager\n- Markdown development journal\n"
            "- Bug tracker, idea & snippet vaults\n- Gemini assistant with RAG memory",
            "Flask app factory with blueprints → services layer → Turso over HTTP. "
            "A lexical + embedding hybrid retriever feeds the Gemini assistant.",
            "**Ephemeral hosting** — solved by keeping all state in Turso.",
            "- Offline-first PWA mode\n- Public API for project data",
            "Web", "in_progress", "high", 0, today_iso(), jdumps(["portfolio", "ai", "flask"]), 1, 1,
            "Configure Turso + Gemini credentials and deploy", ts, ts,
        ),
    )
    techs = ["Python", "Flask", "Turso", "Gemini", "JavaScript", "Chart.js"]
    stmts = [("INSERT INTO project_technologies(project_id, name, sort_order) VALUES (?,?,?)", (pid, t, i))
             for i, t in enumerate(techs)]
    for i, (title, status) in enumerate([
        ("Design database schema", "done"), ("Implement authentication", "done"),
        ("Build public exhibition", "in_progress"), ("Connect Gemini API key", "todo"),
        ("Deploy to Render", "backlog"),
    ]):
        stmts.append((
            "INSERT INTO tasks(project_id, title, status, priority, sort_order, completed_at, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)", (pid, title, status, "high" if i < 3 else "medium", i,
                                           ts if status == "done" else None, ts, ts)))
    stmts.append((
        "INSERT INTO milestones(project_id, title, description, target_date, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)", (pid, "First deployment", "ASTRA live on Render", None, "planned", ts, ts)))
    stmts.append((
        "INSERT INTO journals(project_id, title, content, tags, entry_date, status, visibility, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (pid, "Day 1 — Systems online", SAMPLE_JOURNAL, jdumps(["setup", "architecture"]), today_iso(),
         "published", "public", ts, ts)))
    stmts.append((
        "INSERT INTO activity(project_id, kind, title, entity_type, entity_id, created_at) VALUES (?,?,?,?,?,?)",
        (pid, "project_created", "Project created: ASTRA (sample)", "projects", pid, ts)))
    db.batch(stmts)
    db.execute("INSERT INTO meta(key, value) VALUES('sample_project_id', ?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(pid),))
