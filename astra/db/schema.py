"""Schema + forward-only migrations (SQLite / libSQL / Turso compatible).

Each migration runs once; the applied version is stored in ``meta``.
To change the schema later, append a new entry to MIGRATIONS - never edit an
old one that already ran in production.
"""
import logging

from .core import db, split_sql

log = logging.getLogger("astra.db")

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    tagline TEXT DEFAULT '',
    description TEXT DEFAULT '',
    objective TEXT DEFAULT '',
    problem TEXT DEFAULT '',
    motivation TEXT DEFAULT '',
    features TEXT DEFAULT '',
    architecture TEXT DEFAULT '',
    challenges TEXT DEFAULT '',
    future TEXT DEFAULT '',
    achievements TEXT DEFAULT '',
    documentation TEXT DEFAULT '',
    category TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idea',
    priority TEXT NOT NULL DEFAULT 'medium',
    progress INTEGER NOT NULL DEFAULT 0,
    start_date TEXT,
    target_date TEXT,
    completed_date TEXT,
    cover_image TEXT DEFAULT '',
    gallery TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    github_url TEXT DEFAULT '',
    live_url TEXT DEFAULT '',
    youtube_url TEXT DEFAULT '',
    is_public INTEGER NOT NULL DEFAULT 0,
    is_featured INTEGER NOT NULL DEFAULT 0,
    show_journal INTEGER NOT NULL DEFAULT 1,
    next_action TEXT DEFAULT '',
    archived_from TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_sample INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_public ON projects(is_public, is_featured);

CREATE TABLE IF NOT EXISTS project_technologies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tech_project ON project_technologies(project_id);
CREATE INDEX IF NOT EXISTS idx_tech_name ON project_technologies(name);

CREATE TABLE IF NOT EXISTS project_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    url TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_links_project ON project_links(project_id);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT 'medium',
    due_date TEXT,
    notes TEXT DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed_at);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_milestones_date ON milestones(target_date);

CREATE TABLE IF NOT EXISTS journals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    entry_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    visibility TEXT NOT NULL DEFAULT 'private',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journals_project ON journals(project_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_journals_public ON journals(visibility, status);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT DEFAULT '',
    content TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project_id);

CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    url TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'reference',
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resources_project ON resources(project_id);

CREATE TABLE IF NOT EXISTS bugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    solution TEXT DEFAULT '',
    reported_at TEXT NOT NULL,
    resolved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bugs_project ON bugs(project_id, status);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'new',
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status);

CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    language TEXT DEFAULT 'plaintext',
    code TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snippets_lang ON snippets(language);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    entity_type TEXT DEFAULT '',
    entity_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity(created_at);
CREATE INDEX IF NOT EXISTS idx_activity_project ON activity(project_id, created_at);

CREATE TABLE IF NOT EXISTS focus_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    note TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_focus_open ON focus_sessions(ended_at);
CREATE INDEX IF NOT EXISTS idx_focus_project ON focus_sessions(project_id);

CREATE TABLE IF NOT EXISTS project_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT DEFAULT '',
    technologies TEXT DEFAULT '[]',
    tasks TEXT DEFAULT '[]',
    milestones TEXT DEFAULT '[]',
    builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'New conversation',
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON ai_conversations(updated_at);

CREATE TABLE IF NOT EXISTS ai_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources TEXT DEFAULT '[]',
    actions TEXT DEFAULT '[]',
    project_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON ai_messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS memory_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'fact',
    content TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES ai_conversations(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    project_id INTEGER,
    parent_id INTEGER,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    title TEXT DEFAULT '',
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding TEXT,
    source_date TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON doc_chunks(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_project ON doc_chunks(project_id);

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE,
    filename TEXT DEFAULT '',
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket TEXT NOT NULL,
    key TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate ON rate_events(bucket, key, created_at)
"""

# v2 — Personal OS: exhibit drafts, simple to-dos, personal diary, medicines, finances.
# Additive only: existing rows are kept; old project statuses fold into in_progress/completed.
SCHEMA_V2 = """
ALTER TABLE projects ADD COLUMN process TEXT DEFAULT '';
ALTER TABLE projects ADD COLUMN solutions TEXT DEFAULT '';
ALTER TABLE projects ADD COLUMN learnings TEXT DEFAULT '';
ALTER TABLE projects ADD COLUMN exhibit_published INTEGER NOT NULL DEFAULT 0;
UPDATE projects SET exhibit_published = 1 WHERE is_public = 1 AND status = 'completed';
UPDATE projects SET status = 'in_progress' WHERE status NOT IN ('completed');

CREATE TABLE IF NOT EXISTS project_exhibits (
    project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    draft TEXT NOT NULL DEFAULT '{}',
    generated_at TEXT,
    published_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority TEXT,
    due_date TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_todos_due ON todos(due_date);
CREATE INDEX IF NOT EXISTS idx_todos_completed ON todos(completed_at);

CREATE TABLE IF NOT EXISTS diary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    title TEXT DEFAULT '',
    content TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_diary_date ON diary_entries(entry_date);

CREATE TABLE IF NOT EXISTS medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dosage TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    frequency TEXT NOT NULL DEFAULT 'daily',
    weekdays TEXT DEFAULT '[]',
    interval_days INTEGER NOT NULL DEFAULT 1,
    dose_times TEXT DEFAULT '[]',
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    stopped_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_medicines_status ON medicines(status);

CREATE TABLE IF NOT EXISTS medicine_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
    log_date TEXT NOT NULL,
    dose_index INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'taken',
    logged_at TEXT NOT NULL,
    UNIQUE (medicine_id, log_date, dose_index)
);
CREATE INDEX IF NOT EXISTS idx_medlogs_date ON medicine_logs(log_date);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    description TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'Other',
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_when ON transactions(occurred_at);
CREATE INDEX IF NOT EXISTS idx_tx_kind ON transactions(kind, category)
"""

# v3 — per-medicine dose plan history [{"from": "YYYY-MM-DD", "count": n}], so changing the number of
# daily doses only affects days from the change onwards (past tracking stays exactly as it was).
SCHEMA_V3 = """
ALTER TABLE medicines ADD COLUMN dose_plan TEXT DEFAULT '[]'
"""

MIGRATIONS = [
    (1, SCHEMA_V1),
    (2, SCHEMA_V2),
    (3, SCHEMA_V3),
]


def migrate():
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    current = int(db.scalar("SELECT value FROM meta WHERE key='schema_version'", default=0) or 0)
    for version, script in MIGRATIONS:
        if version <= current:
            continue
        log.info("Applying schema migration v%s", version)
        for stmt in split_sql(script):
            try:
                db.execute(stmt)
            except Exception as exc:  # idempotent re-runs: column already added by a partial run
                if "duplicate column" in str(exc).lower():
                    log.info("Skipping existing column: %s", stmt[:80])
                    continue
                raise
        db.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(version),),
        )
        current = version
    return current
