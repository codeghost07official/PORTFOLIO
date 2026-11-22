PROJECT_STATUSES = ["in_progress", "completed"]
PRIORITIES = ["low", "medium", "high", "critical"]
TASK_STATUSES = ["backlog", "todo", "in_progress", "blocked", "done"]
MILESTONE_STATUSES = ["planned", "in_progress", "done", "missed"]
BUG_SEVERITIES = ["low", "medium", "high", "critical"]
BUG_STATUSES = ["open", "investigating", "fixed", "closed"]
IDEA_STATUSES = ["new", "exploring", "converted", "shelved"]
JOURNAL_STATUSES = ["draft", "published"]
VISIBILITIES = ["private", "public"]
NOTE_CATEGORIES = ["general", "idea", "decision", "remember", "technical", "temporary"]
RESOURCE_CATEGORIES = [
    "documentation", "tutorial", "api", "website", "issue", "article", "research", "reference", "tool",
]
MEMORY_KINDS = ["fact", "preference", "decision", "context"]

LABELS = {
    "in_progress": "In progress",
    "completed": "Completed",
    "todo": "To do",
}


def label(value):
    return LABELS.get(value, (value or "").replace("_", " ").capitalize())


ENUMS = {
    "project_statuses": PROJECT_STATUSES,
    "priorities": PRIORITIES,
    "task_statuses": TASK_STATUSES,
    "milestone_statuses": MILESTONE_STATUSES,
    "bug_severities": BUG_SEVERITIES,
    "bug_statuses": BUG_STATUSES,
    "idea_statuses": IDEA_STATUSES,
    "journal_statuses": JOURNAL_STATUSES,
    "visibilities": VISIBILITIES,
    "note_categories": NOTE_CATEGORIES,
    "resource_categories": RESOURCE_CATEGORIES,
    "memory_kinds": MEMORY_KINDS,
}
