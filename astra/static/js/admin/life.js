/* Personal OS sections: Tasks, Medicines, Expenses. Each section owns its own analytics. */
(function () {
  "use strict";
  const A = window.ASTRA, esc = A.esc, $$ = A.$$;
  const changedBus = (entity, fn, signal) => document.addEventListener("astra:changed", (e) => e.detail?.entity === entity && fn(), { signal });

  /* ============================================================ TASKS */
  const PRIO = [["", "No priority"], ["low", "Low"], ["medium", "Medium"], ["high", "High"]];
  const prioBadge = (p) => (p ? `<span class="badge b-${p === "high" ? "high" : p === "medium" ? "medium" : "low"}">${A.label(p)}</span>` : "");
  const TASK_FIELDS = [
    { name: "title", label: "Task", required: true, full: true },
    { name: "description", label: "Description (optional)", type: "textarea", rows: 3, full: true },
    { name: "due_date", label: "Due date (optional)", type: "date" },
    { name: "priority", label: "Priority (optional)", type: "select", options: PRIO },
  ];
  const editTask = (t) => A.formModal({
    title: t ? "Edit task" : "New task", fields: TASK_FIELDS, values: t || {}, submitLabel: t ? "Save" : "Add task",
    onSubmit: (d) => (t ? A.api("PUT", `/api/admin/todos/${t.id}`, d) : A.api("POST", "/api/admin/todos", d)),
  });

  A.page("tasks", async (main, signal) => {
    const view = main.dataset.view, box = main.querySelector("#sec");
    if (view === "dashboard") {
      const load = async () => {
        const [s, today] = await Promise.all([A.api("GET", "/api/admin/todos/stats"), A.api("GET", "/api/admin/todos?view=today")]);
        box.innerHTML = A.kpis([[s.total, "Total tasks"], [s.completed, "Completed", "", "ok"], [s.pending, "Pending"],
          [s.overdue, "Overdue", "", s.overdue ? "bad" : ""], [`${s.completion_rate}%`, "Completion rate"], [s.due_today, "Due today", `${s.due_week} more this week`]]) +
          `<div class="dash" style="margin-top:1rem">
            <section class="panel pad span-8"><h3 class="panel-title">Completed vs created · last 30 days</h3><div class="chart-box"><canvas id="c-done"></canvas></div></section>
            <section class="panel pad span-4"><h3 class="panel-title">Open tasks by priority</h3><div class="chart-box">${s.pending ? '<canvas id="c-prio"></canvas>' : '<p class="dim small">No open tasks.</p>'}</div></section>
            <section class="panel pad span-12"><div class="row"><h3 class="panel-title" style="margin:0">Due today & overdue</h3><span class="spacer"></span><a class="btn sm ghost" href="/admin/tasks/today">Open Today →</a></div>
              <div id="today-list" style="margin-top:.6rem"></div></section></div>`;
        taskRows(box.querySelector("#today-list"), today.slice(0, 8), load, true);
        A.chart(box.querySelector("#c-done"), { type: "bar", data: { labels: s.days, datasets: [
          { label: "Completed", data: s.completed_per_day, backgroundColor: A.BLUE, borderRadius: 3 },
          { label: "Created", data: s.created_per_day, type: "line", borderColor: "#7f8ba1", backgroundColor: "transparent", tension: 0.3, pointRadius: 0 }] },
          options: { maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { ticks: { maxTicksLimit: 10 } } }, plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } } });
        const pr = s.priority, keys = ["high", "medium", "low", "none"].filter((k) => pr[k]);
        A.chart(box.querySelector("#c-prio"), { type: "doughnut", data: { labels: keys.map((k) => (k === "none" ? "No priority" : A.label(k))),
          datasets: [{ data: keys.map((k) => pr[k]), backgroundColor: keys.map((k) => ({ high: "#f87171", medium: "#fbbf24", low: "#2f7dff", none: "#33415a" })[k]), borderColor: "#000", borderWidth: 3 }] },
          options: { maintainAspectRatio: false, cutout: "66%", plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } } });
      };
      changedBus("todos", load, signal);
      return load().catch((e) => A.errorState(box, e, load));
    }
    // list views
    const state = { q: "", priority: "", sort: "smart" };
    box.innerHTML = `${view !== "completed" ? `<form class="quick-add panel" id="qa" autocomplete="off">
        <input name="title" placeholder="Add a task… (Enter to save)" aria-label="New task title" required>
        <input name="due_date" type="date" aria-label="Due date" ${view === "today" ? `value="${A.today()}"` : ""}>
        <select name="priority" aria-label="Priority">${PRIO.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
        <button class="btn primary" type="submit">${A.icon("plus")} Add</button></form>` : ""}
      <div class="toolbar"><input type="search" data-q placeholder="Search tasks…" aria-label="Search tasks">
        <select data-prio aria-label="Priority filter"><option value="">Any priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option><option value="none">No priority</option></select>
        ${view !== "completed" ? '<select data-sort aria-label="Sort"><option value="smart">Smart order</option><option value="due">Due date</option><option value="priority">Priority</option><option value="newest">Newest</option><option value="oldest">Oldest</option></select>' : ""}
        <span class="spacer"></span><span class="dim small" data-count></span></div><div id="tlist"></div>`;
    const list = box.querySelector("#tlist");
    const load = async () => {
      const rows = await A.api("GET", "/api/admin/todos" + A.qs({ view, q: state.q, priority: state.priority, sort: state.sort }));
      box.querySelector("[data-count]").textContent = `${rows.length} task${rows.length === 1 ? "" : "s"}`;
      if (!rows.length) return A.empty(list, { today: "Nothing due today", upcoming: "Nothing upcoming", completed: "No completed tasks yet" }[view] || "No tasks", view === "completed" ? "Finished tasks land here." : "Add one above. Priority and dates are optional.");
      taskRows(list, rows, load, false);
    };
    box.querySelector("#qa")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      if (!f.title.value.trim()) return;
      try {
        await A.api("POST", "/api/admin/todos", { title: f.title.value, due_date: f.due_date.value, priority: f.priority.value });
        f.title.value = "";
        A.toast("Task added", "ok");
        load();
      } catch (err) { A.toast(err.message, "err"); }
    });
    box.querySelector("[data-q]").addEventListener("input", A.debounce((e) => { state.q = e.target.value; load(); }, 250));
    box.querySelector("[data-prio]").addEventListener("change", (e) => { state.priority = e.target.value; load(); });
    box.querySelector("[data-sort]")?.addEventListener("change", (e) => { state.sort = e.target.value; load(); });
    changedBus("todos", load, signal);
    load().catch((e) => A.errorState(list, e, load));
  });

  function taskRows(el, rows, reload, compact) {
    if (!rows.length) { el.innerHTML = '<p class="dim small">Nothing here. 🎯</p>'; return; }
    el.innerHTML = `<div class="task-list">${rows.map((t) => {
      const late = !t.completed_at && A.isLate(t.due_date);
      return `<div class="task-row ${t.completed_at ? "done" : ""}" data-id="${t.id}">
        <label class="task-check"><input type="checkbox" ${t.completed_at ? "checked" : ""} aria-label="Mark “${esc(t.title)}” ${t.completed_at ? "not done" : "done"}"><span></span></label>
        <div class="task-main"><button class="task-title" type="button" data-edit>${esc(t.title)}</button>
          ${t.description && !compact ? `<div class="dim small">${esc(A.excerpt(t.description, 120))}</div>` : ""}</div>
        <div class="task-meta">${prioBadge(t.priority)}${t.due_date ? `<span class="due ${late ? "late" : ""}">${late ? "Overdue · " : ""}${A.fmtDate(t.due_date, { day: "numeric", month: "short" })}</span>` : ""}
          ${t.completed_at ? `<span class="dim small">✓ ${A.fmtDate(t.completed_at, { day: "numeric", month: "short" })}</span>` : `<span class="dim small" title="Created">${A.rel(t.created_at)}</span>`}</div>
        <div class="task-actions"><button class="btn sm icon ghost" data-edit aria-label="Edit">${A.icon("edit")}</button><button class="btn sm icon ghost" data-del aria-label="Delete">${A.icon("trash")}</button></div></div>`;
    }).join("")}</div>`;
    $$(".task-row", el).forEach((row) => {
      const t = rows.find((x) => String(x.id) === row.dataset.id);
      row.querySelector("input[type=checkbox]").addEventListener("change", async (e) => {
        row.classList.toggle("done", e.target.checked);
        try { await A.api("PATCH", `/api/admin/todos/${t.id}`, { completed: e.target.checked }); A.toast(e.target.checked ? "Done ✓" : "Reopened", "ok"); setTimeout(reload, 350); }
        catch (err) { A.toast(err.message, "err"); }
      });
      $$("[data-edit]", row).forEach((b) => b.addEventListener("click", async () => { if (await editTask(t)) { A.toast("Task saved", "ok"); reload(); } }));
      row.querySelector("[data-del]").addEventListener("click", async () => {
        if (!(await A.confirm(`Delete “${t.title}”?`, { danger: true, confirmLabel: "Delete" }))) return;
        await A.api("DELETE", `/api/admin/todos/${t.id}`);
        A.toast("Task deleted", "ok");
        reload();
      });
    });
  }

  /* ============================================================ MEDICINES */
  const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  async function editMedicine(m) {
    const v = m || { frequency: "daily", start_date: A.today(), dose_times: [], doses_per_day: 1, weekdays: [], interval_days: 2 };
    const customLabels = (v.dose_times || []).slice(0, v.doses_per_day).filter((l, i) => l !== `Dose ${i + 1}`);
    return new Promise((resolve) => {
      let done = false;
      const form = A.h(`<form class="form-grid" novalidate>
        <div class="field full" data-field="name"><label>Medicine name *</label><input name="name" value="${esc(v.name || "")}" required></div>
        <div class="field" data-field="dosage"><label>Dosage (optional)</label><input name="dosage" value="${esc(v.dosage || "")}" placeholder="e.g. 500 mg, 1 tablet"></div>
        <div class="field" data-field="frequency"><label>Frequency</label><select name="frequency">
          ${[["daily", "Daily"], ["alternate", "Alternate days"], ["weekdays", "Specific weekdays"], ["interval", "Every N days"]].map(([k, l]) => `<option value="${k}" ${v.frequency === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div class="field full" data-field="weekdays" data-show="weekdays"><label>Days</label><div class="chips">${WD.map((d, i) => `<label class="chip-check"><input type="checkbox" name="wd" value="${i}" ${v.weekdays.includes(i) ? "checked" : ""}><span>${d}</span></label>`).join("")}</div></div>
        <div class="field" data-field="interval_days" data-show="interval"><label>Every how many days?</label><input name="interval_days" type="number" min="1" max="60" value="${v.interval_days || 2}"></div>
        <div class="field" data-field="doses_per_day"><label>Doses per day</label><input name="doses_per_day" type="number" min="1" max="8" inputmode="numeric" value="${v.doses_per_day || 1}">
          <span class="hint">Each dose gets its own checkbox.${m ? " Changing this applies from today; past tracking is kept." : ""}</span></div>
        <div class="field" data-field="dose_times"><label>Dose names (optional)</label><input name="dose_times" value="${esc(customLabels.join(", "))}" placeholder="Morning, Night">
          <span class="hint">Comma separated. Unnamed doses show as Dose 1, Dose 2…</span></div>
        <div class="field" data-field="start_date"><label>Start date</label><input name="start_date" type="date" value="${v.start_date || A.today()}"></div>
        <div class="field" data-field="end_date"><label class="switch" style="margin-bottom:.35rem"><input type="checkbox" name="has_end" ${v.end_date ? "checked" : ""}><span class="track"></span>Has an end date</label>
          <input name="end_date" type="date" value="${v.end_date || ""}" ${v.end_date ? "" : "disabled"}></div>
        <div class="field full" data-field="notes"><label>Instructions / notes (optional)</label><textarea name="notes" rows="2">${esc(v.notes || "")}</textarea></div>
        <p class="hint full" style="margin:0">ASTRA tracks your doses; it never gives medical advice.</p></form>`);
      const sync = () => {
        $$("[data-show]", form).forEach((el) => el.classList.toggle("hidden", el.dataset.show !== form.frequency.value));
        form.end_date.disabled = !form.has_end.checked;
      };
      form.addEventListener("change", sync);
      sync();
      const m2 = A.modal({ title: m ? `Edit ${m.name}` : "Add medicine", body: form, wide: true, onClose: () => !done && resolve(null),
        actions: [{ label: "Cancel", kind: "ghost", onClick: (_, { close }) => close() }, { label: m ? "Save" : "Add medicine", kind: "primary", onClick: () => submit() }] });
      const submit = async () => {
        const d = { name: form.name.value, dosage: form.dosage.value, frequency: form.frequency.value,
          weekdays: $$("input[name=wd]:checked", form).map((x) => Number(x.value)), interval_days: form.interval_days.value,
          doses_per_day: Number(form.doses_per_day.value || 1), dose_times: form.dose_times.value, start_date: form.start_date.value, has_end: form.has_end.checked,
          end_date: form.has_end.checked ? form.end_date.value : "", notes: form.notes.value };
        try {
          const r = m ? await A.api("PUT", `/api/admin/medicines/${m.id}`, d) : await A.api("POST", "/api/admin/medicines", d);
          done = true; resolve(r); m2.close();
          A.toast(m ? "Medicine updated" : "Medicine added", "ok");
        } catch (err) { A.showErrors(form, err); A.toast(err.message, "err"); }
      };
      form.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
    });
  }
  async function stopMedicine(m) {
    if (!(await A.confirm(`Stop tracking ${m.name}? Its schedule ends today; the medicine and all its history are kept in Stopped.`, { confirmLabel: "Stop tracking" }))) return false;
    await A.api("POST", `/api/admin/medicines/${m.id}/stop`);
    A.toast(`${m.name} stopped · history kept`, "ok");
    return true;
  }
  async function deleteMedicine(m) {
    if (!(await A.confirm(`DELETE ${m.name} permanently? This removes the medicine AND every tracking record (taken / missed history). Use “Stop” instead to keep the history.`, { danger: true, confirmLabel: "Delete permanently", title: "Delete medicine" }))) return false;
    await A.api("DELETE", `/api/admin/medicines/${m.id}`);
    A.toast(`${m.name} deleted`, "ok");
    return true;
  }
  function medCards(el, meds, reload, stopped) {
    if (!meds.length) return A.empty(el, stopped ? "No stopped medicines" : "No active medicines", stopped ? "Stopped medicines and their history appear here." : "Add a medicine to start tracking.", stopped ? "" : '<button class="btn primary" data-add-med>Add medicine</button>');
    el.innerHTML = `<div class="cgrid">${meds.map((m) => `<article class="panel citem med-card" data-id="${m.id}">
        <div class="row wrap"><span class="badge ${m.status === "active" ? "b-active" : "b-private"}">${m.status === "active" ? "Active" : "Stopped"}</span><span class="spacer"></span>${m.dosage ? `<span class="chip">${esc(m.dosage)}</span>` : ""}</div>
        <h4>${esc(m.name)}</h4><div class="small">${esc(m.schedule_label)}</div>
        <div class="chips">${m.dose_times.slice(0, m.doses_per_day).map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div>
        <div class="dim small">From ${A.fmtDate(m.start_date)}${m.end_date ? ` to ${A.fmtDate(m.end_date)}` : " · no end date"}${m.stopped_at ? ` · stopped ${A.fmtDate(m.stopped_at)}` : ""}</div>
        ${m.notes ? `<div class="body">${esc(m.notes)}</div>` : ""}
        <div class="foot">${m.status === "active" ? `<a class="btn sm" href="/admin/medicines/tracking">Track</a><button class="btn sm ghost" data-a="stop">${A.icon("pause")} Stop</button>`
          : `<button class="btn sm" data-a="resume">${A.icon("restore")} Resume</button><a class="btn sm ghost" href="/admin/medicines/history?medicine=${m.id}">History</a>`}
          <span class="spacer"></span><button class="btn sm icon ghost" data-a="edit" aria-label="Edit">${A.icon("edit")}</button>
          <button class="btn sm icon ghost danger-icon" data-a="delete" aria-label="Delete permanently">${A.icon("trash")}</button></div></article>`).join("")}</div>`;
    $$("[data-a]", el).forEach((b) => b.addEventListener("click", async () => {
      const m = meds.find((x) => String(x.id) === b.closest("[data-id]").dataset.id);
      try {
        if (b.dataset.a === "edit" && !(await editMedicine(m))) return;
        if (b.dataset.a === "stop" && !(await stopMedicine(m))) return;
        if (b.dataset.a === "delete" && !(await deleteMedicine(m))) return;
        if (b.dataset.a === "resume") { await A.api("POST", `/api/admin/medicines/${m.id}/resume`); A.toast(`${m.name} resumed`, "ok"); }
        reload();
      } catch (err) { A.toast(err.message, "err"); }
    }));
  }

  A.page("medicines", async (main, signal) => {
    const view = main.dataset.view, box = main.querySelector("#sec");
    main.addEventListener("click", async (e) => {
      if (e.target.closest("[data-add-med]") && (await editMedicine(null))) A.reload();
    }, { signal });
    if (view === "dashboard") {
      const s = await A.api("GET", "/api/admin/medicines/stats?window=30");
      box.innerHTML = A.kpis([[s.active, "Active medicines", s.stopped ? `${s.stopped} stopped` : ""],
        [`${s.today_taken}/${s.today_scheduled}`, "Doses today"], [s.adherence === null ? "—" : `${s.adherence}%`, "Adherence · 30 days", "", s.adherence !== null && s.adherence < 80 ? "warn" : "ok"],
        [s.scheduled, "Scheduled · 30 days"], [s.taken, "Taken", "", "ok"], [s.missed, "Missed", "", s.missed ? "bad" : ""]]) +
        `<div class="dash" style="margin-top:1rem">
          <section class="panel pad span-8"><h3 class="panel-title">Daily adherence · last 30 days</h3><div class="chart-box"><canvas id="c-adh"></canvas></div></section>
          <section class="panel pad span-4"><h3 class="panel-title">Recent tracking</h3><div class="list">${s.recent.map((r) => `<div class="list-item"><span class="t">${esc(r.name)} · ${esc(r.dose)}</span><span class="m">${A.fmtDate(r.log_date, { day: "numeric", month: "short" })}</span></div>`).join("") || '<p class="dim small">No doses logged yet.</p>'}</div></section>
          <section class="panel pad span-12"><h3 class="panel-title">Adherence by medicine · 30 days</h3>${s.per_medicine.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Medicine</th><th>Scheduled</th><th>Taken</th><th>Missed</th><th style="width:40%">Adherence</th></tr></thead><tbody>${s.per_medicine.map((m) => `<tr><td class="title-cell">${esc(m.name)} ${m.status === "stopped" ? '<span class="badge b-private">Stopped</span>' : ""}</td><td>${m.scheduled}</td><td>${m.taken}</td><td>${m.missed}</td>
            <td>${m.adherence === null ? '<span class="dim small">No past doses yet</span>' : `<div class="row"><div class="progress" style="flex:1"><span style="width:${m.adherence}%"></span></div><span class="mono small">${m.adherence}%</span></div>`}</td></tr>`).join("")}</tbody></table></div>` : '<p class="dim small">Add medicines to see adherence.</p>'}</section></div>`;
      A.chart(box.querySelector("#c-adh"), { type: "line", data: { labels: s.trend_days, datasets: [{ label: "Adherence %", data: s.trend, borderColor: A.BLUE, backgroundColor: A.BLUE_SOFT, fill: true, tension: 0.3, spanGaps: true, pointRadius: 2 }] },
        options: { maintainAspectRatio: false, scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } }, x: { ticks: { maxTicksLimit: 10 } } }, plugins: { legend: { display: false } } } });
      return;
    }
    if (view === "list") {
      let status = new URLSearchParams(location.search).get("status") === "stopped" ? "stopped" : "active";
      box.innerHTML = `<div class="toolbar"><div class="seg" role="group" aria-label="Status">
          <button type="button" data-s="active">Active</button><button type="button" data-s="stopped">Stopped</button></div>
        <span class="spacer"></span><button class="btn primary" data-add-med>${A.icon("plus")} Add medicine</button></div><div id="mlist"></div>`;
      const list = box.querySelector("#mlist");
      const paint = () => $$("[data-s]", box).forEach((b) => { b.classList.toggle("on", b.dataset.s === status); b.setAttribute("aria-pressed", String(b.dataset.s === status)); });
      const load = async () => medCards(list, await A.api("GET", `/api/admin/medicines?status=${status}`), load, status === "stopped");
      $$("[data-s]", box).forEach((b) => b.addEventListener("click", () => {
        status = b.dataset.s; paint();
        history.replaceState(history.state, "", `${location.pathname}?status=${status}`);
        load().catch((e) => A.errorState(list, e, load));
      }));
      paint();
      return load().catch((e) => A.errorState(list, e, load));
    }
    if (view === "tracking") return trackingGrid(box);
    if (view === "history") return medHistory(box);
  });

  async function trackingGrid(box) {
    let days = window.innerWidth < 700 ? 7 : 14;
    let start = A.addDays(A.today(), -(days - 4));
    let showStopped = false;
    box.innerHTML = `<div class="toolbar"><div class="seg"><button type="button" data-nav="-1">${A.icon("left")}</button><button type="button" data-nav="0">Today</button><button type="button" data-nav="1">${A.icon("right")}</button></div>
      <select data-days aria-label="Range"><option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option></select>
      <label class="switch"><input type="checkbox" data-stopped><span class="track"></span>Show stopped</label><span class="spacer"></span>
      <span class="legend"><i class="lg taken"></i>Taken <i class="lg pending"></i>Due today <i class="lg missed"></i>Missed <i class="lg future"></i>Upcoming <i class="lg na"></i>Not scheduled</span></div>
      <div id="sheet"></div>`;
    box.querySelector("[data-days]").value = String(days);
    const sheet = box.querySelector("#sheet");
    const load = async () => {
      const g = await A.api("GET", "/api/admin/medicines/grid" + A.qs({ start, days, status: showStopped ? "all" : "active" }));
      if (!g.rows.length) return A.empty(sheet, "No medicines to track", "Add a medicine first.", '<button class="btn primary" data-add-med>Add medicine</button>');
      const head = g.dates.map((d) => { const dt = new Date(d + "T00:00:00"); return `<th class="${d === g.today ? "is-today" : ""}"><span>${dt.toLocaleDateString(undefined, { weekday: "short" })}</span><b>${dt.getDate()}</b><small>${dt.toLocaleDateString(undefined, { month: "short" })}</small></th>`; }).join("");
      sheet.innerHTML = `<div class="sheet-wrap"><table class="sheet"><thead><tr><th class="sheet-name">Medicine</th>${head}</tr></thead><tbody>${g.rows.map((r) => `
        <tr><th class="sheet-name"><b>${esc(r.medicine.name)}</b><small>${esc(r.medicine.schedule_label)}</small></th>${r.cells.map((c, i) => {
          const d = g.dates[i];
          if (c.state === "na") return `<td class="na ${d === g.today ? "is-today" : ""}"><span aria-label="Not scheduled">·</span></td>`;
          const n = c.doses.length, done = c.doses.filter((x) => x === "taken").length;
          return `<td class="${d === g.today ? "is-today" : ""}"><div class="doses n${Math.min(n, 4)}">${c.doses.map((st, k) => `<button type="button" class="dose ${st}" data-m="${r.medicine.id}" data-d="${d}" data-k="${k}" ${st === "future" ? "disabled" : ""} title="${esc(r.medicine.dose_times[k] || `Dose ${k + 1}`)} · ${A.fmtDate(d)} · ${st}" aria-label="${esc(r.medicine.name)}, ${esc(r.medicine.dose_times[k] || `dose ${k + 1}`)}, ${d}: ${st}" aria-pressed="${st === "taken"}">${n > 1 ? k + 1 : st === "taken" ? "✓" : st === "missed" ? "✕" : ""}</button>`).join("")}</div>${n > 1 ? `<div class="dose-count">${done}/${n}</div>` : ""}</td>`;
        }).join("")}</tr>`).join("")}</tbody></table></div>`;
      $$(".dose", sheet).forEach((b) => b.addEventListener("click", async () => {
        const taken = !b.classList.contains("taken");
        b.disabled = true;
        try {
          await A.api("POST", "/api/admin/medicines/dose", { medicine_id: Number(b.dataset.m), date: b.dataset.d, dose_index: Number(b.dataset.k), taken });
          b.className = `dose ${taken ? "taken" : b.dataset.d === g.today ? "pending" : "missed"}`;
          const cell = b.closest("td"), boxes = cell.querySelectorAll(".dose");
          if (boxes.length === 1) b.textContent = taken ? "✓" : b.dataset.d === g.today ? "" : "✕";
          b.setAttribute("aria-pressed", String(taken));
          const cnt = cell.querySelector(".dose-count");
          if (cnt) cnt.textContent = `${cell.querySelectorAll(".dose.taken").length}/${boxes.length}`;
        } catch (e) { A.toast(e.message, "err"); }
        b.disabled = false;
      }));
      const todayCol = sheet.querySelector("th.is-today");
      todayCol && todayCol.scrollIntoView({ block: "nearest", inline: "center" });
    };
    box.querySelector("[data-days]").addEventListener("change", (e) => { days = Number(e.target.value); start = A.addDays(A.today(), -(days - Math.min(4, days - 1))); load(); });
    box.querySelector("[data-stopped]").addEventListener("change", (e) => { showStopped = e.target.checked; load(); });
    $$("[data-nav]", box).forEach((b) => b.addEventListener("click", () => {
      const n = Number(b.dataset.nav);
      start = n === 0 ? A.addDays(A.today(), -(days - Math.min(4, days - 1))) : A.addDays(start, n * days);
      load();
    }));
    load().catch((e) => A.errorState(sheet, e, load));
  }

  async function medHistory(box) {
    const meds = await A.api("GET", "/api/admin/medicines?status=all");
    const pre = new URLSearchParams(location.search).get("medicine") || "";
    box.innerHTML = `<div class="toolbar"><select data-med aria-label="Medicine"><option value="">All medicines</option>${meds.map((m) => `<option value="${m.id}" ${String(m.id) === pre ? "selected" : ""}>${esc(m.name)}${m.status === "stopped" ? " (stopped)" : ""}</option>`).join("")}</select>
      <span class="spacer"></span><a class="btn sm ghost" href="/admin/medicines/tracking">Open spreadsheet →</a></div><div id="hstats"></div><div id="hlist"></div>`;
    const load = async () => {
      const mid = box.querySelector("[data-med]").value;
      const [s, logs] = await Promise.all([A.api("GET", "/api/admin/medicines/stats?window=90"), A.api("GET", "/api/admin/medicines/history" + A.qs({ medicine_id: mid }))]);
      const per = s.per_medicine.filter((m) => !mid || String(m.id) === mid);
      box.querySelector("#hstats").innerHTML = `<section class="panel pad" style="margin-bottom:1rem"><h3 class="panel-title">Adherence · last 90 days</h3>${per.map((m) => `<div class="prog-row"><span>${esc(m.name)}</span><div class="progress"><span style="width:${m.adherence || 0}%"></span></div><span class="pct">${m.adherence === null ? "—" : m.adherence + "%"}</span></div><div class="dim small" style="margin:-.3rem 0 .5rem">${m.taken} taken · ${m.missed} missed of ${m.scheduled} scheduled</div>`).join("") || '<p class="dim small">No scheduled doses in this period.</p>'}</section>`;
      const list = box.querySelector("#hlist");
      list.innerHTML = logs.length ? `<div class="panel table-wrap"><table class="data"><thead><tr><th>Date</th><th>Medicine</th><th>Dose</th><th>Logged</th></tr></thead><tbody>${logs.map((l) => `<tr><td class="mono small">${A.fmtDate(l.log_date)}</td><td class="title-cell">${esc(l.name)}</td><td>${esc(l.dose)}</td><td class="dim small">${A.rel(l.logged_at)}</td></tr>`).join("")}</tbody></table></div>`
        : '<div class="panel empty"><h4>No taken doses recorded</h4><p>Tick doses in the tracking spreadsheet.</p></div>';
    };
    box.querySelector("[data-med]").addEventListener("change", load);
    load().catch((e) => A.errorState(box, e, load));
  }

  /* ============================================================ EXPENSES */
  let catCache = null;
  const loadCats = async (fresh) => { if (!catCache || fresh) { catCache = await A.api("GET", "/api/admin/finance/categories"); A._currency = catCache.currency; } return catCache; };
  async function editTx(t, kind = "expense") {
    const cats = await loadCats();
    const v = t || { kind, occurred_at: A.nowLocal(), category: "" };
    return new Promise((resolve) => {
      let done = false;
      const form = A.h(`<form class="form-grid" novalidate>
        <div class="field full"><div class="seg kind-seg" role="radiogroup" aria-label="Type">
          <button type="button" data-k="expense" class="${v.kind === "expense" ? "on" : ""}">− Expense</button><button type="button" data-k="income" class="${v.kind === "income" ? "on" : ""}">+ Income</button></div></div>
        <div class="field" data-field="amount"><label>Amount (${esc(cats.currency)}) *</label><input name="amount" inputmode="decimal" value="${t ? t.amount : ""}" placeholder="0.00" required autofocus></div>
        <div class="field" data-field="category"><label>Category</label><input name="category" list="cat-list" value="${esc(v.category)}" placeholder="Choose or type"><datalist id="cat-list"></datalist></div>
        <div class="field full" data-field="description"><label>Description</label><input name="description" value="${esc(v.description || "")}" placeholder="What was it for?"></div>
        <div class="field" data-field="occurred_at"><label>Date</label><input name="date" type="date" value="${v.occurred_at.slice(0, 10)}"></div>
        <div class="field"><label>Time</label><input name="time" type="time" value="${v.occurred_at.slice(11, 16)}"></div></form>`);
      let k = v.kind;
      const fillCats = () => { form.querySelector("#cat-list").innerHTML = cats.items.filter((c) => c.kind === k).map((c) => `<option value="${esc(c.name)}">`).join(""); };
      $$("[data-k]", form).forEach((b) => b.addEventListener("click", () => { k = b.dataset.k; $$("[data-k]", form).forEach((x) => x.classList.toggle("on", x === b)); fillCats(); }));
      fillCats();
      const m = A.modal({ title: t ? "Edit transaction" : "New transaction", body: form, onClose: () => !done && resolve(null),
        actions: [{ label: "Cancel", kind: "ghost", onClick: (_, { close }) => close() }, { label: t ? "Save" : "Add", kind: "primary", onClick: () => submit() }] });
      const submit = async () => {
        const d = { kind: k, amount: form.amount.value, category: form.category.value, description: form.description.value, occurred_at: `${form.date.value}T${form.time.value || "00:00"}` };
        try {
          const r = t ? await A.api("PUT", `/api/admin/finance/tx/${t.id}`, d) : await A.api("POST", "/api/admin/finance/tx", d);
          done = true; resolve(r); m.close(); A.toast(t ? "Transaction saved" : `${k === "income" ? "Income" : "Expense"} added`, "ok");
        } catch (err) { A.showErrors(form, err); A.toast(err.message, "err"); }
      };
      form.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
      form.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); submit(); } });
    });
  }
  const amt = (t) => `<span class="amt ${t.kind}">${t.kind === "income" ? "+" : "−"}${A.money(t.amount).replace("−", "")}</span>`;
  function txDetail(t, reload) {
    A.modal({ title: t.description || A.label(t.kind), body: `<dl class="kv"><dt>Type</dt><dd>${A.label(t.kind)}</dd><dt>Amount</dt><dd>${amt(t)}</dd><dt>Category</dt><dd>${esc(t.category)}</dd>
      <dt>When</dt><dd>${A.fmtDate(t.occurred_at.slice(0, 10), { weekday: "short", day: "numeric", month: "long", year: "numeric" })} · ${t.occurred_at.slice(11, 16)}</dd><dt>Description</dt><dd>${esc(t.description || "—")}</dd><dt>Recorded</dt><dd>${A.rel(t.created_at)}</dd></dl>`,
      actions: [
        { label: "Delete", kind: "danger", onClick: async (_, { close }) => { if (await deleteTx(t)) { close(); reload(); } } },
        { label: "Edit", kind: "primary", onClick: async (_, { close }) => { close(); if (await editTx(t)) reload(); } },
      ] });
  }
  async function deleteTx(t) {
    if (!(await A.confirm(`Delete this ${t.kind} of ${A.money(t.amount)}${t.description ? ` (“${t.description}”)` : ""}?`, { danger: true, confirmLabel: "Delete" }))) return false;
    await A.api("DELETE", `/api/admin/finance/tx/${t.id}`);
    A.toast("Transaction deleted", "ok");
    return true;
  }

  A.page("expenses", async (main, signal) => {
    const view = main.dataset.view, box = main.querySelector("#sec");
    await loadCats(true);
    main.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-add-tx]");
      if (b && (await editTx(null, b.dataset.addTx))) A.reload();
    }, { signal });
    if (view === "dashboard") {
      const s = await A.api("GET", "/api/admin/finance/stats");
      A._currency = s.currency;
      const net = s.month_income - s.month_expense;
      box.innerHTML = A.kpis([[A.money(s.total_income), "Total income", "", "ok"], [A.money(s.total_expense), "Total expenses", "", "bad"],
        [A.money(s.net), "Net balance", "", s.net < 0 ? "bad" : "ok"], [A.money(s.month_income), "Income this month"], [A.money(s.month_expense), "Expenses this month"],
        [A.money(net), "Net this month", "", net < 0 ? "bad" : ""]]) +
        `<div class="dash" style="margin-top:1rem">
          <section class="panel pad span-8"><h3 class="panel-title">Income vs expenses · 12 months</h3><div class="chart-box"><canvas id="c-ie"></canvas></div></section>
          <section class="panel pad span-4"><h3 class="panel-title">Spending by category · this month</h3><div class="chart-box">${s.month_categories.length ? '<canvas id="c-cat"></canvas>' : '<p class="dim small">No expenses this month.</p>'}</div></section>
          <section class="panel pad span-6"><h3 class="panel-title">Net trend</h3><div class="chart-box" style="height:200px"><canvas id="c-net"></canvas></div></section>
          <section class="panel pad span-6"><div class="row"><h3 class="panel-title" style="margin:0">Recent transactions</h3><span class="spacer"></span><a class="btn sm ghost" href="/admin/expenses/transactions">Ledger →</a></div>
            <div class="list" style="margin-top:.5rem" id="recent"></div></section></div>`;
      const rec = box.querySelector("#recent");
      rec.innerHTML = s.recent.map((t) => `<button type="button" class="list-item tx-li" data-id="${t.id}"><span class="t">${esc(t.description || t.category)}<br><span class="dim small">${esc(t.category)} · ${A.fmtDate(t.occurred_at.slice(0, 10), { day: "numeric", month: "short" })}</span></span>${amt(t)}</button>`).join("") || '<p class="dim small">No transactions yet. Add your first income or expense.</p>';
      $$(".tx-li", rec).forEach((b) => b.addEventListener("click", () => txDetail(s.recent.find((t) => String(t.id) === b.dataset.id), A.reload)));
      const lbl = s.months.map((m) => new Date(m + "-01T00:00:00").toLocaleDateString(undefined, { month: "short", year: "2-digit" }));
      const money = { callbacks: { label: (c) => `${c.dataset.label}: ${A.money(c.parsed.y ?? c.parsed)}` } };
      A.chart(box.querySelector("#c-ie"), { type: "bar", data: { labels: lbl, datasets: [{ label: "Income", data: s.income_series, backgroundColor: "#34d399", borderRadius: 3 }, { label: "Expenses", data: s.expense_series, backgroundColor: A.BLUE, borderRadius: 3 }] },
        options: { maintainAspectRatio: false, plugins: { tooltip: money, legend: { position: "bottom", labels: { boxWidth: 10 } } }, scales: { y: { beginAtZero: true } } } });
      const palette = ["#2f7dff", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#22d3ee", "#fb923c", "#e879f9", "#94a3b8", "#4ade80"];
      A.chart(box.querySelector("#c-cat"), { type: "doughnut", data: { labels: s.month_categories.map((c) => c.category), datasets: [{ data: s.month_categories.map((c) => c.amount), backgroundColor: palette, borderColor: "#000", borderWidth: 3 }] },
        options: { maintainAspectRatio: false, cutout: "62%", plugins: { tooltip: { callbacks: { label: (c) => `${c.label}: ${A.money(c.parsed)}` } }, legend: { position: "bottom", labels: { boxWidth: 10 } } } } });
      A.chart(box.querySelector("#c-net"), { type: "line", data: { labels: lbl, datasets: [{ label: "Net", data: s.income_series.map((v, i) => v - s.expense_series[i]), borderColor: A.BLUE, backgroundColor: A.BLUE_SOFT, fill: true, tension: 0.3 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: money } } });
      return;
    }
    if (view === "categories") return categoriesView(box);
    if (view === "monthly") return monthlyView(box);
    // ledger views
    const fixedKind = "";
    const p = new URLSearchParams(location.search);
    const urlKind = ["income", "expense"].includes(p.get("kind")) ? p.get("kind") : "";
    const state = { kind: urlKind, category: "", q: "", from: "", to: "", month: p.get("month") || "", sort: "newest", offset: 0 };
    const cats = await loadCats();
    box.innerHTML = `<div class="toolbar"><input type="search" data-f="q" placeholder="Search description or category…" aria-label="Search">
      ${fixedKind ? "" : '<select data-f="kind" aria-label="Type"><option value="">Income & expenses</option><option value="income">Income</option><option value="expense">Expenses</option></select>'}
      <select data-f="category" aria-label="Category"><option value="">All categories</option>${[...new Set(cats.items.filter((c) => !fixedKind || c.kind === fixedKind).map((c) => c.name))].map((c) => `<option>${esc(c)}</option>`).join("")}</select>
      <input type="month" data-f="month" aria-label="Month" value="${state.month}">
      <label class="small dim">From <input type="date" data-f="from" aria-label="From date"></label><label class="small dim">To <input type="date" data-f="to" aria-label="To date"></label>
      <select data-f="sort" aria-label="Sort"><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="amount_desc">Largest</option><option value="amount_asc">Smallest</option></select></div>
      <div id="txsum"></div><div id="txlist"></div>`;
    const list = box.querySelector("#txlist");
    let rows = [];
    const load = async (append = false) => {
      if (!append) state.offset = 0;
      const r = await A.api("GET", "/api/admin/finance/tx" + A.qs({ ...state, limit: 100 }));
      rows = append ? rows.concat(r.items) : r.items;
      box.querySelector("#txsum").innerHTML = `<div class="tx-summary"><span>${r.count} transaction${r.count === 1 ? "" : "s"}</span>${fixedKind !== "expense" ? `<span>Income <b class="amt income">${A.money(r.income)}</b></span>` : ""}${fixedKind !== "income" ? `<span>Expenses <b class="amt expense">${A.money(r.expense)}</b></span>` : ""}${!fixedKind ? `<span>Net <b>${A.money(r.net)}</b></span>` : ""}</div>`;
      if (!rows.length) return A.empty(list, "No transactions", "Nothing matches these filters yet.", `<button class="btn primary" data-add-tx="${fixedKind || "expense"}">Add ${fixedKind || "transaction"}</button>`);
      list.innerHTML = `<div class="panel table-wrap"><table class="data ledger"><thead><tr><th>Date</th><th>Description</th><th>Category</th><th style="text-align:right">Amount</th><th></th></tr></thead><tbody>${rows.map((t) => `
        <tr data-id="${t.id}" class="clickable"><td class="mono small">${A.fmtDate(t.occurred_at.slice(0, 10), { day: "numeric", month: "short", year: "2-digit" })}<div class="dim">${t.occurred_at.slice(11, 16)}</div></td>
        <td class="title-cell">${esc(t.description || "—")}</td><td><span class="chip">${esc(t.category)}</span></td><td style="text-align:right">${amt(t)}</td>
        <td><div class="row" style="justify-content:flex-end"><button class="btn sm icon ghost" data-e aria-label="Edit">${A.icon("edit")}</button><button class="btn sm icon ghost" data-d aria-label="Delete">${A.icon("trash")}</button></div></td></tr>`).join("")}</tbody></table></div>
        ${rows.length < r.count ? '<button class="btn" data-more style="margin-top:1rem">Load more</button>' : ""}`;
      $$("tr[data-id]", list).forEach((tr) => {
        const t = rows.find((x) => String(x.id) === tr.dataset.id);
        tr.addEventListener("click", async (e) => {
          if (e.target.closest("[data-e]")) { if (await editTx(t)) load(); return; }
          if (e.target.closest("[data-d]")) { if (await deleteTx(t)) load(); return; }
          txDetail(t, load);
        });
      });
      list.querySelector("[data-more]")?.addEventListener("click", () => { state.offset += 100; load(true); });
    };
    if (urlKind) box.querySelector('[data-f="kind"]').value = urlKind;
    $$("[data-f]", box).forEach((el) => el.addEventListener(el.tagName === "INPUT" && el.type === "search" ? "input" : "change", A.debounce(() => { state[el.dataset.f] = el.value; load(); }, 200)));
    load().catch((e) => A.errorState(list, e, load));
  });

  async function categoriesView(box) {
    const render = async (fresh) => {
      const c = await loadCats(fresh);
      box.innerHTML = `<section class="panel pad" style="margin-bottom:1rem"><div class="row wrap"><label class="small">Currency symbol <input id="cur" value="${esc(c.currency)}" maxlength="4" style="width:5rem;margin-left:.4rem"></label><button class="btn sm" id="cur-save">Save</button></div></section>
        <div class="dash">${["expense", "income"].map((k) => `<section class="panel pad span-6"><div class="row"><h3 class="panel-title" style="margin:0">${k === "expense" ? "Expense" : "Income"} categories</h3><span class="spacer"></span><button class="btn sm primary" data-add="${k}">${A.icon("plus")} Add</button></div>
          <div class="list" style="margin-top:.6rem">${c.items.filter((x) => x.kind === k).map((x) => `<div class="list-item" data-k="${k}" data-n="${esc(x.name)}"><span class="t">${esc(x.name)}</span><span class="m">${x.count} · ${A.money(x.amount)}</span>
            <button class="btn sm icon ghost" data-ren aria-label="Rename">${A.icon("edit")}</button>${x.name !== "Other" ? `<button class="btn sm icon ghost" data-rm aria-label="Remove">${A.icon("trash")}</button>` : ""}</div>`).join("")}</div></section>`).join("")}</div>`;
      box.querySelector("#cur-save").addEventListener("click", async () => {
        const s = (await A.api("GET", "/api/admin/settings")).settings.finance;
        await A.api("PUT", "/api/admin/settings/finance", { ...s, currency: box.querySelector("#cur").value || "₹" });
        A.toast("Currency saved", "ok"); render(true);
      });
      $$("[data-add]", box).forEach((b) => b.addEventListener("click", async () => {
        const r = await A.formModal({ title: `New ${b.dataset.add} category`, fields: [{ name: "name", label: "Name", required: true, full: true }], onSubmit: (d) => A.api("POST", "/api/admin/finance/categories", { kind: b.dataset.add, name: d.name }) });
        if (r) render(true);
      }));
      $$("[data-ren]", box).forEach((b) => b.addEventListener("click", async () => {
        const row = b.closest("[data-k]");
        const r = await A.formModal({ title: "Rename category", intro: "Existing transactions move to the new name.", fields: [{ name: "name", label: "Name", required: true, full: true }], values: { name: row.dataset.n },
          onSubmit: (d) => A.api("POST", "/api/admin/finance/categories", { kind: row.dataset.k, name: d.name, old_name: row.dataset.n }) });
        if (r) render(true);
      }));
      $$("[data-rm]", box).forEach((b) => b.addEventListener("click", async () => {
        const row = b.closest("[data-k]");
        if (!(await A.confirm(`Remove category “${row.dataset.n}”? Its transactions are kept and moved to “Other”.`, { danger: true, confirmLabel: "Remove" }))) return;
        await A.api("DELETE", "/api/admin/finance/categories", { kind: row.dataset.k, name: row.dataset.n });
        render(true);
      }));
    };
    render(true);
  }

  async function monthlyView(box) {
    const rows = await A.api("GET", "/api/admin/finance/monthly");
    if (!rows.length) return A.empty(box, "No months yet", "Monthly overviews appear once you record transactions.", '<button class="btn primary" data-add-tx="expense">Add expense</button>');
    box.innerHTML = `<section class="panel pad" style="margin-bottom:1rem"><div class="chart-box" style="height:220px"><canvas id="c-m"></canvas></div></section>
      <div class="panel table-wrap"><table class="data"><thead><tr><th>Month</th><th style="text-align:right">Income</th><th style="text-align:right">Expenses</th><th style="text-align:right">Net</th><th>Transactions</th><th></th></tr></thead><tbody>${rows.map((r) => `
      <tr><td class="title-cell">${new Date(r.month + "-01T00:00:00").toLocaleDateString(undefined, { month: "long", year: "numeric" })}</td><td style="text-align:right"><span class="amt income">${A.money(r.income)}</span></td>
      <td style="text-align:right"><span class="amt expense">${A.money(r.expense)}</span></td><td style="text-align:right"><b>${A.money(r.net)}</b></td><td>${r.count}</td>
      <td><a class="btn sm ghost" href="/admin/expenses/transactions?month=${r.month}">View →</a></td></tr>`).join("")}</tbody></table></div>`;
    const asc = [...rows].reverse();
    A.chart(box.querySelector("#c-m"), { type: "bar", data: { labels: asc.map((r) => r.month), datasets: [{ label: "Income", data: asc.map((r) => r.income), backgroundColor: "#34d399" }, { label: "Expenses", data: asc.map((r) => r.expense), backgroundColor: A.BLUE }] },
      options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } } });
  }
})();
