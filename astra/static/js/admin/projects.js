/* Projects section: project list, Exhibit Management, project workspace (overview / journal / exhibit). */
(function () {
  "use strict";
  const A = window.ASTRA, esc = A.esc, $$ = A.$$;

  const STATUS = { in_progress: "In progress", completed: "Completed" };
  const statusPill = (p) => `<span class="badge b-${p.status}">${STATUS[p.status] || A.label(p.status)}</span>`;
  const exhibitPill = (p) => p.exhibit_published
    ? `<span class="badge b-published">${p.status === "completed" ? "Exhibit live" : "Exhibit published · waits for completion"}</span>`
    : (p.exhibit && p.exhibit.has_draft ? '<span class="badge b-draft">Exhibit draft</span>' : '<span class="badge b-private">No exhibit</span>');

  /* ---------- create / edit dialog (internal project information) ---------- */
  const PROJECT_FIELDS = [
    { name: "name", label: "Project name", required: true, full: true },
    { name: "category", label: "Category", placeholder: "Web, AI, Tool…" },
    { name: "status", label: "Status", type: "select", options: [["in_progress", "In progress"], ["completed", "Completed"]] },
    { name: "objective", label: "Objective (private)", type: "textarea", rows: 2, full: true, placeholder: "What is this project for?" },
    { name: "next_action", label: "Next action (private)", full: true },
    { name: "technologies", label: "Technologies", type: "tags", full: true, placeholder: "Python, Flask…" },
    { name: "start_date", label: "Start date", type: "date" },
    { name: "target_date", label: "Target date", type: "date" },
    { name: "is_public", label: "Show on public site (in-progress projects show only title + status)", type: "bool", full: true },
    { name: "is_featured", label: "Feature on the public home page", type: "bool", full: true },
  ];
  A.editProject = async (p = null) => {
    const values = p ? { ...p, technologies: p.technologies } : { status: "in_progress", start_date: A.today(), is_public: true };
    const saved = await A.formModal({
      title: p ? "Edit project" : "New project", fields: PROJECT_FIELDS, values, submitLabel: p ? "Save" : "Create project",
      onSubmit: (d) => (p ? A.api("PUT", `/api/admin/projects/${p.id}`, d) : A.api("POST", "/api/admin/projects", d)),
    });
    if (saved) { A.toast(p ? "Project saved" : "Project created", "ok"); A.meta(true); }
    return saved;
  };
  A.deleteProject = async (p) => {
    const ok = await A.confirm(`Permanently delete “${p.name}”, its project journal and its exhibit? This cannot be undone.`,
      { danger: true, confirmLabel: "Delete project", title: "Delete project" });
    if (!ok) return false;
    await A.api("DELETE", `/api/admin/projects/${p.id}`);
    A.toast("Project deleted", "ok");
    A.meta(true);
    return true;
  };
  A.setProjectStatus = async (p, status) => {
    const r = await A.api("PATCH", `/api/admin/projects/${p.id}`, { status });
    A.toast(status === "completed" ? "Marked completed" + (r.exhibit_published ? " · exhibit is now live" : " · publish its exhibit to show details") : "Marked in progress · public details hidden", "ok");
    return r;
  };

  /* ======================= PROJECT LIST ======================= */
  A.page("projects", async (main) => {
    const box = main.querySelector("#plist"), stats = main.querySelector("#pstats");
    const state = { q: "", status: "", sort: "updated" };
    const load = async () => {
      if (!box.children.length) A.loading(box, 3);
      let rows;
      try { rows = await A.api("GET", "/api/admin/projects" + A.qs({ q: state.q, status: state.status, sort: state.sort })); }
      catch (e) { return A.errorState(box, e, load); }
      const all = state.q || state.status ? await A.api("GET", "/api/admin/projects") : rows;
      stats.innerHTML = A.kpis([
        [all.length, "Projects"], [all.filter((p) => p.status === "in_progress").length, "In progress"],
        [all.filter((p) => p.status === "completed").length, "Completed", "", "ok"],
        [all.filter((p) => p.exhibit_published && p.status === "completed").length, "Live exhibits"],
        [all.reduce((n, p) => n + p.journal_count, 0), "Journal entries"],
      ]);
      if (!rows.length) return A.empty(box, state.q || state.status ? "No projects match" : "No projects yet", "Create a project, then document it in its journal.", '<button class="btn primary" data-new>New project</button>');
      box.innerHTML = `<div class="pgrid">${rows.map((p) => `
        <article class="panel pcard" data-id="${p.id}">
          <div class="row wrap">${statusPill(p)}${exhibitPill(p)}<span class="spacer"></span><span class="dim small mono">${esc(p.category || "")}</span></div>
          <h3><a href="/admin/projects/${p.id}">${esc(p.name)}</a></h3>
          ${p.objective ? `<p class="muted small" style="margin:0">${esc(A.excerpt(p.objective, 140))}</p>` : ""}
          <div class="small dim">${p.journal_count} journal entr${p.journal_count === 1 ? "y" : "ies"}${p.journal_last ? ` · last ${A.fmtDate(p.journal_last)}` : ""}</div>
          <div class="foot">
            <div class="pc-links">
              <a class="btn sm" href="/admin/projects/${p.id}">Open</a>
              <a class="btn sm ghost" href="/admin/projects/${p.id}/journal">Journal</a>
              <a class="btn sm ghost" href="/admin/projects/${p.id}/exhibit">Exhibit</a>
            </div>
            <div class="pc-acts">
              <button class="btn sm ghost" data-act="toggle" title="Change status">${p.status === "completed" ? "↺ In progress" : "✓ Complete"}</button>
              <button class="btn sm icon ghost" data-act="edit" title="Edit" aria-label="Edit ${esc(p.name)}">${A.icon("edit")}</button>
              <button class="btn sm icon ghost" data-act="delete" title="Delete" aria-label="Delete ${esc(p.name)}">${A.icon("trash")}</button>
            </div>
          </div>
        </article>`).join("")}</div>`;
      const byId = Object.fromEntries(rows.map((p) => [p.id, p]));
      $$("[data-act]", box).forEach((b) => b.addEventListener("click", async () => {
        const p = byId[b.closest("[data-id]").dataset.id];
        try {
          if (b.dataset.act === "toggle") await A.setProjectStatus(p, p.status === "completed" ? "in_progress" : "completed");
          if (b.dataset.act === "edit" && !(await A.editProject(p))) return;
          if (b.dataset.act === "delete" && !(await A.deleteProject(p))) return;
          load();
        } catch (e) { A.toast(e.message, "err"); }
      }));
    };
    main.addEventListener("click", async (e) => {
      if (!e.target.closest("[data-new]")) return;
      const p = await A.editProject(null);
      if (p) A.go(`/admin/projects/${p.id}`);
    });
    main.querySelector("#pq").addEventListener("input", A.debounce((e) => { state.q = e.target.value; load(); }, 250));
    main.querySelector("#pstatus").addEventListener("change", (e) => { state.status = e.target.value; load(); });
    main.querySelector("#psort").addEventListener("change", (e) => { state.sort = e.target.value; load(); });
    load();
  });

  /* ======================= EXHIBIT MANAGEMENT (overview) ======================= */
  A.page("exhibits", async (main) => {
    const box = main.querySelector("#xlist");
    const load = async () => {
      A.loading(box, 2);
      const rows = await A.api("GET", "/api/admin/projects");
      if (!rows.length) return A.empty(box, "No projects yet", "Create a project first.");
      box.innerHTML = `<div class="panel table-wrap"><table class="data"><thead><tr><th>Project</th><th>Status</th><th>Public exhibit</th><th>Draft</th><th>Visitors see</th><th></th></tr></thead><tbody>${rows.map((p) => {
        const live = p.exhibit_published && p.status === "completed";
        const visitors = !p.is_public && !live ? "Nothing (hidden)" : p.status === "in_progress" ? "Title + “In progress” only" : live ? "Full exhibit" : "Nothing until published";
        return `<tr data-id="${p.id}"><td class="title-cell"><a href="/admin/projects/${p.id}/exhibit">${esc(p.name)}</a></td><td>${statusPill(p)}</td>
          <td>${p.exhibit_published ? '<span class="badge b-published">Published</span>' : '<span class="badge b-private">Not published</span>'}${p.exhibit.published_at ? `<div class="dim small">${A.fmtDate(p.exhibit.published_at)}</div>` : ""}</td>
          <td class="small">${p.exhibit.has_draft ? `Saved ${A.rel(p.exhibit.draft_updated)}${p.exhibit.generated_at ? ` · AI ${A.fmtDate(p.exhibit.generated_at)}` : ""}` : '<span class="dim">—</span>'}</td>
          <td class="small">${visitors}</td>
          <td><div class="row"><a class="btn sm" href="/admin/projects/${p.id}/exhibit">Edit exhibit</a>
            ${p.exhibit_published ? '<button class="btn sm ghost" data-act="unpublish">Unpublish</button>' : '<button class="btn sm ghost" data-act="publish">Publish</button>'}
            ${live ? `<a class="btn sm ghost" href="/projects/${esc(p.slug)}" target="_blank" rel="noopener">View ↗</a>` : ""}</div></td></tr>`;
      }).join("")}</tbody></table></div>`;
      $$("[data-act]", box).forEach((b) => b.addEventListener("click", async () => {
        const id = b.closest("[data-id]").dataset.id;
        if (b.dataset.act === "publish" && !(await A.confirm("Publish the saved exhibit draft? Visitors see it once the project is completed.", { confirmLabel: "Publish" }))) return;
        try { await A.api("POST", `/api/admin/projects/${id}/exhibit/${b.dataset.act}`); A.toast(b.dataset.act === "publish" ? "Exhibit published" : "Exhibit unpublished", "ok"); load(); }
        catch (e) { A.toast(e.message, "err"); }
      }));
    };
    load().catch((e) => A.errorState(box, e, load));
  });

  /* ======================= WORKSPACE ======================= */
  A.page("workspace", async (main) => {
    const pid = Number(main.dataset.projectId), tab = main.dataset.tab;
    const pane = main.querySelector("#ws-pane");
    let project = await A.api("GET", `/api/admin/projects/${pid}`);
    main.querySelector("#ws-actions").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      try {
        if (b.dataset.act === "toggle") { await A.setProjectStatus(project, project.status === "completed" ? "in_progress" : "completed"); A.reload(); }
        if (b.dataset.act === "edit" && (await A.editProject(project))) A.reload();
        if (b.dataset.act === "delete" && (await A.deleteProject(project))) A.go("/admin/projects");
      } catch (err) { A.toast(err.message, "err"); }
    });
    if (tab === "journal") return journalPane(pane, project);
    if (tab === "exhibit") return exhibitPane(pane, project);
    // overview
    const entries = await A.api("GET", `/api/admin/e/journals?project_id=${pid}&limit=5`);
    const live = project.exhibit_published && project.status === "completed";
    pane.innerHTML = `<div class="ov-grid">
      <div class="stack">
        <section class="panel pad corners"><h3 class="panel-title">Objective</h3><p style="margin:0">${esc(project.objective || "No objective written yet.")}</p>
          ${project.next_action ? `<p class="small" style="margin:.8rem 0 0"><span class="label">Next action</span><br>${esc(project.next_action)}</p>` : ""}</section>
        <section class="panel pad"><div class="row"><h3 class="panel-title" style="margin:0">Recent journal entries</h3><span class="spacer"></span><a class="btn sm primary" href="/admin/journal/new?project_id=${pid}">${A.icon("plus")} New entry</a></div>
          <div class="list" style="margin-top:.6rem">${entries.map((j) => `<a class="list-item" href="/admin/journal/${j.id}"><span class="t">${esc(j.title)}</span><span class="m">${A.fmtDate(j.entry_date)}</span></a>`).join("") || '<p class="dim small">No entries yet. The journal is where this project’s story gets written, and the source for its AI-generated exhibit.</p>'}</div>
          ${entries.length ? `<a class="btn sm ghost" href="/admin/projects/${pid}/journal" style="margin-top:.5rem">Full journal (${project.journal_count}) →</a>` : ""}</section>
      </div>
      <div class="stack">
        <section class="panel pad"><h3 class="panel-title">Status</h3>
          <dl class="kv"><dt>Status</dt><dd>${statusPill(project)}</dd><dt>Exhibit</dt><dd>${exhibitPill(project)}</dd>
          <dt>Public site</dt><dd>${live ? "Full exhibit live" : project.is_public ? (project.status === "in_progress" ? "Title + In progress" : "Hidden until exhibit published") : "Hidden"}</dd>
          <dt>Started</dt><dd>${A.fmtDate(project.start_date) || "—"}</dd><dt>Target</dt><dd>${A.fmtDate(project.target_date) || "—"}</dd>
          <dt>Stack</dt><dd>${project.technologies.map((t) => `<span class="chip">${esc(t)}</span>`).join(" ") || "—"}</dd></dl>
          ${live ? `<a class="btn sm" style="margin-top:1rem" href="/projects/${esc(project.slug)}" target="_blank" rel="noopener">View public exhibit ↗</a>` : ""}</section>
      </div></div>`;
  });

  /* ---------- project journal pane + AI generation ---------- */
  async function journalPane(pane, project) {
    const pid = project.id;
    const entries = await A.api("GET", `/api/admin/e/journals?project_id=${pid}&limit=500`);
    pane.innerHTML = `<section class="panel pad corners gen-card">
        <div><h3 style="margin:0 0 .3rem">Turn this journal into an exhibit</h3>
        <p class="muted small" style="margin:0">Gemini reads all ${entries.length} entries in order and drafts the exhibition fields. It only uses facts from your journal. The draft stays private until you review and publish it.</p></div>
        <button class="btn primary gen-btn" type="button" id="gen-btn" ${entries.length ? "" : "disabled"}>${A.icon("spark")} Generate Exhibition Content with AI</button>
      </section>
      <div class="toolbar" style="margin-top:1rem"><input type="search" id="jq" placeholder="Search this journal…" aria-label="Search journal"><span class="spacer"></span><a class="btn primary" href="/admin/journal/new?project_id=${pid}">${A.icon("plus")} New entry</a></div>
      <div id="jlist"></div>`;
    const list = pane.querySelector("#jlist");
    const paint = (q = "") => {
      const rows = entries.filter((j) => !q || (j.title + " " + j.content).toLowerCase().includes(q));
      if (!rows.length) return A.empty(list, entries.length ? "No entries match" : "No journal entries yet", "Record progress, decisions, problems, solutions and lessons as you build.");
      list.innerHTML = `<div class="timeline-entries">${rows.map((j) => `
        <article class="panel je-card" data-id="${j.id}"><div class="je-date mono">${A.fmtDate(j.entry_date)}</div>
          <div class="je-body"><h4><a href="/admin/journal/${j.id}">${esc(j.title)}</a></h4><p class="muted small">${esc(A.excerpt(j.content, 220))}</p>
          ${j.tags.length ? `<div class="chips">${j.tags.map((t) => `<span class="chip">#${esc(t)}</span>`).join("")}</div>` : ""}</div>
          <div class="je-actions"><a class="btn sm ghost" href="/admin/journal/${j.id}">Read</a><a class="btn sm ghost" href="/admin/journal/${j.id}/edit">${A.icon("edit")} Edit</a>
          <button class="btn sm icon ghost" data-del aria-label="Delete entry">${A.icon("trash")}</button></div></article>`).join("")}</div>`;
      $$("[data-del]", list).forEach((b) => b.addEventListener("click", async () => {
        const j = entries.find((x) => String(x.id) === b.closest("[data-id]").dataset.id);
        if (await A.deleteEntity("journals", j, j.title)) { entries.splice(entries.indexOf(j), 1); paint(pane.querySelector("#jq").value.toLowerCase()); }
      }));
    };
    pane.querySelector("#jq").addEventListener("input", (e) => paint(e.target.value.toLowerCase()));
    paint();
    pane.querySelector("#gen-btn").addEventListener("click", () => A.generateExhibit(project, entries.length));
  }

  A.generateExhibit = async (project, n) => {
    const ok = await A.confirm(`Gemini will read all ${n} journal entries of “${project.name}” and write a new exhibit DRAFT, replacing the draft text fields (images and links are kept). Nothing becomes public until you publish.`, { confirmLabel: "Generate draft", title: "Generate exhibition content" });
    if (!ok) return;
    const veil = A.h(`<div class="modal-backdrop gen-veil"><div class="gen-status panel corners"><span class="gen-orb"></span><b>Reading the journal…</b><span class="muted small">Analysing ${n} entries chronologically. This can take up to a minute.</span></div></div>`);
    document.body.appendChild(veil);
    try {
      const r = await A.api("POST", `/api/admin/projects/${project.id}/exhibit/generate`);
      sessionStorage.setItem("astra.genNotice", JSON.stringify({ pid: project.id, needs: r.needs_input, model: r.model, entries: r.entries_used }));
      A.toast("Draft generated · review it before publishing", "ok");
      veil.remove();
      A.go(`/admin/projects/${project.id}/exhibit`);
    } catch (e) {
      veil.remove();
      A.modal({ title: "Generation failed", body: `<p>${esc(e.message)}</p><p class="muted small">Your journal is untouched. Try again in a moment.</p>`, actions: [{ label: "OK", kind: "primary", onClick: (_, { close }) => close() }] });
    }
  };

  /* ---------- exhibit editor pane ---------- */
  async function exhibitPane(pane, project) {
    const ex = await A.api("GET", `/api/admin/projects/${project.id}/exhibit`);
    const notice = JSON.parse(sessionStorage.getItem("astra.genNotice") || "null");
    if (notice && notice.pid === project.id) sessionStorage.removeItem("astra.genNotice");
    const needs = new Set(notice && notice.pid === project.id ? notice.needs || [] : []);
    const d = ex.draft;
    const val = (f) => f.kind === "tags" ? (d[f.key] || []).join(", ") : f.kind === "urls" ? (d[f.key] || []).join("\n")
      : f.kind === "links" ? (d[f.key] || []).map((l) => `${l.label} | ${l.url}`).join("\n") : d[f.key] || "";
    const fieldHtml = (f) => {
      const id = `x-${f.key}`, flag = needs.has(f.key) ? '<span class="badge b-draft">needs your input</span>' : "";
      const big = ["md"].includes(f.kind), multi = ["urls", "links"].includes(f.kind);
      const input = big || multi ? `<textarea id="${id}" name="${f.key}" rows="${big ? 5 : 3}" ${big ? 'class="mono-soft"' : ""}>${esc(val(f))}</textarea>`
        : `<input id="${id}" name="${f.key}" type="${f.kind === "url" ? "url" : "text"}" value="${esc(val(f))}">`;
      return `<div class="field ${big || multi || f.key === "tagline" || f.key === "name" ? "full" : ""}" data-field="${f.key}"><label for="${id}">${esc(f.label)} ${flag}</label>${input}${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ""}</div>`;
    };
    const groups = [["Basics", ["name", "tagline", "category", "technologies"]],
      ["Story", ["description", "problem", "features", "architecture", "process", "challenges", "solutions", "learnings", "achievements", "future"]],
      ["Media & links", ["cover_image", "gallery", "github_url", "live_url", "youtube_url", "links"]]];
    const byKey = Object.fromEntries(ex.fields.map((f) => [f.key, f]));
    const live = ex.project.exhibit_published && ex.project.status === "completed";
    pane.innerHTML = `
      ${notice && notice.pid === project.id ? `<div class="gen-banner panel"><b>${A.icon("spark")} AI draft ready.</b> Generated from ${notice.entries} journal entries (${esc(notice.model || "Gemini")}). Review every field. ${needs.size ? `Fields marked <span class="badge b-draft">needs your input</span> had no supporting journal content.` : ""} Nothing is public yet.</div>` : ""}
      <div class="ex-status panel pad">
        <div><span class="label">Public exhibit</span><div class="row wrap" style="margin-top:.3rem">${ex.project.exhibit_published ? '<span class="badge b-published">Published</span>' : '<span class="badge b-private">Not published</span>'}${statusPill(ex.project)}
          ${ex.draft_differs ? '<span class="badge b-draft">Draft has unpublished changes</span>' : ""}</div>
          <p class="dim small" style="margin:.5rem 0 0">${ex.project.status === "in_progress" ? "This project is in progress, so visitors only see its title and an “In progress” badge, even after publishing." : live ? "Visitors can open the full exhibit." : "Publish to make the exhibit visible."}${ex.generated_at ? ` · Last AI draft ${A.fmtDate(ex.generated_at)}` : ""}</p></div>
        <div class="row wrap"><button class="btn" type="button" data-x="regen">${A.icon("spark")} ${ex.generated_at ? "Regenerate" : "Generate"} with AI</button>
          ${ex.project.exhibit_published ? '<button class="btn" type="button" data-x="unpublish">Unpublish</button>' : ""}
          ${live ? `<a class="btn ghost" href="/projects/${esc(ex.project.slug)}" target="_blank" rel="noopener">View public ↗</a>` : ""}</div>
      </div>
      <form id="ex-form" novalidate>${groups.map(([g, keys]) => `<section class="panel pad"><h3 class="panel-title">${g}</h3><div class="form-grid">${keys.map((k) => fieldHtml(byKey[k])).join("")}</div></section>`).join("")}</form>
      <div class="ex-savebar panel"><span class="save-state" id="ex-state">All changes saved</span><span class="spacer"></span>
        ${ex.draft_differs || ex.generated_at ? '<button class="btn ghost" type="button" data-x="discard">Discard draft</button>' : ""}
        <button class="btn" type="button" data-x="save">Save draft</button><button class="btn primary" type="button" data-x="publish">Publish exhibit</button></div>`;
    const form = pane.querySelector("#ex-form"), st = pane.querySelector("#ex-state");
    let dirty = false;
    A.guard = () => dirty;
    form.addEventListener("input", () => { dirty = true; st.className = "save-state dirty"; st.textContent = "Unsaved changes"; });
    const data = () => Object.fromEntries(ex.fields.map((f) => [f.key, form.elements[f.key].value]));
    const act = async (x) => {
      try {
        if (x === "save") { await A.api("PUT", `/api/admin/projects/${project.id}/exhibit`, data()); dirty = false; A.toast("Draft saved", "ok"); return A.reload(); }
        if (x === "publish") {
          const msg = project.status === "completed" ? "Publish this exhibit? It becomes visible to visitors immediately." : "Publish this exhibit? The project is still in progress, so visitors only see its title until you mark it completed.";
          if (!(await A.confirm(msg, { confirmLabel: "Publish" }))) return;
          await A.api("POST", `/api/admin/projects/${project.id}/exhibit/publish`, data()); dirty = false; A.toast("Exhibit published", "ok"); return A.reload();
        }
        if (x === "unpublish") { await A.api("POST", `/api/admin/projects/${project.id}/exhibit/unpublish`); A.toast("Exhibit unpublished", "ok"); return A.reload(); }
        if (x === "discard") {
          if (!(await A.confirm("Discard the draft and reload the currently published content?", { danger: true, confirmLabel: "Discard" }))) return;
          await A.api("POST", `/api/admin/projects/${project.id}/exhibit/discard`); dirty = false; return A.reload();
        }
        if (x === "regen") {
          if (dirty && !(await A.confirm("You have unsaved edits. Regenerating replaces the text fields. Continue?", { danger: true, confirmLabel: "Regenerate" }))) return;
          dirty = false;
          return A.generateExhibit(project, ex.journal_entries);
        }
      } catch (e) { A.showErrors(form, e); A.toast(e.message, "err"); }
    };
    pane.addEventListener("click", (e) => { const b = e.target.closest("[data-x]"); if (b) act(b.dataset.x); });
    document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); act("save"); } }, { signal: A.signal });
  }
})();
