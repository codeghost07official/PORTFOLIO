/* Settings: profile, appearance, visibility, chatbot, login, defaults, backup/export, index maintenance. */
(function () {
  "use strict";
  const A = window.ASTRA, esc = A.esc, $ = A.$, $$ = A.$$;

  const sw = (name, label, on) => `<label class="switch"><input type="checkbox" name="${name}" ${on ? "checked" : ""}><span class="track"></span>${esc(label)}</label>`;
  const inp = (name, label, val, type = "text", extra = "") => `<div class="field ${extra}" data-field="${name}"><label>${esc(label)}</label><input type="${type}" name="${name}" value="${esc(val ?? "")}"></div>`;
  const ta = (name, label, val, rows = 3, hint = "", extra = "full") => `<div class="field ${extra}" data-field="${name}"><label>${esc(label)}</label><textarea name="${name}" rows="${rows}">${esc(val ?? "")}</textarea>${hint ? `<span class="hint">${esc(hint)}</span>` : ""}</div>`;
  const sel = (name, label, val, opts) => `<div class="field" data-field="${name}"><label>${esc(label)}</label><select name="${name}">${opts.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(val) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>`;
  const section = (id, title, inner, save = true) => `<section class="panel pad" id="s-${id}"><h3 class="panel-title">${esc(title)}</h3><form data-group="${id}" novalidate>${inner}${save ? '<div class="row" style="margin-top:1rem"><span class="spacer"></span><button class="btn primary" type="submit">Save</button></div>' : ""}</form></section>`;

  async function render(main) {
    const root = main.querySelector("#settings-root");
    let data;
    try { data = await A.api("GET", "/api/admin/settings"); } catch (e) { return A.errorState(root, e, () => render(main)); }
    const s = data.settings, sys = data.system, p = s.profile, ai = sys.ai;
    const st = (l, v, cls = "") => `<div class="status-card"><div class="l">${esc(l)}</div><div class="v ${cls}">${v}</div></div>`;
    root.innerHTML = [
      `<section class="panel pad" id="s-system"><h3 class="panel-title">System status</h3><div class="status-grid">
        ${st("Database", esc(sys.database), sys.turso ? "ok" : "warn")}
        ${st("Persistence", sys.turso ? "Turso cloud" : "Turso NOT configured", sys.turso ? "ok" : "bad")}
        ${st("Gemini API", ai.configured ? "Configured" : "Not configured", ai.configured ? "ok" : "bad")}
        ${st("Primary model", esc(s.assistant.model || ai.model))}
        ${st("Fallback model", esc(ai.fallback))}
        ${st("Embeddings", ai.embeddings ? esc(ai.embedding_model) : "Lexical only (BM25)", ai.embeddings ? "ok" : "warn")}
        ${st("Memory index", `${sys.index.chunks} chunks · ${sys.index.embedded} embedded`)}
        ${st("Environment", esc(sys.environment))}
      </div>
      <div class="row wrap" style="margin-top:1rem"><button class="btn primary" type="button" data-diag>Run diagnostics</button><span class="hint">Connection, write/read self-test, credentials and Gemini model availability. Nothing permanent is written.</span></div>
      <div data-diag-out style="margin-top:1rem"></div>${sys.warnings.length ? `<div class="error-state" style="margin-top:1rem"><b>Configuration warnings</b><ul style="margin:.4rem 0 0;padding-left:1.2rem">${sys.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}</section>`,

      section("profile", "Profile", `<div class="form-grid">
        ${inp("name", "Name", p.name)}${inp("title", "Title", p.title)}
        ${ta("intro", "Introduction (hero)", p.intro, 2)}
        ${ta("about", "About (Markdown)", p.about, 6)}
        <div class="field full" data-field="avatar"><label>Profile image URL</label><div class="row"><input type="url" name="avatar" value="${esc(p.avatar)}" placeholder="https://… or upload"><label class="btn sm" style="cursor:pointer">Upload<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" class="sr-only" data-avatar></label></div></div>
        ${inp("location", "Location (optional)", p.location)}${inp("email", "Primary email", p.email, "email")}
        ${inp("email2", "Secondary email", p.email2, "email")}${inp("phone", "Phone", p.phone, "tel")}
        ${inp("github", "GitHub profile", p.github, "url")}${inp("youtube", "YouTube channel", p.youtube, "url")}
        ${inp("linkedin", "LinkedIn", p.linkedin, "url")}${inp("twitter", "X / Twitter", p.twitter, "url")}
        ${inp("website", "Website", p.website, "url")}${inp("footer_note", "Footer note", p.footer_note)}
        ${ta("interests", "Interests & domains (comma separated)", p.interests.join(", "), 2)}
        ${ta("skills", "Skills — one group per line: Group: item, item", p.skills.map((g) => `${g.group}: ${g.items.join(", ")}`).join("\n"), 5)}
        ${ta("achievements", "Achievements — one per line: Title | detail | date", p.achievements.map((a) => [a.title, a.detail, a.date].join(" | ")).join("\n"), 4)}
        ${ta("journey", "Journey — one per line: Year | Title | detail", p.journey.map((j) => [j.year, j.title, j.detail].join(" | ")).join("\n"), 4)}
      </div>`),

      section("appearance", "Appearance & public visibility", `<div class="form-grid">
        ${sel("accent", "Theme accent", s.appearance.accent, [["cyan", "Cyan (default)"], ["blue", "Electric blue"], ["violet", "Violet"], ["emerald", "Emerald"], ["amber", "Amber"]])}
        ${sel("effects", "Visual effects", s.appearance.effects, [["full", "Full — 3D objects, particles, scanlines"], ["lite", "Lite — fewer objects"], ["off", "Off — static (also auto for reduced motion)"]])}
        ${inp("hero_kicker", "Hero kicker text", s.appearance.hero_kicker, "text", "full")}
        <div class="field full"><label>Public sections</label><div class="stack">
          ${sw("show_interests", "Interests & domains", s.visibility.show_interests)}${sw("show_skills", "Technologies & skills", s.visibility.show_skills)}
          ${sw("show_achievements", "Achievements", s.visibility.show_achievements)}${sw("show_journey", "Development journey", s.visibility.show_journey)}
          ${sw("show_contact", "Contact section", s.visibility.show_contact)}${sw("show_chatbot", "Floating AI guide", s.visibility.show_chatbot)}
        </div></div></div>`),

      section("chatbot", "Public AI guide", `<div class="form-grid">
        <div class="field full">${sw("public_enabled", "Public AI guide enabled", s.chatbot.public_enabled)}</div>
        ${ta("public_greeting", "Public greeting", s.chatbot.public_greeting, 2)}
        ${inp("public_daily_limit", "Public daily message cap (0 = env default " + sys.limits.PUBLIC_CHAT_GLOBAL_DAY + ")", s.chatbot.public_daily_limit, "number")}
        ${inp("public_model", "Public model override (blank = env)", s.chatbot.public_model)}
        ${inp("public_temperature", "Public temperature (0–1.5)", s.chatbot.public_temperature, "number")}
        <div class="field full"><div class="row wrap"><button class="btn sm" type="button" data-models>List models available to my API key</button><span class="hint">Per-IP limits: ${sys.limits.PUBLIC_CHAT_PER_IP_10MIN}/10 min, ${sys.limits.PUBLIC_CHAT_PER_IP_DAY}/day · max ${sys.limits.PUBLIC_CHAT_MAX_CHARS} chars</span></div><div data-model-list class="chips" style="margin-top:.6rem"></div></div>
      </div>`),

      section("login", "Login & security", `<div class="form-grid">
        ${sel("entry_point", "Discreet login entry point", s.login.entry_point, [["footer_glyph", "Tiny glyph in the footer"], ["logo_dblclick", "Double-click the ASTRA logo"], ["keyboard", "Type “astra” anywhere on the site"], ["none", "None — use the URL directly"]])}
        <div class="field"><label>Login URL</label><input value="${esc(sys.login_path)}" readonly><span class="hint">Change with the ADMIN_LOGIN_PATH environment variable.</span></div>
        <div class="field full"><p class="muted small" style="margin:0">Sessions last ${sys.session_hours}h (idle timeout ${sys.idle_minutes} min). Login is rate-limited and every admin endpoint is protected server-side — the hidden entry point is cosmetic, not security.</p></div>
        <div class="field full"><label>Change login PIN</label>
          <div class="pin-change" data-pin-change>
            <input type="password" inputmode="numeric" maxlength="4" pattern="[0-9]{4}" placeholder="Current" autocomplete="current-password" data-pin="current" aria-label="Current PIN">
            <input type="password" inputmode="numeric" maxlength="4" pattern="[0-9]{4}" placeholder="New" autocomplete="new-password" data-pin="new" aria-label="New PIN">
            <input type="password" inputmode="numeric" maxlength="4" pattern="[0-9]{4}" placeholder="Repeat" autocomplete="new-password" data-pin="confirm" aria-label="Repeat new PIN">
            <button class="btn" type="button" data-pin-save>Update PIN</button>
          </div>
          <span class="hint">Forgot it? Sign out and use “Forgot PIN?” on the login page with your admin password.</span></div>
        <div class="field full"><button class="btn danger" type="button" data-revoke style="align-self:flex-start">Sign out all other sessions</button></div>
      </div>`),

      section("defaults", "Default settings for new projects", `<div class="form-grid">
        ${sel("status", "Default status", s.defaults.status, ["idea", "planning", "active", "paused"].map((v) => [v, A.label(v)]))}
        ${sel("priority", "Default priority", s.defaults.priority, ["low", "medium", "high", "critical"].map((v) => [v, A.label(v)]))}
        <div class="field full"><div class="stack">${sw("is_public", "New projects are public", s.defaults.is_public)}${sw("show_journal", "Show public journal entries", s.defaults.show_journal)}</div></div>
      </div>`),

      `<section class="panel pad" id="s-data"><h3 class="panel-title">Backup & data</h3>
        <p class="muted small">Your history is never locked to one provider. The JSON backup contains every table (except rate-limit logs and the rebuildable search index).</p>
        <div class="row wrap"><a class="btn primary" href="/api/admin/export/json?ai=1">Full JSON backup</a><a class="btn" href="/api/admin/export/json?ai=0">JSON without AI chats</a><a class="btn" href="/api/admin/export/journals.md">Journals as Markdown</a></div>
        <h4 class="label" style="margin-top:1.2rem">CSV exports</h4>
        <div class="row wrap">${["projects", "tasks", "milestones", "journals", "notes", "resources", "bugs", "ideas", "snippets"].map((t) => `<a class="btn sm" href="/api/admin/export/csv/${t}">${A.label(t)}</a>`).join("")}</div>
        <h4 class="label" style="margin-top:1.2rem">AI memory index</h4>
        <div class="row wrap"><button class="btn sm" type="button" data-reindex>Rebuild index</button><button class="btn sm" type="button" data-embed ${ai.embeddings ? "" : "disabled"}>Embed pending chunks</button><span class="hint" data-index-stat>${sys.index.chunks} chunks · ${sys.index.embedded} embedded</span></div>
        ${sys.sample_project ? `<h4 class="label" style="margin-top:1.2rem">Sample data</h4><button class="btn sm danger" type="button" data-sample>Remove sample project</button>` : ""}
      </section>`,
    ].join("");

    // one settings page per route: keep only the requested section
    const map = { system: "s-system", profile: "s-profile", appearance: "s-appearance", chatbot: "s-chatbot",
      security: "s-login", data: "s-data" };
    const wanted = (root.dataset.sections || main.dataset.section || "system").split(",").map((k) => map[k]);
    root.querySelectorAll(":scope > section[id^='s-']").forEach((sec) => { if (!wanted.includes(sec.id)) sec.remove(); });
    if (wanted.length === 1) root.querySelectorAll(":scope > section > .panel-title").forEach((h) => h.classList.add("hidden"));

    /* diagnostics (system page) */
    const diag = root.querySelector("[data-diag]");
    diag?.addEventListener("click", async () => {
      const out = root.querySelector("[data-diag-out]");
      diag.disabled = true;
      out.innerHTML = '<span class="spinner"></span> Running checks against your real database and Gemini…';
      try {
        const checks = await A.api("GET", "/api/admin/diagnostics");
        out.innerHTML = '<div class="list">' + checks.map((c) => `<div class="list-item" style="align-items:flex-start"><span class="badge ${c.ok && !c.warn ? "b-done" : c.ok || c.warn ? "b-paused" : "b-blocked"}">${c.ok && !c.warn ? "OK" : c.ok || c.warn ? "WARN" : "FAIL"}</span><span class="t" style="white-space:normal"><b>${esc(c.name)}</b> — ${esc(c.detail)}${(!c.ok || c.warn) && c.hint ? `<br><span class="muted small">${esc(c.hint)}</span>` : ""}</span></div>`).join("") + "</div>";
      } catch (e) { out.innerHTML = `<div class="error-state">${esc(e.message)}</div>`; }
      diag.disabled = false;
    });

    /* save handlers */
    const collect = {
      profile: (f) => ({
        ...Object.fromEntries(["name", "title", "intro", "about", "avatar", "location", "email", "email2", "phone", "github", "youtube", "linkedin", "twitter", "website", "footer_note"].map((k) => [k, f.elements[k].value])),
        interests: f.elements.interests.value.split(",").map((x) => x.trim()).filter(Boolean),
        skills: f.elements.skills.value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const i = l.indexOf(":"); return i < 0 ? { group: l, items: [] } : { group: l.slice(0, i).trim(), items: l.slice(i + 1).split(",").map((x) => x.trim()).filter(Boolean) }; }),
        achievements: f.elements.achievements.value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [title, detail = "", date = ""] = l.split("|").map((x) => x.trim()); return { title, detail, date }; }),
        journey: f.elements.journey.value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [year, title = "", detail = ""] = l.split("|").map((x) => x.trim()); return { year, title, detail }; }),
      }),
      appearance: (f) => [{ accent: f.elements.accent.value, effects: f.elements.effects.value, hero_kicker: f.elements.hero_kicker.value },
        Object.fromEntries(["show_interests", "show_skills", "show_achievements", "show_journey", "show_contact", "show_chatbot"].map((k) => [k, f.elements[k].checked]))],
      chatbot: (f) => ({
        ...s.chatbot, public_enabled: f.elements.public_enabled.checked, public_greeting: f.elements.public_greeting.value,
        public_daily_limit: Number(f.elements.public_daily_limit.value || 0), public_model: f.elements.public_model.value.trim(),
        public_temperature: Number(f.elements.public_temperature.value),
      }),
      login: (f) => ({ entry_point: f.elements.entry_point.value }),
      defaults: (f) => ({ status: f.elements.status.value, priority: f.elements.priority.value, is_public: f.elements.is_public.checked, show_journal: f.elements.show_journal.checked }),
    };
    $$("form[data-group]", root).forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const g = f.dataset.group;
      const btn = f.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        if (g === "appearance") {
          const [app, vis] = collect.appearance(f);
          await A.api("PUT", "/api/admin/settings/appearance", app);
          await A.api("PUT", "/api/admin/settings/visibility", vis);
        } else await A.api("PUT", `/api/admin/settings/${g}`, collect[g](f));
        A.showErrors(f, null);
        A.toast("Settings saved", "ok");
      } catch (err) {
        A.showErrors(f, err);
        A.toast(err.message, "err");
      }
      btn.disabled = false;
    }));

    $("[data-avatar]", root)?.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      try {
        const { url } = await A.api("POST", "/api/admin/media", fd);
        root.querySelector('[name="avatar"]').value = url;
        A.toast("Uploaded — remember to save the profile", "ok");
      } catch (err) { A.toast(err.message, "err"); }
    });
    $("[data-models]", root)?.addEventListener("click", async () => {
      const box = $("[data-model-list]", root);
      box.innerHTML = '<span class="spinner"></span>';
      try {
        const models = (await A.api("GET", "/api/admin/ai/models")).filter((m) => m.generate);
        box.innerHTML = models.map((m) => `<button type="button" class="chip" data-m="${esc(m.id)}" title="${esc(m.label)}">${esc(m.id)}</button>`).join("") || "No models returned.";
        $$("[data-m]", box).forEach((b) => b.addEventListener("click", () => { root.querySelector('[name="public_model"]').value = b.dataset.m; A.toast(`Set public guide model to ${b.dataset.m}. Save to apply`); }));
      } catch (err) { box.innerHTML = `<span class="small" style="color:var(--bad)">${esc(err.message)}</span>`; }
    });
    $("[data-pin-save]", root)?.addEventListener("click", async (e) => {
      const box = $("[data-pin-change]", root), val = (k) => box.querySelector(`[data-pin="${k}"]`).value.trim();
      const data = { current: val("current"), new: val("new"), confirm: val("confirm") };
      if (![data.current, data.new, data.confirm].every((v) => /^\d{4}$/.test(v))) return A.toast("Each PIN must be exactly 4 digits", "bad");
      e.target.disabled = true;
      try {
        await A.api("POST", "/api/admin/security/pin", data);
        box.querySelectorAll("input").forEach((i) => (i.value = ""));
        A.toast("PIN updated", "ok");
      } catch (err) { A.toast(err.errors ? Object.values(err.errors)[0] : err.message, "bad"); }
      finally { e.target.disabled = false; }
    });
    $("[data-revoke]", root)?.addEventListener("click", async () => {
      if (!(await A.confirm("Invalidate every session except this one?", { confirmLabel: "Revoke" }))) return;
      const r = await A.api("POST", "/api/admin/sessions/revoke");
      if (r.csrf) document.querySelector('meta[name="csrf-token"]').content = r.csrf;
      A.toast("All other sessions revoked", "ok");
    });
    $("[data-reindex]", root)?.addEventListener("click", async (e) => {
      e.target.disabled = true;
      try {
        const r = await A.api("POST", "/api/admin/index/rebuild");
        $("[data-index-stat]", root).textContent = `${r.stats.chunks} chunks · ${r.stats.embedded} embedded (embedding continues in background)`;
        A.toast("Index rebuilt", "ok");
      } catch (err) { A.toast(err.message, "err"); }
      e.target.disabled = false;
    });
    $("[data-embed]", root)?.addEventListener("click", async (e) => {
      e.target.disabled = true;
      try {
        const r = await A.api("POST", "/api/admin/index/embed");
        $("[data-index-stat]", root).textContent = `${r.stats.chunks} chunks · ${r.stats.embedded} embedded`;
        A.toast(`Embedded ${r.embedded} chunks`, "ok");
      } catch (err) { A.toast(err.message, "err"); }
      e.target.disabled = false;
    });
    $("[data-sample]", root)?.addEventListener("click", async () => {
      if (!(await A.confirm("Delete the sample ASTRA project and everything attached to it?", { danger: true, confirmLabel: "Remove" }))) return;
      await A.api("DELETE", "/api/admin/sample-data");
      A.toast("Sample data removed", "ok");
      A.meta(true);
      render(main);
    });

  }

  A.page("profile", (main) => render(main));
  A.page("system", (main) => render(main));
})();
