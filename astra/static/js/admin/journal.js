/* Project journal editor + a reusable Markdown toolbar (also used by personal Journaling). */
(function () {
  "use strict";
  const A = window.ASTRA, esc = A.esc, $$ = A.$$;

  /** Bind formatting buttons ([data-md]) and shortcuts to a textarea. */
  A.mdToolbar = (root, ta, onChange) => {
    const changed = () => onChange && onChange();
    const wrap = (before, after = before, ph = "text") => {
      const s = ta.selectionStart, e = ta.selectionEnd, sel = ta.value.slice(s, e) || ph;
      ta.setRangeText(before + sel + after, s, e, "end");
      ta.selectionStart = s + before.length;
      ta.selectionEnd = s + before.length + sel.length;
      ta.focus();
      changed();
    };
    const linePrefix = (prefix) => {
      const s = ta.selectionStart, e = ta.selectionEnd, start = ta.value.lastIndexOf("\n", s - 1) + 1;
      const lines = ta.value.slice(start, e).split("\n").map((l, i) => (typeof prefix === "function" ? prefix(i) : prefix) + l);
      ta.setRangeText(lines.join("\n"), start, e, "end");
      ta.focus();
      changed();
    };
    const insert = (text) => {
      const s = ta.selectionStart;
      ta.setRangeText((s > 0 && ta.value[s - 1] !== "\n" ? "\n\n" : "") + text, s, ta.selectionEnd, "end");
      ta.focus();
      changed();
    };
    const ACTIONS = {
      h2: () => linePrefix("## "), h3: () => linePrefix("### "), bold: () => wrap("**"), italic: () => wrap("_"), strike: () => wrap("~~"),
      code: () => wrap("`", "`", "code"), ul: () => linePrefix("- "), ol: () => linePrefix((i) => `${i + 1}. `), task: () => linePrefix("- [ ] "),
      quote: () => linePrefix("> "), link: () => wrap("[", "](https://)", "link text"), image: () => wrap("![", "](https://)", "alt text"),
      codeblock: () => wrap("\n```python\n", "\n```\n", "code here"), hr: () => insert("---\n"),
      table: () => insert("| Column | Column |\n|--------|--------|\n| Value  | Value  |\n"),
    };
    $$("[data-md]", root).forEach((b) => b.addEventListener("click", () => ACTIONS[b.dataset.md]()));
    ta.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey) {
        const k = e.key.toLowerCase();
        if (k === "b") { e.preventDefault(); ACTIONS.bold(); }
        if (k === "i") { e.preventDefault(); ACTIONS.italic(); }
        if (k === "k") { e.preventDefault(); e.stopPropagation(); ACTIONS.link(); }
      }
      if (e.key === "Tab") { e.preventDefault(); ta.setRangeText("  ", ta.selectionStart, ta.selectionEnd, "end"); changed(); }
    });
  };

  /* ======================= PROJECT JOURNAL EDITOR ======================= */
  A.page("journal-editor", async (main, signal) => {
    const pid = Number(main.dataset.projectId);
    let id = main.dataset.entryId ? Number(main.dataset.entryId) : null;
    let dirty = false, saving = false, saveTimer = null, previewTimer = null;
    const $ = (s) => main.querySelector(s);
    const title = $("#je-title"), content = $("#je-content"), preview = $("#je-preview"), state = $("#je-state");
    const date = $("#je-date"), tags = $("#je-tags");
    date.value = A.today();
    const setState = (cls, text) => { state.className = `save-state ${cls}`; state.textContent = text; };
    const words = () => ($("#je-words").textContent = `${(content.value.match(/\S+/g) || []).length} words`);
    if (id) {
      const j = await A.api("GET", `/api/admin/e/journals/${id}`);
      title.value = j.title; content.value = j.content || ""; date.value = j.entry_date; tags.value = j.tags.join(", ");
      setState("", `Saved ${A.rel(j.updated_at)}`);
      $("#je-delete").classList.remove("hidden");
    }
    words();
    A.guard = () => dirty;
    const save = async (manual = false) => {
      if (saving) { saveTimer = setTimeout(() => save(manual), 600); return; }
      if (!manual && !dirty) return;
      if (!id && !title.value.trim() && !content.value.trim()) return;
      saving = true;
      setState("saving", "Saving…");
      try {
        const data = { title: title.value.trim() || "Untitled entry", content: content.value, project_id: pid,
          entry_date: date.value || A.today(), tags: tags.value, visibility: "private", status: "draft" };
        const saved = id ? await A.api("PUT", `/api/admin/e/journals/${id}`, data) : await A.api("POST", "/api/admin/e/journals", data);
        if (!id) {
          id = saved.id;
          main.dataset.entryId = id;
          history.replaceState(null, "", `/admin/journal/${id}/edit`);
          $("#je-delete").classList.remove("hidden");
        }
        dirty = false;
        document.getElementById("crumb-title") && (document.getElementById("crumb-title").textContent = saved.title);
        setState("", `Saved at ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`);
        if (manual) A.toast("Entry saved", "ok");
      } catch (e) {
        setState("error", "Save failed: " + e.message);
        if (manual) A.toast(e.message, "err");
      } finally { saving = false; }
    };
    const renderPreview = async () => {
      if ($("#je-panes").classList.contains("write")) return;
      try {
        const { html } = await A.api("POST", "/api/admin/markdown", { text: content.value });
        preview.innerHTML = html || '<p class="dim">Preview appears here.</p>';
        A.enhanceMarkdown(preview.parentElement);
      } catch (_) { /* keep last preview */ }
    };
    const changed = () => {
      dirty = true;
      setState("dirty", "Unsaved changes");
      words();
      clearTimeout(saveTimer); saveTimer = setTimeout(() => save(false), 2500);
      clearTimeout(previewTimer); previewTimer = setTimeout(renderPreview, 450);
    };
    [title, content].forEach((el) => el.addEventListener("input", changed));
    [date, tags].forEach((el) => el.addEventListener("change", changed));
    A.mdToolbar(main, content, changed);
    const setMode = (mode) => {
      $("#je-panes").className = `editor-panes ${mode === "split" ? "" : mode}`;
      $$("[data-mode]", main).forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
      try { localStorage.setItem("astra.jmode", mode); } catch (_) { /* ignore */ }
      renderPreview();
    };
    $$("[data-mode]", main).forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
    let mode = "split";
    try { mode = localStorage.getItem("astra.jmode") || "split"; } catch (_) { /* ignore */ }
    setMode(mode);
    $("#je-save").addEventListener("click", () => save(true));
    $("#je-delete").addEventListener("click", async () => {
      if (!(await A.confirm("Delete this journal entry permanently? This cannot be undone.", { danger: true, confirmLabel: "Delete" }))) return;
      await A.api("DELETE", `/api/admin/e/journals/${id}`);
      dirty = false;
      A.toast("Entry deleted", "ok");
      A.go(`/admin/projects/${pid}/journal`);
    });
    document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(true); } }, { signal, capture: true });
    signal.addEventListener("abort", () => { clearTimeout(saveTimer); if (dirty) save(true); });
    (id ? content : title).focus();
  });

  A.page("journal-read", () => {});
  void esc;
})();
