/* Journaling — personal daily journal with its own "magical sci-fi codex" theme.
   Autosaves to Turso; a local draft copy protects against refresh/crash until the save lands. */
(function () {
  "use strict";
  const A = window.ASTRA, esc = A.esc, $$ = A.$$;
  const DRAFT_KEY = (id) => `astra.diary.draft.${id || "new"}`;
  const store = {
    get: (k) => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (_) { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* storage full/blocked */ } },
    del: (k) => { try { localStorage.removeItem(k); } catch (_) { /* ignore */ } },
  };
  const longDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  /* drifting blue motes — tiny, paused when hidden, off for reduced motion */
  function motes(canvas, signal) {
    if (!canvas || A.reducedMotion()) return;
    const ctx = canvas.getContext("2d");
    let W, H, raf;
    const fit = () => { const r = canvas.getBoundingClientRect(); W = canvas.width = r.width; H = canvas.height = r.height; };
    fit();
    const ps = Array.from({ length: window.innerWidth < 700 ? 18 : 36 }, () => ({ x: Math.random() * W, y: Math.random() * H, r: Math.random() * 1.6 + 0.4, v: Math.random() * 0.25 + 0.05, p: Math.random() * 6 }));
    const step = () => {
      ctx.clearRect(0, 0, W, H);
      for (const q of ps) {
        q.y -= q.v; q.p += 0.02;
        if (q.y < -5) { q.y = H + 5; q.x = Math.random() * W; }
        ctx.globalAlpha = 0.25 + Math.sin(q.p) * 0.2;
        ctx.fillStyle = "#5aa2ff";
        ctx.beginPath(); ctx.arc(q.x + Math.sin(q.p) * 6, q.y, q.r, 0, 6.283); ctx.fill();
      }
      raf = requestAnimationFrame(step);
    };
    const vis = () => { cancelAnimationFrame(raf); if (!document.hidden) raf = requestAnimationFrame(step); };
    document.addEventListener("visibilitychange", vis, { signal });
    window.addEventListener("resize", fit, { signal });
    signal.addEventListener("abort", () => cancelAnimationFrame(raf));
    raf = requestAnimationFrame(step);
  }

  A.page("journaling", async (main, signal) => {
    motes(main.querySelector("#realm-motes"), signal);
    const box = main.querySelector("#sec");
    if (main.dataset.view === "entries") return entriesView(box);
    return writeView(main, box, signal);
  });

  async function writeView(main, box, signal) {
    let id = main.dataset.entryId ? Number(main.dataset.entryId) : null;
    let entry = id ? await A.api("GET", `/api/admin/diary/${id}`) : { entry_date: A.today(), title: "", content: "" };
    const local = store.get(DRAFT_KEY(id));
    let restored = false;
    if (local && (!id || local.saved_at > (entry.updated_at || "")) && (local.content !== entry.content || local.title !== entry.title)) {
      entry = { ...entry, ...local };
      restored = true;
    }
    const stats = await A.api("GET", "/api/admin/diary/stats").catch(() => null);
    box.innerHTML = `<div class="tome">
      <div class="tome-page">
        <div class="tome-meta">
          <label class="tome-date"><span class="sr-only">Entry date</span><input type="date" id="dy-date" value="${entry.entry_date}"></label>
          <span class="tome-longdate" id="dy-long">${longDate(entry.entry_date)}</span>
          <span class="spacer"></span><span class="tome-state" id="dy-state">${restored ? "Recovered unsaved words" : id ? "Sealed in the codex" : "A fresh page"}</span>
        </div>
        <input class="tome-title" id="dy-title" maxlength="200" placeholder="Title this day… (optional)" value="${esc(entry.title)}">
        <div class="tome-tools" role="toolbar" aria-label="Formatting">
          <button type="button" data-md="bold" title="Bold"><b>B</b></button><button type="button" data-md="italic" title="Italic"><i>I</i></button>
          <button type="button" data-md="h3" title="Heading">H</button><button type="button" data-md="ul" title="List">•</button><button type="button" data-md="quote" title="Quote">❝</button>
          <span class="spacer"></span><span class="tome-words" id="dy-words"></span>
        </div>
        <textarea class="tome-ink" id="dy-content" placeholder="Write anything… what happened, what you thought, what you want to remember.">${esc(entry.content)}</textarea>
      </div>
      <aside class="tome-side">
        <button class="realm-btn primary" type="button" id="dy-save">Seal entry <span class="kbd">Ctrl S</span></button>
        <button class="realm-btn" type="button" id="dy-new">✦ New entry</button>
        ${id ? '<button class="realm-btn danger" type="button" id="dy-del">Delete entry</button>' : ""}
        <div class="tome-card"><span class="realm-eyebrow">This day</span><div id="dy-sameday" class="small"></div></div>
        ${stats ? `<div class="tome-card"><span class="realm-eyebrow">Chronicle</span><div class="tome-stats"><b>${stats.entries}</b> entries<br><b>${stats.streak}</b>-day streak<br><b>${stats.this_month}</b> this month<br><b>${stats.words.toLocaleString()}</b> words written</div></div>` : ""}
      </aside></div>`;
    const $ = (s) => box.querySelector(s);
    const ta = $("#dy-content"), title = $("#dy-title"), date = $("#dy-date"), st = $("#dy-state");
    let dirty = restored, saving = false, timer = null;
    const words = () => ($("#dy-words").textContent = `${(ta.value.match(/\S+/g) || []).length} words`);
    words();
    const grow = () => { ta.style.height = "auto"; ta.style.height = Math.max(420, ta.scrollHeight) + "px"; };
    grow();
    const sameDay = async () => {
      const rows = await A.api("GET", `/api/admin/diary?date=${date.value}`);
      $("#dy-sameday").innerHTML = rows.length ? rows.map((r) => `<a href="/admin/journaling?entry=${r.id}" class="${r.id === id ? "on" : ""}">${esc(r.title || "Untitled")} <span class="dim">${A.fmtTime(r.created_at)}</span></a>`).join("") : '<span class="dim">No other entries for this date.</span>';
    };
    sameDay();
    A.guard = () => dirty && !saving;
    const save = async (manual) => {
      if (saving) { clearTimeout(timer); timer = setTimeout(() => save(manual), 500); return; }
      if (!dirty && !manual) return;
      if (!id && !ta.value.trim() && !title.value.trim()) return;
      saving = true;
      st.textContent = "Sealing…";
      st.className = "tome-state saving";
      try {
        const data = { entry_date: date.value || A.today(), title: title.value, content: ta.value };
        const saved = id ? await A.api("PUT", `/api/admin/diary/${id}`, data) : await A.api("POST", "/api/admin/diary", data);
        if (!id) {
          store.del(DRAFT_KEY(null));
          id = saved.id;
          history.replaceState(null, "", `/admin/journaling?entry=${id}`);
          sameDay();
        }
        store.del(DRAFT_KEY(id));
        dirty = false;
        st.textContent = `Sealed at ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
        st.className = "tome-state sealed";
        if (manual) A.toast("Entry sealed", "ok");
      } catch (e) {
        st.textContent = "Not saved: " + e.message + " (kept locally)";
        st.className = "tome-state error";
      } finally { saving = false; }
    };
    const changed = () => {
      dirty = true;
      st.textContent = "Writing…";
      st.className = "tome-state";
      words(); grow();
      store.set(DRAFT_KEY(id), { title: title.value, content: ta.value, entry_date: date.value, saved_at: new Date().toISOString() });
      clearTimeout(timer); timer = setTimeout(() => save(false), 1500);
    };
    [ta, title].forEach((el) => el.addEventListener("input", changed));
    date.addEventListener("change", () => { $("#dy-long").textContent = longDate(date.value); changed(); sameDay(); });
    A.mdToolbar(box, ta, changed);
    $("#dy-save").addEventListener("click", () => save(true));
    $("#dy-new").addEventListener("click", async () => { if (dirty) await save(true); A.go("/admin/journaling?new=" + Date.now()); });
    $("#dy-del")?.addEventListener("click", async () => {
      if (!(await A.confirm("Delete this journal entry permanently? This cannot be undone.", { danger: true, confirmLabel: "Delete" }))) return;
      await A.api("DELETE", `/api/admin/diary/${id}`);
      store.del(DRAFT_KEY(id));
      dirty = false;
      A.toast("Entry deleted", "ok");
      A.go("/admin/journaling/entries");
    });
    document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(true); } }, { signal, capture: true });
    signal.addEventListener("abort", () => { clearTimeout(timer); if (dirty) save(true); });
    window.addEventListener("pagehide", () => { if (dirty) save(true); }, { signal });
    (id ? ta : title).focus();
  }

  async function entriesView(box) {
    let month = A.today().slice(0, 7), q = "", day = "";
    box.innerHTML = `<div class="archive">
      <aside class="archive-cal"><div class="cal-head"><button type="button" class="realm-btn sm" data-m="-1" aria-label="Previous month">‹</button><b id="cal-title"></b><button type="button" class="realm-btn sm" data-m="1" aria-label="Next month">›</button></div>
        <div class="cal-grid" id="cal"></div><button type="button" class="realm-btn sm" id="cal-clear" style="margin-top:.6rem">Show whole month</button></aside>
      <section><input class="realm-search" type="search" id="aq" placeholder="Search your journal…" aria-label="Search journal"><div id="alist"></div></section></div>`;
    const $ = (s) => box.querySelector(s);
    const renderCal = async () => {
      const counts = await A.api("GET", `/api/admin/diary/calendar?month=${month}`);
      const first = new Date(month + "-01T00:00:00"), days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
      $("#cal-title").textContent = first.toLocaleDateString(undefined, { month: "long", year: "numeric" });
      const lead = (first.getDay() + 6) % 7;
      let html = ["M", "T", "W", "T", "F", "S", "S"].map((d) => `<span class="cal-dow">${d}</span>`).join("") + "<span></span>".repeat(lead);
      for (let i = 1; i <= days; i++) {
        const iso = `${month}-${String(i).padStart(2, "0")}`;
        html += `<button type="button" class="cal-day ${counts[iso] ? "has" : ""} ${iso === A.today() ? "today" : ""} ${iso === day ? "sel" : ""}" data-d="${iso}" aria-label="${iso}${counts[iso] ? `, ${counts[iso]} entries` : ""}">${i}</button>`;
      }
      $("#cal").innerHTML = html;
      $$(".cal-day", box).forEach((b) => b.addEventListener("click", () => { day = b.dataset.d; renderCal(); renderList(); }));
    };
    const renderList = async () => {
      const list = $("#alist");
      const rows = await A.api("GET", "/api/admin/diary" + A.qs({ q, month: q || day ? "" : month, date: day, limit: 200 }));
      if (!rows.length) {
        list.innerHTML = `<div class="archive-empty"><p>${q ? "No entries match that search." : "No entries here yet."}</p><a class="realm-btn primary" href="/admin/journaling">✒ Write today’s entry</a></div>`;
        return;
      }
      list.innerHTML = rows.map((r) => `<a class="scroll-card" href="/admin/journaling?entry=${r.id}">
        <span class="scroll-date">${longDate(r.entry_date)}</span><b>${esc(r.title || "Untitled entry")}</b>
        <span class="scroll-prev">${esc(A.excerpt(r.preview, 220))}</span></a>`).join("");
    };
    $$("[data-m]", box).forEach((b) => b.addEventListener("click", () => {
      const d = new Date(month + "-01T00:00:00");
      d.setMonth(d.getMonth() + Number(b.dataset.m));
      month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      day = "";
      renderCal(); renderList();
    }));
    $("#cal-clear").addEventListener("click", () => { day = ""; renderCal(); renderList(); });
    $("#aq").addEventListener("input", A.debounce((e) => { q = e.target.value.trim(); renderList(); }, 250));
    renderCal(); renderList();
  }
})();
