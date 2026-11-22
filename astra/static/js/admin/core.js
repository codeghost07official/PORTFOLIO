/* ASTRA personal OS — admin runtime.
   - client-side router (fetch page → swap #main/crumbs/sidebar → pushState) so the HUD persists
   - page modules: A.page("name", (main, signal) => {...}) run for <main data-init="name">
   - shared helpers: api, modals, forms, toasts, charts */
(function () {
  "use strict";
  const A = window.ASTRA;
  const $ = (A.$ = (s, r = document) => r.querySelector(s));
  const $$ = (A.$$ = (s, r = document) => Array.from(r.querySelectorAll(s)));
  const esc = A.esc;

  /* ---------- local dates (personal data follows Sir's own calendar day) ---------- */
  const pad = (n) => String(n).padStart(2, "0");
  A.today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
  A.nowLocal = () => { const d = new Date(); return `${A.today()}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  A.addDays = (iso, n) => { const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };

  /* every admin API call carries the browser's local date */
  const rawApi = A.api;
  A.api = (method, url, data, opts = {}) => {
    if (url.startsWith("/api/admin")) {
      const u = new URL(url, location.origin);
      if (!u.searchParams.has("today")) u.searchParams.set("today", A.today());
      url = u.pathname + u.search;
    }
    return rawApi(method, url, data, opts);
  };

  A.h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
  A.debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  A.icon = (name) => {
    const P = {
      edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4z"/>',
      trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
      plus: '<path d="M12 5v14M5 12h14"/>', check: '<path d="M20 6 9 17l-5-5"/>',
      ext: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
      close: '<path d="M18 6 6 18M6 6l12 12"/>', stop: '<rect x="6" y="6" width="12" height="12" rx="1"/>',
      play: '<path d="m7 4 13 8-13 8z"/>', spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
      left: '<path d="m15 18-6-6 6-6"/>', right: '<path d="m9 18 6-6-6-6"/>', eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
      book: '<path d="M4 19.5V5a2 2 0 0 1 2-2h14v16H6.5A2.5 2.5 0 0 0 4 21.5zM4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>',
      restore: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"/>', pause: '<path d="M8 5v14M16 5v14"/>',
    };
    return `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ""}</svg>`;
  };

  /* ---------- formatting ---------- */
  A.label = (v) => (A._labels && A._labels[v]) || String(v || "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  A.badge = (v, text) => (v ? `<span class="badge b-${esc(v)}">${esc(text || A.label(v))}</span>` : "");
  A.fmtDate = (v, opts) => {
    if (!v) return "";
    const d = new Date(v.length === 10 ? v + "T00:00:00" : v);
    return isNaN(d) ? v : d.toLocaleDateString(undefined, opts || { day: "numeric", month: "short", year: "numeric" });
  };
  A.fmtTime = (v) => { const d = new Date(v.length === 16 ? v + ":00" : v); return isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };
  A.rel = (v) => {
    if (!v) return "";
    const s = (Date.now() - new Date(v).getTime()) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
    return A.fmtDate(v);
  };
  A.isLate = (d) => d && d < A.today();
  A.excerpt = (s, n = 160) => {
    const t = String(s || "").replace(/```[\s\S]*?```/g, " ").replace(/[#>*_`~|]/g, "").replace(/\s+/g, " ").trim();
    return t.length > n ? t.slice(0, n - 1) + "…" : t;
  };
  A.params = () => new URLSearchParams(location.search);
  A.qs = (obj) => {
    const p = new URLSearchParams();
    Object.entries(obj).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && p.set(k, v));
    const s = p.toString();
    return s ? `?${s}` : "";
  };
  A.main = () => $("#main");

  let metaPromise = null;
  A.meta = (fresh = false) => {
    if (!metaPromise || fresh) metaPromise = A.api("GET", "/api/admin/meta").then((m) => { A._labels = m.labels; return m; });
    return metaPromise;
  };

  /* ---------- states ---------- */
  A.loading = (el, rows = 3) => { el.innerHTML = Array.from({ length: rows }, () => '<div class="skeleton" style="height:56px;margin-bottom:10px"></div>').join(""); };
  A.empty = (el, title, text = "", actionHtml = "") => {
    el.innerHTML = `<div class="empty"><div class="empty-icon">${A.icon("plus")}</div><h4>${esc(title)}</h4><p>${esc(text)}</p>${actionHtml}</div>`;
  };
  A.errorState = (el, err, retry) => {
    el.innerHTML = `<div class="error-state"><b>Could not load.</b> ${esc(err.message || err)} ${retry ? '<button class="btn sm" type="button">Retry</button>' : ""}</div>`;
    retry && el.querySelector("button").addEventListener("click", retry);
  };

  /* ---------- modal ---------- */
  A.modal = ({ title, body, wide = false, actions = [], onClose, className = "" }) => {
    const prev = document.activeElement;
    const back = A.h(`<div class="modal-backdrop" role="presentation">
      <div class="modal ${wide ? "wide" : ""} ${className}" role="dialog" aria-modal="true" aria-label="${esc(title || "Dialog")}">
        ${title ? `<div class="modal-head"><h3>${esc(title)}</h3><span class="spacer"></span><button class="btn icon ghost sm" data-x aria-label="Close">${A.icon("close")}</button></div>` : ""}
        <div class="modal-body"></div>${actions.length ? '<div class="modal-foot"></div>' : ""}</div></div>`);
    const bodyEl = back.querySelector(".modal-body");
    if (typeof body === "string") bodyEl.innerHTML = body; else if (body) bodyEl.appendChild(body);
    let closed = false;
    const close = () => {
      if (closed) return;
      closed = true;
      back.classList.add("closing");
      setTimeout(() => back.remove(), 170);
      document.removeEventListener("keydown", onKey);
      onClose && onClose();
      prev && prev.focus && prev.focus();
    };
    const onKey = (e) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const f = $$('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])', back).filter((x) => !x.disabled && x.offsetParent);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    const foot = back.querySelector(".modal-foot");
    actions.forEach((a) => {
      const b = A.h(`<button class="btn ${a.kind || ""}" type="${a.submit ? "submit" : "button"}">${esc(a.label)}</button>`);
      if (a.form) b.setAttribute("form", a.form);
      b.addEventListener("click", (e) => a.onClick && a.onClick(e, { close, button: b }));
      foot.appendChild(b);
    });
    back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
    back.querySelector("[data-x]")?.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.appendChild(back);
    setTimeout(() => (back.querySelector("[autofocus], input:not([type=hidden]), textarea, select, .modal-foot .btn") || back).focus(), 30);
    return { el: back, body: bodyEl, close };
  };
  A.confirm = (message, { title = "Please confirm", danger = false, confirmLabel = "Confirm" } = {}) =>
    new Promise((resolve) => {
      let done = false;
      A.modal({
        title, body: `<p style="margin:0">${esc(message)}</p>`, onClose: () => !done && resolve(false),
        actions: [
          { label: "Cancel", kind: "ghost", onClick: (_, { close }) => close() },
          { label: confirmLabel, kind: danger ? "danger" : "primary", onClick: (_, { close }) => { done = true; resolve(true); close(); } },
        ],
      });
    });

  /* ---------- schema-driven forms ---------- */
  A.SCHEMAS = {
    memories: [
      { name: "content", label: "What should the assistant remember?", type: "textarea", full: true, rows: 3, required: true },
      { name: "kind", label: "Kind", type: "select", options: [["fact", "Fact"], ["preference", "Preference"], ["decision", "Decision"], ["context", "Context"]] },
    ],
  };
  A.renderFields = (fields, values) =>
    fields.map((f) => {
      const v = values[f.name] ?? f.default ?? "";
      const id = `f-${f.name}-${Math.random().toString(36).slice(2, 7)}`;
      const req = f.required ? "required" : "";
      let input;
      switch (f.type) {
        case "textarea":
        case "code":
          input = `<textarea id="${id}" name="${f.name}" rows="${f.rows || 4}" ${req} ${f.type === "code" ? 'spellcheck="false" class="mono"' : ""} placeholder="${esc(f.placeholder || "")}">${esc(v)}</textarea>`;
          break;
        case "select":
          input = `<select id="${id}" name="${f.name}" ${req}>${f.options.map(([val, lab]) => `<option value="${esc(val)}" ${String(val) === String(v ?? "") ? "selected" : ""}>${esc(lab)}</option>`).join("")}</select>`;
          break;
        case "bool":
          return `<div class="field ${f.full ? "full" : ""}" data-field="${f.name}" style="justify-content:flex-end"><label class="switch"><input type="checkbox" name="${f.name}" ${v ? "checked" : ""}><span class="track"></span>${esc(f.label)}</label></div>`;
        case "tags":
          input = `<input id="${id}" type="text" name="${f.name}" value="${esc(Array.isArray(v) ? v.join(", ") : v)}" placeholder="${esc(f.placeholder || "tag, another")}">`;
          break;
        default:
          input = `<input id="${id}" type="${f.type || "text"}" name="${f.name}" value="${esc(v)}" ${req} ${f.step ? `step="${f.step}"` : ""} ${f.min !== undefined ? `min="${f.min}"` : ""} placeholder="${esc(f.placeholder || "")}">`;
      }
      return `<div class="field ${f.full ? "full" : ""}" data-field="${f.name}"><label for="${id}">${esc(f.label)}${f.required ? " *" : ""}</label>${input}${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ""}</div>`;
    }).join("");
  A.readForm = (form, fields) => {
    const out = {};
    fields.forEach((f) => {
      const el = form.elements[f.name];
      if (!el) return;
      out[f.name] = f.type === "bool" ? el.checked : el.value;
    });
    return out;
  };
  A.showErrors = (form, err) => {
    $$(".field.invalid", form).forEach((f) => { f.classList.remove("invalid"); f.querySelector(".error")?.remove(); });
    if (err && err.errors) {
      Object.entries(err.errors).forEach(([k, msg]) => {
        const f = form.querySelector(`[data-field="${k}"]`);
        if (f) { f.classList.add("invalid"); f.insertAdjacentHTML("beforeend", `<span class="error">${esc(msg)}</span>`); }
      });
    }
  };
  A.formModal = ({ title, fields, values = {}, submitLabel = "Save", onSubmit, wide = false, extra = "", intro = "" }) =>
    new Promise((resolve) => {
      let done = false;
      const fid = "form-" + Math.random().toString(36).slice(2, 8);
      const form = A.h(`<form id="${fid}" class="form-grid" novalidate>${intro ? `<p class="muted small full" style="margin:0">${intro}</p>` : ""}${A.renderFields(fields, values)}${extra}</form>`);
      const m = A.modal({
        title, body: form, wide, onClose: () => !done && resolve(null),
        actions: [{ label: "Cancel", kind: "ghost", onClick: (_, { close }) => close() }, { label: submitLabel, kind: "primary", submit: true, form: fid }],
      });
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const missing = fields.filter((f) => f.required && f.type !== "bool" && !String(form.elements[f.name].value).trim());
        if (missing.length) return A.showErrors(form, { errors: Object.fromEntries(missing.map((f) => [f.name, "required"])) });
        const btn = m.el.querySelector(".modal-foot .primary");
        btn.disabled = true;
        try {
          const saved = await onSubmit(A.readForm(form, fields), form);
          done = true;
          resolve(saved);
          m.close();
        } catch (err) {
          A.showErrors(form, err);
          A.toast(err.message, "err");
          btn.disabled = false;
        }
      });
      form.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") form.requestSubmit(); });
      form._modal = m;
    });
  A.editEntity = (entity, item = null, defaults = {}, title) =>
    A.formModal({
      title: title || (item ? "Edit" : "Add"), fields: A.SCHEMAS[entity], values: item || defaults, submitLabel: item ? "Save" : "Add",
      onSubmit: async (data) => {
        const saved = item ? await A.api("PUT", `/api/admin/e/${entity}/${item.id}`, data) : await A.api("POST", `/api/admin/e/${entity}`, data);
        A.toast("Saved", "ok");
        return saved;
      },
    });
  A.deleteEntity = async (entity, item, name) => {
    if (!(await A.confirm(`Delete “${name || item.title || item.name || "this item"}”? This cannot be undone.`, { danger: true, confirmLabel: "Delete" }))) return false;
    await A.api("DELETE", `/api/admin/e/${entity}/${item.id}`);
    A.toast("Deleted", "ok");
    return true;
  };

  /* ---------- charts (Chart.js loaded on first use) ---------- */
  let chartLib = null;
  A.chartLib = () => {
    if (window.Chart) return Promise.resolve(window.Chart);
    if (!chartLib) {
      chartLib = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js";
        s.onload = () => {
          const C = window.Chart;
          C.defaults.color = "#7f8ba1";
          C.defaults.font.family = "Inter, sans-serif";
          C.defaults.borderColor = "#13213a";
          if (A.reducedMotion()) C.defaults.animation = false;
          resolve(C);
        };
        s.onerror = () => reject(new Error("Chart library failed to load (offline?)"));
        document.head.appendChild(s);
      });
    }
    return chartLib;
  };
  A.chart = async (canvas, config) => {
    if (!canvas) return null;
    try {
      const C = await A.chartLib();
      const c = new C(canvas, config);
      A.signal?.addEventListener("abort", () => c.destroy());
      return c;
    } catch (e) {
      canvas.replaceWith(A.h(`<p class="dim small">${esc(e.message)}</p>`));
      return null;
    }
  };
  A.BLUE = "#2f7dff";
  A.BLUE_SOFT = "rgba(47,125,255,0.18)";
  A.money = (n, cur = A._currency || "₹") => `${n < 0 ? "−" : ""}${cur}${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

  /* ---------- sub-navigation helper for section pages ---------- */
  A.kpis = (items) => `<section class="kpis">${items.map(([v, l, s = "", cls = ""]) => `<div class="kpi ${cls}"><div class="v">${v}</div><div class="l">${esc(l)}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`).join("")}</section>`;

  /* ======================= ROUTER ======================= */
  A.pages = {};
  A.page = (name, fn) => (A.pages[name] = fn);
  A.guard = null; // set by editors: () => true when there are unsaved changes
  let pageCtl = null;
  function initPage() {
    pageCtl?.abort();
    pageCtl = new AbortController();
    A.signal = pageCtl.signal;
    A.guard = null;
    const main = A.main();
    A.enhanceMarkdown(main);
    A.observeCounters(main);
    const fn = A.pages[main.dataset.init];
    if (fn) Promise.resolve().then(() => fn(main, A.signal)).catch((e) => { console.error(e); A.toast(e.message || "Page error", "err"); });
  }
  const bar = () => $("#nav-progress");
  let navSeq = 0;
  async function navigate(href, push = true) {
    if (A.guard && A.guard() && !window.confirm("You have unsaved changes. Leave this page?")) return;
    const seq = ++navSeq;
    // progress bar: shown only while a page is actually being fetched (delayed so instant loads never flash it)
    const showBar = setTimeout(() => bar()?.classList.add("on"), 150);
    const hideBar = () => { clearTimeout(showBar); if (seq === navSeq) bar()?.classList.remove("on"); };
    let res;
    try {
      res = await fetch(href, { credentials: "same-origin", headers: { "X-Astra-Nav": "1" } });
    } catch (_) { hideBar(); location.href = href; return; }
    if (seq !== navSeq) { clearTimeout(showBar); return; }
    const final = new URL(res.url);
    if (!final.pathname.startsWith("/admin") || res.status >= 500) { location.href = res.url; return; }
    const doc = new DOMParser().parseFromString(await res.text(), "text/html");
    const newMain = doc.getElementById("main");
    if (!newMain) { location.href = href; return; }
    const target = new URL(href, location.origin);
    const swap = () => {
      document.title = doc.title;
      $("#crumbs").innerHTML = doc.getElementById("crumbs").innerHTML;
      $("#side-nav").innerHTML = doc.getElementById("side-nav").innerHTML;
      A.main().replaceWith(document.importNode(newMain, true));
      if (push) history.pushState({ astra: 1 }, "", final.pathname + final.search + target.hash);
      if (!target.hash) window.scrollTo(0, 0);
      closeSidebar();
      initPage();
    };
    if (document.startViewTransition && !A.reducedMotion()) document.startViewTransition(swap).finished.catch(() => {});
    else swap();
    hideBar();
  }
  A.go = (href) => navigate(href, true);
  A.reload = () => navigate(location.pathname + location.search, false);
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download") || a.dataset.full !== undefined) return;
    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith("/admin")) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    navigate(url.href, true);
  }, true);
  window.addEventListener("popstate", () => navigate(location.href, false));
  window.addEventListener("beforeunload", (e) => { if (A.guard && A.guard()) { e.preventDefault(); e.returnValue = ""; } });

  /* ---------- sidebar ---------- */
  const setCookie = (k, v) => (document.cookie = `${k}=${encodeURIComponent(v)}; path=/admin; max-age=31536000; SameSite=Lax`);
  let scrim;
  function closeSidebar() {
    $("#sidebar")?.classList.remove("open");
    $("#menu-btn")?.setAttribute("aria-expanded", "false");
    scrim?.remove();
  }
  document.addEventListener("click", (e) => {
    const chev = e.target.closest(".os-chev");
    if (!chev) return;
    const g = chev.closest(".os-group");
    const collapsed = g.classList.toggle("collapsed");
    chev.setAttribute("aria-expanded", String(!collapsed));
    setCookie("astra_nav", $$(".os-group.collapsed").map((x) => x.dataset.group).join(","));
  });

  /* ---------- quick task (Q) ---------- */
  A.quickTask = () =>
    A.formModal({
      title: "Quick task",
      fields: [
        { name: "title", label: "Task", required: true, full: true },
        { name: "due_date", label: "Due date", type: "date" },
        { name: "priority", label: "Priority", type: "select", options: [["", "No priority"], ["low", "Low"], ["medium", "Medium"], ["high", "High"]] },
      ],
      submitLabel: "Add task",
      onSubmit: async (d) => {
        const t = await A.api("POST", "/api/admin/todos", d);
        A.toast("Task added", "ok");
        document.dispatchEvent(new CustomEvent("astra:changed", { detail: { entity: "todos" } }));
        return t;
      },
    });

  /* ---------- jump palette (Ctrl+K) ---------- */
  A.openPalette = async () => {
    const dest = [
      ["Projects", "/admin/projects"], ["Exhibit Management", "/admin/exhibits"], ["Public Profile", "/admin/profile"],
      ["Medicines · Overview", "/admin/medicines"], ["Medicines · Tracking", "/admin/medicines/tracking"], ["Medicines · List", "/admin/medicines/list"],
      ["Medicines · History", "/admin/medicines/history"],
      ["Tasks · Overview", "/admin/tasks"], ["Tasks · Today", "/admin/tasks/today"], ["Tasks · All", "/admin/tasks/all"],
      ["Tasks · Upcoming", "/admin/tasks/upcoming"], ["Tasks · Completed", "/admin/tasks/completed"],
      ["Journaling · Write", "/admin/journaling"], ["Journaling · Entries", "/admin/journaling/entries"],
      ["Expenses · Overview", "/admin/expenses"], ["Expenses · Transactions", "/admin/expenses/transactions"], ["Expenses · Monthly", "/admin/expenses/monthly"],
      ["Expenses · Categories", "/admin/expenses/categories"], ["AI Assistant · Personality", "/admin/assistant"], ["AI Assistant · Voice", "/admin/assistant/voice"],
      ["AI Assistant · Memory", "/admin/assistant/memory"], ["AI Assistant · History", "/admin/assistant/history"], ["System", "/admin/settings"],
    ];
    try { (await A.meta()).projects.forEach((p) => dest.push([`Project · ${p.name}`, `/admin/projects/${p.id}`])); } catch (_) { /* offline */ }
    const box = A.h(`<div class="palette"><input type="search" placeholder="Jump to a section or project…" aria-label="Jump to" autofocus><div class="palette-results" role="listbox"></div></div>`);
    const m = A.modal({ body: box, className: "palette" });
    m.body.style.padding = "0";
    const input = box.querySelector("input"), results = box.querySelector(".palette-results");
    let items = [], sel = 0;
    const paint = () => {
      const q = input.value.toLowerCase().trim();
      items = dest.filter(([n]) => !q || n.toLowerCase().includes(q)).slice(0, 30);
      results.innerHTML = items.map(([n, u], i) => `<a class="palette-item ${i === sel ? "sel" : ""}" href="${u}">${esc(n)}</a>`).join("") || '<div class="empty small">No matches</div>';
      results.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => m.close()));
    };
    input.addEventListener("input", () => { sel = 0; paint(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(items.length - 1, sel + 1); paint(); }
      if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); paint(); }
      if (e.key === "Enter" && items[sel]) { e.preventDefault(); m.close(); A.go(items[sel][1]); }
    });
    paint();
  };

  /* ---------- welcome marquee ---------- */
  async function marquee() {
    const el = $("#os-marquee");
    if (!el) return;
    const h = new Date().getHours();
    const parts = [`${h < 5 ? "Burning the midnight oil" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"}, Sir`,
      new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })];
    try {
      const [t, g] = await Promise.all([A.api("GET", "/api/admin/todos/stats"), A.api("GET", `/api/admin/medicines/grid?days=1&start=${A.today()}`)]);
      parts.push(t.due_today + t.overdue ? `${t.due_today + t.overdue} task${t.due_today + t.overdue === 1 ? "" : "s"} need attention today` : "no tasks due today");
      let due = 0, taken = 0;
      g.rows.forEach((r) => r.cells[0].doses && r.cells[0].doses.forEach((d) => { due++; taken += d === "taken"; }));
      if (due) parts.push(`${taken} of ${due} medicine doses taken`);
    } catch (_) { /* keep the greeting */ }
    parts.push("ASTRA personal OS online", "all systems nominal");
    marqueeText = parts.join("  ·  ");
    layoutMarquee();
  }
  let marqueeText = "";
  /* Build two identical halves, each at least as wide as the bar, then slide by exactly one half.
     Speed is constant (px/s) whatever the text length or viewport width. */
  function layoutMarquee() {
    const el = $("#os-marquee");
    if (!el || !marqueeText) return;
    el.style.animation = "none";
    el.innerHTML = `<span>${esc(marqueeText)}</span>`;
    const unit = el.firstElementChild.getBoundingClientRect().width || 1;
    const bar = el.parentElement.clientWidth || window.innerWidth;
    const copies = Math.max(1, Math.ceil(bar / unit));
    const half = Array.from({ length: copies }, (_, i) => `<span${i ? ' aria-hidden="true"' : ""}>${esc(marqueeText)}</span>`).join("");
    el.innerHTML = half + half.replace(/<span>/g, '<span aria-hidden="true">');
    el.style.setProperty("--marquee-dur", `${Math.round((unit * copies) / 45)}s`);
    void el.offsetWidth; // restart from 0 with the new geometry
    el.style.animation = "";
  }
  let marqueeW = window.innerWidth;
  window.addEventListener("resize", A.debounce(() => { if (window.innerWidth !== marqueeW) { marqueeW = window.innerWidth; layoutMarquee(); } }, 250));

  /* ---------- boot ---------- */
  document.addEventListener("DOMContentLoaded", () => {
    $("#search-trigger")?.addEventListener("click", A.openPalette);
    document.addEventListener("click", (e) => { if (e.target.closest("[data-quick-task]")) A.quickTask(); });
    $("#rail-toggle")?.addEventListener("click", () => setCookie("astra_rail", $("#shell").classList.toggle("rail") ? "1" : "0"));
    $("#menu-btn")?.addEventListener("click", () => {
      $("#sidebar").classList.add("open");
      $("#menu-btn").setAttribute("aria-expanded", "true");
      scrim = A.h('<div class="scrim"></div>');
      scrim.addEventListener("click", closeSidebar);
      document.body.appendChild(scrim);
    });
    document.addEventListener("keydown", (e) => {
      const typing = e.target.closest("input, textarea, select, [contenteditable]");
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && !e.target.closest("#je-content")) { e.preventDefault(); A.openPalette(); }
      if (typing || e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".modal-backdrop")) return;
      if (e.key.toLowerCase() === "q") { e.preventDefault(); A.quickTask(); }
    });
    A.meta().catch(() => {});
    // heartbeat: tells the server this admin tab is still open (closing it ends the visit)
    const alive = () => A.api("POST", "/api/admin/alive").catch(() => {});
    alive();
    setInterval(alive, 60000);
    // a page restored from the back/forward cache must be re-checked by the server
    window.addEventListener("pageshow", (e) => { if (e.persisted) location.reload(); });
    marquee();
    initPage();
  });
})();
