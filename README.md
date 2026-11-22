# ASTRA — Personal Portfolio, Project Command Center & AI Workspace

ASTRA gives you two experiences in one Flask app:

- **Public exhibition (Liquid Glass sci-fi):** visitors explore *completed* projects whose exhibits you've published, plus your identity, skills, achievements and journey. In-progress projects show only their title and an "In progress" badge. A floating AI guide answers questions from public content only.
- **Private personal OS:** exactly six sections, reached via the footer **Admin** link (`/gate`):

| Section | What it does |
|---|---|
| **Projects** | Create, edit and delete projects, and switch them between In progress and Completed. Each project has a private **journal**. **Exhibit Management** holds a draft of everything the public sees. **Generate Exhibition Content with AI** has Gemini read the whole journal in order and fill the draft, which you review, edit and then publish. **Public Profile** edits your public identity. |
| **Medicines** | Dashboard with adherence analytics, a spreadsheet tracker with one checkbox per dose, and History. Schedules can be daily, alternate days, chosen weekdays or every N days, with optional end dates. **Stop** keeps all history; **Delete** removes everything (after confirmation). |
| **Tasks** | Simple to-dos: optional priority and due date, quick add, and Dashboard, All, Today, Upcoming and Completed views, with task analytics. |
| **Journaling** | Personal daily journal with its own "Codex of Days" theme. Autosaves to Turso (with a local backup against refreshes), supports several entries per day, search, and a browse-by-date calendar. |
| **Expenses** | Income and expense ledger with editable date and time, categories, filters, monthly overview and finance dashboard. Amounts are stored exactly, in paise. |
| **AI Assistant** | Your private assistant lives in a **floating HUD** that persists across every admin page. It replies in short sentences in text and speech (a female British voice where available, with mute, volume, speed and replay), takes voice input, and proposes actions only for you to confirm. Its settings cover personality, voice, context permissions, memory and history. |

All data lives in Turso. The admin shell navigates client-side, so the HUD and its conversation never reset. Shortcuts: **Ctrl+K** jump, **Q** quick task, **Ctrl+J** toggle the assistant.

There is exactly **one administrator**: you. Visitors can't sign up, and there are no other accounts.

---

