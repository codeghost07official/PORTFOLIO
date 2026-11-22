"""Data portability: full JSON backup + per-collection CSV."""
import csv
import io

from ..db import db
from ..utils import now_iso

EXPORT_TABLES = [
    "settings", "projects", "project_technologies", "project_links", "tasks", "milestones", "journals", "notes",
    "resources", "bugs", "ideas", "snippets", "activity", "focus_sessions", "project_templates",
    "ai_conversations", "ai_messages", "memory_records",
]
CSV_TABLES = ["projects", "tasks", "milestones", "journals", "notes", "resources", "bugs", "ideas", "snippets"]


def full_export(include_ai=True):
    data = {"format": "astra-backup", "version": 1, "exported_at": now_iso(), "tables": {}}
    for table in EXPORT_TABLES:
        if not include_ai and table.startswith(("ai_", "memory")):
            continue
        data["tables"][table] = db.query(f"SELECT * FROM {table} ORDER BY rowid")
    return data


def csv_export(table):
    if table not in CSV_TABLES:
        raise KeyError(table)
    rows = db.query(f"SELECT * FROM {table} ORDER BY id")
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            # neutralise spreadsheet formula injection
            writer.writerow({k: ("'" + v if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in r.items()})
    return buf.getvalue()


def markdown_journals():
    """All journals as a single Markdown document."""
    rows = db.query("SELECT j.*, p.name AS project_name FROM journals j LEFT JOIN projects p ON p.id=j.project_id "
                    "ORDER BY j.entry_date, j.id")
    parts = ["# ASTRA journal export", f"_Exported {now_iso()}_", ""]
    for r in rows:
        parts += [f"## {r['title']}", f"*{r['entry_date']} · {r['project_name'] or 'No project'} · "
                                      f"{r['status']} · {r['visibility']}*", "", r["content"] or "", "", "---", ""]
    return "\n".join(parts)