## Contents
1. [Features](#features)
2. [Tech stack](#tech-stack)
3. [Project structure](#project-structure)
4. [Local setup](#local-setup)
5. [Environment variables](#environment-variables)
6. [Turso setup (beginner friendly)](#turso-setup-beginner-friendly)
7. [Gemini setup](#gemini-setup)
8. [Admin credentials](#admin-credentials)
9. [Deploying to Render (free tier)](#deploying-to-render-free-tier)
10. [How the AI memory works](#how-the-ai-memory-works)
11. [Security](#security)
12. [Backups & data ownership](#backups--data-ownership)

---

## Features

### Public exhibition
- Cinematic landing page:
  - a live 3D wireframe "core" (geodesic sphere, orbit rings, satellites and a radar sweep)
  - floating rotating mechanical objects (icosahedron, gear, torus)
  - a particle field with cursor and scroll parallax, scanlines and a blueprint grid
- About, interests, skills, a technology cloud, achievements, a journey timeline and contact links. You edit all of these in **Settings → Profile**; none are hard-coded.
- Featured projects, a filterable project archive (search, category, technology) and a dedicated page per project with:
  - overview, problem, motivation, features, tech stack, architecture, challenges, achievements, future work and documentation
  - links, a screenshot gallery with lightbox, an embedded YouTube video and a milestone timeline
  - the public development journal
- **Empty sections and empty links are never rendered.** External links always open in a new tab with `rel="noopener noreferrer"`.
- Markdown renders as polished technical documentation: tables, task lists, blockquotes, images, and syntax-highlighted code blocks with language labels and copy buttons.
- Floating **AI guide** (Gemini, server-side) that answers from public data only.
- Responsive from phone to desktop. Effects respect `prefers-reduced-motion` and the **Effects** setting (full / lite / off), and pause in background tabs.

### Private command center
| Area | What you get |
|---|---|
| Dashboard | Live KPIs, current mission with timer, project progress, deadlines, milestones, activity feed, recent journals, open bugs, Chart.js analytics (12-week productivity, project distribution, 30-day activity, focus time per project). Widgets can be toggled. |
| Projects | Create from scratch or from templates. Edit, archive, restore, delete (with confirmation), set status (idea → planning → active → paused → completed → archived), feature, public/private, search, filter and sort. Image upload is stored in the DB. |
| Workspace (per project) | Overview (next action, current objectives, links, focus time), tasks (list **and** drag-and-drop Kanban), milestone timeline, journal, notes, resources, bugs |
| Journal | Markdown editor with a toolbar, write/split/preview modes, autosave, save status, Ctrl+S, draft/published and private/public, tags, dates, search |
| Toolkit | Bug & issue tracker, Idea vault (promote an idea to a project without losing the original), Snippet vault (highlighted, one-click copy), Notes, Resources |
| Roadmap | Gantt-style timeline of projects with milestones, a "today" marker, the pipeline and future ideas |
| Focus / Current mission | Pick a project or task, see it prominently with a live timer, and switch quickly. Focus sessions double as time tracking. |
| Quick capture | Press **Q** anywhere to capture an idea, note, task, bug or resource. Items without a project land in the **Inbox** for later triage. |
| Global search | **Ctrl+K** command palette, plus a search page across projects, tasks, journals, notes, ideas, snippets, resources, bugs, milestones and AI chats |
| Activity timeline | Real events written by the backend: created, completed, reached, published, status changes and more |
| AI assistant | Multiple sessions (new, rename, delete), search past chats, project context mode, cited sources, confirmable actions, and a memory bank |
| Settings | Profile, appearance and accent, public section visibility, chatbot behaviour, model overrides (with a "list models" button), login entry point, project defaults, session revocation, export/backup, index maintenance |

---

## Tech stack
- **Backend:** Python 3.10+, Flask (application factory and blueprints), Gunicorn
- **Database:** Turso (libSQL, SQLite-compatible) through Turso's official **HTTP API**. The optional `libsql` SDK driver is also supported. Turso is the only persistent store: there is no local database fallback.
- **AI:** Google Gemini REST API (generation and `gemini-embedding-001` embeddings), all calls server-side
- **Frontend:** HTML5, CSS3 and vanilla JavaScript, with no build step. Chart.js renders charts and highlight.js handles code highlighting (both from jsDelivr). The 3D effects use a custom dependency-free canvas renderer.
- **Markdown:** Python-Markdown, sanitised with `nh3` (Rust *ammonia*)

---

## Project structure
```
PORTFOLIO/
├── app.py                      # entry point (python app.py / gunicorn app:app)
├── requirements.txt
├── render.yaml                 # Render blueprint
├── .env.example                # every setting, documented
├── .python-version
├── scripts/hash_password.py    # generates ADMIN_PASSWORD_HASH
└── astra/
    ├── __init__.py             # app factory, hooks, error handlers
    ├── config.py               # env-driven configuration
    ├── security.py             # auth, sessions, CSRF, rate limiting, headers
    ├── markdown_render.py      # Markdown → sanitised HTML
    ├── utils.py
    ├── db/                     # database layer
    │   ├── core.py             # Turso drivers: HTTP (default) and libsql SDK
    │   ├── schema.py           # schema + forward-only migrations
    │   └── seed.py             # built-in templates + removable sample project
    ├── services/               # business logic (single validated write path)
    │   ├── entities.py         # whitelist-driven CRUD for tasks, bugs, notes…
    │   ├── projects.py         # lifecycle, templates, idea conversion
    │   ├── dashboard.py, focus.py, activity.py, search.py, export.py
    │   ├── settings.py
    │   └── public_data.py      # the ONLY data source for public pages/chatbot
    ├── rag/                    # retrieval & memory
    │   ├── chunking.py, indexer.py, retriever.py
    ├── ai/
    │   ├── gemini.py           # REST client, model fallback, embeddings
    │   ├── assistant.py        # private assistant (context building, actions)
    │   ├── actions.py          # whitelisted, validated, confirm-first actions
    │   └── public_bot.py       # public guide
    ├── routes/                 # public, auth, admin pages, admin API, AI API
    ├── templates/              # Jinja templates (public/, admin/)
    └── static/                 # css/, js/ (public + admin/), img/
```

---

## Local setup

> ASTRA never installs anything by itself. You run these commands.

**1. Create a virtual environment** (Python 3.10 or newer; 3.12 recommended)

Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**2. Install the dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure your environment**
```bash
cp .env.example .env
```
Open `.env` and set at least `SECRET_KEY`, `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` (see [Admin credentials](#admin-credentials)). Also set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` (see [Turso setup](#turso-setup-beginner-friendly)); ASTRA needs them to run.

**4. Check your setup** (optional, but recommended)
```bash
python scripts/check_setup.py
```
This checks `.env`, your credentials, the database (it writes, reads and deletes a scratch row) and Gemini (key valid, configured models available). Every problem it finds comes with a fix.

**5. Run the app**

```bash
python app.py
```
The console prints a startup summary: the site URL, the admin login URL, which database is in use, and the Gemini status. The site is at <http://localhost:5000>, and login is at `/gate` (or your `ADMIN_LOGIN_PATH`). Debug mode with auto-reload is on in development.

> Gunicorn doesn't run on Windows. Locally, use `python app.py`. Deployment is a later phase.

---

## Local development notes

**Where your data goes:** everything (projects, tasks, journals, settings, AI chats, RAG chunks and embeddings, uploaded images) is stored in Turso. If `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` are missing or Turso can't be reached, ASTRA shows a diagnostic page with the error and the likely fix, and retries every 10 seconds. It never switches to a local database.

Uploaded images are stored in the database (the `media` table), in Turso.

**Diagnostics:** **Settings → System status → Run diagnostics** runs the same checks as `scripts/check_setup.py` from inside the app.

**Speed with remote Turso:** every query is a network round trip, which was about 300 ms from this machine to the Oregon region. ASTRA batches independent reads into one request (the dashboard needs 2 round trips), caches public pages briefly, and indexes AI memory in a background thread, so saves stay quick. If pages still feel slow, create the Turso database in the region closest to you.

**Gemini availability:** flash models sometimes return *"high demand"* (503) or retire a model for new keys. ASTRA tries `GEMINI_MODEL`, then each model in `GEMINI_FALLBACK_MODEL` (comma-separated), then the `gemini-flash-latest` and `gemini-flash-lite-latest` aliases. The reply shows which model answered. Use **Settings → AI → List models** to see what your key can use.

**Troubleshooting**

| Symptom | Fix |
|---|---|
| "The database is unavailable" page | Read the error on the page, or run `python scripts/check_setup.py`. A 401 means the Turso token is wrong or expired, so create a new one. A DNS or connection error means you're offline or the URL is wrong. |
| Login always fails | Check `ADMIN_USERNAME`, and wrap `ADMIN_PASSWORD_HASH` in single quotes in `.env`. Don't set `ASTRA_ENV=production` locally, because secure cookies need HTTPS. |
| "Too many failed attempts" | Wait `LOGIN_WINDOW_MINUTES` (default 15). |
| AI says it's offline | Set `GEMINI_API_KEY`, then check **Settings → System status**. |

---

## Site map

**Public:**
- `/` home (cinematic intro and exhibit halls)
- `/about`, `/achievements`, `/journey`, `/contact`
- `/projects` exhibition, with filter state kept in the URL: `?category=`, `?tech=`, `?q=`, `?sort=`
- `/projects/<slug>` exhibit page

**Private** (each is its own page, so refresh, back/forward and bookmarks all work):

| Route | Page |
|---|---|
| `/admin/` | Dashboard |
| `/admin/projects`, `/admin/projects/new` | Project list, new project |
| `/admin/projects/<id>` | Workspace overview |
| `/admin/projects/<id>/{tasks,milestones,journal,notes,resources,bugs,activity}` | Workspace sections |
| `/admin/projects/<id>/edit` | Project editor |
| `/admin/tasks`, `/admin/tasks/<id>` | Global Kanban/list, task page |
| `/admin/journal` → `/admin/journal/<id>` → `/admin/journal/<id>/edit` | List → reading view → editor |
| `/admin/{ideas,bugs,snippets,resources,notes}` and `…/<id>` | Toolkit lists and item pages |
| `/admin/roadmap`, `/admin/activity`, `/admin/search`, `/admin/capture`, `/admin/templates` | Other tools (`capture` is the inbox) |
| `/admin/assistant`, `/admin/assistant/<conversation-id>` | AI assistant |
| `/admin/settings/{system,profile,appearance,ai,security,defaults,data}` | Settings sections |

Page changes use the browser's native cross-document View Transitions (Chrome and Edge), with a fallback fade elsewhere. They're disabled under `prefers-reduced-motion`.

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | **yes (prod)** | Signs session cookies. Use a long random value. |
| `ASTRA_ENV` | prod | `production` turns on secure cookies, HSTS and proxy headers |
| `TURSO_DATABASE_URL` | **yes** | `libsql://<db>-<org>.turso.io`. Required: ASTRA has no local database. |
| `TURSO_AUTH_TOKEN` | **yes** | Turso database token |
| `TURSO_DRIVER` | no | `http` (default) or `libsql` |
| `ADMIN_USERNAME` | **yes** | Your login identifier |
| `ADMIN_PASSWORD_HASH` | **yes** | Werkzeug scrypt hash (see below) |
| `ADMIN_PASSWORD` | dev only | Plain-text alternative for local experiments |
| `ADMIN_LOGIN_PATH` | no | Login URL path (default `gate`) |
| `SESSION_LIFETIME_HOURS` / `SESSION_IDLE_MINUTES` | no | Session expiry (8 h absolute, 120 min idle) |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_MINUTES` | no | Login rate limit (5 failures per 15 min per IP) |
| `GEMINI_API_KEY` | for AI | Google AI Studio key |
| `GEMINI_MODEL` | no | Primary model ID (default `gemini-3.8-flash`) |
| `GEMINI_FALLBACK_MODEL` | no | Comma-separated models tried when the primary is overloaded or unavailable (default `gemini-3.7-flash,gemini-flash-latest`) |
| `GEMINI_PUBLIC_MODEL` | no | Optional cheaper model for the public guide |
| `EMBEDDINGS_PROVIDER` | no | `gemini` or `none` (keyword-only retrieval) |
| `GEMINI_EMBEDDING_MODEL` / `EMBEDDING_DIM` | no | Defaults: `gemini-embedding-001` and `768` |
| `PUBLIC_CHAT_*` | no | Public chatbot limits (per IP and global per day, max message length) |
| `SEED_SAMPLE_DATA` | no | Create one removable sample project on first run |

Every key is documented in [`.env.example`](.env.example).

---

## Turso setup (beginner friendly)

Turso is a hosted SQLite-compatible database with a free tier. ASTRA keeps **all** persistent data there, because Render's free disk is wiped on every restart.

1. **Create an account** at <https://turso.tech> and sign in to the dashboard.
2. **Create a database.** In the dashboard, click **Create Database**, name it `astra`, and pick the region closest to your Render region.
   - Or use the CLI. Install it ([docs](https://docs.turso.tech/cli/installation)), then run:
     ```bash
     turso auth login
     turso db create astra
     ```
3. **Get the database URL.**
   - Dashboard: open the database. The URL looks like `libsql://astra-<your-org>.turso.io`.
   - CLI: `turso db show astra --url`
   - Put it in `TURSO_DATABASE_URL`.
4. **Create an auth token.**
   - Dashboard: open the database, choose **Create Token**, and select read & write access.
   - CLI: `turso db tokens create astra`
   - Put the long string it prints in `TURSO_AUTH_TOKEN`. Treat it like a password.
5. **Start ASTRA.** On first boot it creates all tables, indexes and built-in templates. There are no manual SQL steps. The **Settings → System status** panel should show `turso-http` as the database.

```dotenv
TURSO_DATABASE_URL=libsql://astra-yourorg.turso.io
TURSO_AUTH_TOKEN=eyJhbGciOi...
```

**Schema changes later:** add a new `(version, sql)` entry to `MIGRATIONS` in `astra/db/schema.py`. It runs once on the next start.

---

## Gemini setup
1. Go to <https://aistudio.google.com/apikey> and create an API key.
2. Set `GEMINI_API_KEY` in `.env` (and later on Render).
3. Choose the model. `GEMINI_MODEL` defaults to `gemini-3.8-flash`. Model IDs change over time, so in **Settings → AI & chatbot** click **List models available to my API key**, then click an ID to use it. You can also set it in the environment. If the primary ID is rejected, ASTRA retries with `GEMINI_FALLBACK_MODEL` automatically.
4. Embeddings (`gemini-embedding-001`, 768 dimensions) power semantic memory. To stay strictly within free quotas, set `EMBEDDINGS_PROVIDER=none` and ASTRA uses keyword (BM25) retrieval only.

The key is used only server-side. It never appears in HTML or JavaScript.

---

## Admin credentials
Generate a password hash (the password is typed hidden and never stored):
```bash
python scripts/hash_password.py
```
Copy the output into `.env`. Keep the single quotes in `.env` files.
```dotenv
ADMIN_USERNAME=commander
ADMIN_PASSWORD_HASH='scrypt:32768:8:1$...$...'
```
On Render, paste the hash value **without** quotes.

**Discreet entry point.** The public navbar has no login button. Choose how you reach the login page in **Settings → Login & security**:
- a faint glyph after the footer copyright (default)
- double-clicking the ASTRA logo
- typing `astra` anywhere on the page
- none, in which case you visit `/<ADMIN_LOGIN_PATH>` directly

This is a convenience only. Real protection is server-side; see [Security](#security).

---

## Deploying to Render (free tier)
1. Push this repository to GitHub. Don't commit `.env`.
2. In the Render dashboard, choose **New → Blueprint** and select the repository. `render.yaml` sets up:
   - a free Python web service (Python 3.12.7)
   - `gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`
   - the `/healthz` health check
   - a generated `SECRET_KEY`, `ASTRA_ENV=production` and `SEED_SAMPLE_DATA=false`
3. When prompted, fill in the variables, copying each value from your local `.env`:
   `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` (without quotes),
   `ADMIN_LOGIN_PATH`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`.
   Do **not** set `ADMIN_PASSWORD` (plain text, local convenience only) on Render.
4. Deploy. Visit `https://<service>.onrender.com/healthz`. It should return `{"status":"ok","database":"turso-http"}`.
5. Open `https://<service>.onrender.com/<ADMIN_LOGIN_PATH>` and sign in with your **existing PIN**: it is stored
   (hashed) in Turso, so it is the same locally and on Render.

**Your data.** The deployed app reads and writes the same Turso database as your local copy, so every project,
journal, medicine log, task, expense, setting and conversation is there immediately. Startup only applies schema
migrations that haven't run yet; it never drops, resets or re-seeds an existing database.

You can also skip the Blueprint and set it up manually: **New → Web Service**, Build command `pip install -r requirements.txt`, Start command as in `render.yaml`, then add the same environment variables.

Notes:
- Free instances sleep when idle, so the first request after a sleep takes a few seconds.
- Nothing persistent is written to Render's disk. Uploaded images are stored in Turso, in the `media` table.
- Logs go to stdout, which you can read in the Render dashboard.

---

## How the AI memory works

**Indexing.** Every write through the services layer re-chunks that single record into `doc_chunks`. This covers projects, tasks, milestones, journals (split on headings, with overlap), notes, resources, bugs, ideas, snippets and assistant replies. Gemini embeddings are computed in a background thread and re-used whenever a chunk's content hash hasn't changed. Vectors are stored compactly as float16 values.

**Retrieval.** For each question, ASTRA runs hybrid ranking in Python: BM25 lexical scoring combined with cosine similarity. It adds a boost for the selected project and caps how many chunks come from one source. Workspace sources and past-conversation sources are retrieved separately. At personal-workspace scale this needs no vector database.

**Prompt.** Each request includes only what's relevant:
- persona and rules
- recent turns of the conversation
- a compact **workspace snapshot**: projects with IDs, open tasks, bugs, milestones, the last 7 days of activity, and current focus
- your **memory bank**
- the top retrieved sources, labelled `[S#]` and marked `WORKSPACE` or `PAST CONVERSATION`

The model is told to cite sources, to separate facts from past chats from its own suggestions, and to say plainly when no record exists.

**Actions.** The assistant can only *propose* actions as JSON. Supported actions:
- `create_task`, `update_task`, `delete_task`
- `create_journal_draft`, `add_note`, `update_project`
- `create_idea`, `create_bug`, `update_bug`
- `save_memory`

The backend validates each proposal against a whitelist and checks that referenced IDs exist. It shows the proposal as a card, and executes it through the same validated service functions the UI uses only after you click **Confirm**. Destructive actions need a second confirmation. AI-generated SQL is never executed.

**Public guide.** It reads only `services/public_data.py`, which filters for public, non-archived projects and published public journals. It has no path to private data, admin notes or memories.

---

## Security
- **Single admin.** Credentials come from the environment and the password is stored as a Werkzeug scrypt hash. Comparisons run in constant time.
- **Sessions.**
  - Signed `HttpOnly`, `SameSite=Lax` cookies, marked `Secure` in production
  - Absolute and idle expiry
  - Session fixation protection
  - **Server-side revocation:** logging out rotates a session epoch stored in the DB, which invalidates every copy of the cookie
- **CSRF.** A per-session token is required on every POST, PUT, PATCH or DELETE, sent in a form field or the `X-CSRF-Token` header.
- **Rate limiting.** Backed by the database, so it works across workers and restarts: failed logins per IP, and public chat per IP and globally per day. IPs are stored only as HMAC hashes.
- **Server-side protection.** Every admin page and `/api/admin/*` route is guarded server-side. Hiding the login entry point isn't relied on.
- **SQL.** Statements are always parameterised, and only whitelisted columns can be written.
- **Markdown and XSS.** Output is sanitised with nh3: no scripts, event handlers or `javascript:` URLs. Templates are auto-escaped.
- **Headers.** A strict Content Security Policy with no inline scripts, plus `X-Frame-Options: DENY`, `nosniff`, Referrer-Policy, HSTS in production, and `no-store` on admin responses.
- **Uploads.** Only PNG, JPEG, GIF and WebP are accepted, verified by magic bytes (SVG is rejected). Images are served from unguessable tokens.
- **CSV export.** Values are protected against spreadsheet formula injection.
- **Secrets.** None are committed. `.env` is gitignored, and the Gemini key and Turso token never reach the browser.

---

## Backups & data ownership
**Settings → Backup & data** offers:
- **Full JSON backup** of every table (optionally without AI chats)
- **CSV exports** for projects, tasks, milestones, journals, notes, resources, bugs, ideas and snippets
- **All journals as a single Markdown file**

The search index can be rebuilt from your data at any time, so it's excluded from backups. Because Turso is SQLite-compatible, you can also run `turso db shell astra .dump > backup.sql`.

**Sample data:** a fresh database gets one example project, "ASTRA". Remove it with **Settings → Backup & data → Remove sample project**, or set `SEED_SAMPLE_DATA=false` before the first run.
