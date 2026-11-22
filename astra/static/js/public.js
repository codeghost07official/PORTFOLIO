/* ASTRA public exhibition behaviour */
(function () {
  "use strict";
  const A = window.ASTRA;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  document.addEventListener("DOMContentLoaded", () => {
    const year = $("#year");
    if (year) year.textContent = new Date().getFullYear();

    /* nav */
    const nav = $("#nav");
    const onScroll = () => nav && nav.classList.toggle("scrolled", window.scrollY > 10);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    const toggle = $("#nav-toggle"), links = $("#nav-links");
    toggle?.addEventListener("click", () => {
      const open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    $$("#nav-links a").forEach((a) => a.addEventListener("click", () => links.classList.remove("open")));

    /* reveal on scroll */
    // position-based (not IntersectionObserver) so fast scroll jumps never leave sections hidden
    let pending = $$(".reveal:not(.in)");
    if (A.reducedMotion()) pending.forEach((el) => el.classList.add("in"));
    else {
      let ticking = false;
      const reveal = () => {
        ticking = false;
        const limit = window.innerHeight * 0.92;
        pending = pending.filter((el) => {
          if (el.getBoundingClientRect().top < limit) { el.classList.add("in"); return false; }
          return true;
        });
        if (!pending.length) window.removeEventListener("scroll", onReveal);
      };
      const onReveal = () => { if (!ticking) { ticking = true; requestAnimationFrame(reveal); } };
      window.addEventListener("scroll", onReveal, { passive: true });
      window.addEventListener("resize", onReveal);
      reveal();
    }

    /* subtle 3D tilt on cards (pointer devices only) */
    if (!A.reducedMotion() && window.matchMedia("(hover: hover)").matches) {
      $$(".tilt").forEach((card) => {
        card.addEventListener("pointermove", (e) => {
          const r = card.getBoundingClientRect();
          const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
          card.style.transform = `perspective(900px) rotateX(${(-y * 1.5).toFixed(2)}deg) rotateY(${(x * 2).toFixed(2)}deg)`;
        });
        card.addEventListener("pointerleave", () => (card.style.transform = ""));
      });
    }

    /* liquid-glass specular sheen: disabled in the lighter design (CSS hides it), kept behind a flag */
    if (window.ASTRA_SHEEN && !A.reducedMotion() && window.matchMedia("(hover: hover) and (min-width: 761px)").matches) {
      let pending = null, frame = 0;
      document.addEventListener("pointermove", (e) => {
        pending = e;
        if (frame) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          const el = pending.target.closest && pending.target.closest(".panel, .glass");
          if (!el) return;
          const r = el.getBoundingClientRect();
          el.style.setProperty("--mx", `${pending.clientX - r.left}px`);
          el.style.setProperty("--my", `${pending.clientY - r.top}px`);
        });
      }, { passive: true });
    }

    /* discreet admin entry (UI convenience only — the server enforces auth) */
    const gate = document.body.dataset.gate, mode = document.body.dataset.gateMode;
    if (gate && mode === "logo_dblclick") {
      $("#brand")?.addEventListener("dblclick", (e) => {
        e.preventDefault();
        location.href = gate;
      });
    }
    if (gate && mode === "keyboard") {
      let buf = "";
      document.addEventListener("keydown", (e) => {
        if (e.target.closest("input, textarea, select, [contenteditable]")) return;
        buf = (buf + e.key.toLowerCase()).slice(-5);
        if (buf === "astra") location.href = gate;
      });
    }

    /* exhibition: filtering + sorting synced to the URL (refresh/share keeps the view) */
    const grid = $("#pf-grid");
    if (grid) {
      const q = $("#pf-q"), tech = $("#pf-tech"), sort = $("#pf-sort"), empty = $("#pf-empty"), count = $("#pf-count");
      const params = new URLSearchParams(location.search);
      let cat = params.get("category") || "";
      if (params.get("sort") && sort) sort.value = params.get("sort");
      const cards = $$(".proj-card", grid);
      const apply = (push = false) => {
        const term = (q.value || "").toLowerCase().trim();
        const t = tech ? tech.value : "";
        let shown = 0;
        cards.forEach((c) => {
          const ok = (!cat || c.dataset.category === cat) && (!t || c.dataset.techs.split("|").includes(t)) &&
            (!term || c.dataset.search.includes(term));
          c.classList.toggle("hidden", !ok);
          if (ok) { shown++; c.classList.add("in"); }
        });
        const mode = sort ? sort.value : "featured";
        const sorted = [...cards].sort((a, b) => mode === "name" ? a.dataset.name.localeCompare(b.dataset.name)
          : mode === "newest" ? b.dataset.date.localeCompare(a.dataset.date)
          : (Number(b.dataset.featured) - Number(a.dataset.featured)));
        sorted.forEach((c) => grid.appendChild(c));
        empty.classList.toggle("hidden", shown > 0);
        if (count) count.textContent = shown + " of " + cards.length + " exhibits";
        $$("#pf-cats a").forEach((a) => a.classList.toggle("on", a.dataset.cat === cat));
        const url = new URL(location.href);
        [["category", cat], ["tech", t], ["q", q.value.trim()], ["sort", mode === "featured" ? "" : mode]]
          .forEach(([k, v]) => (v ? url.searchParams.set(k, v) : url.searchParams.delete(k)));
        history[push ? "pushState" : "replaceState"]({ cat }, "", url);
      };
      q.addEventListener("input", () => apply(false));
      tech?.addEventListener("change", () => apply(false));
      sort?.addEventListener("change", () => apply(false));
      $$("#pf-cats a").forEach((a) => a.addEventListener("click", (e) => {
        e.preventDefault(); // instant filter; the href still works without JS and on refresh
        cat = a.dataset.cat;
        apply(true);
      }));
      window.addEventListener("popstate", () => {
        const p = new URLSearchParams(location.search);
        cat = p.get("category") || "";
        q.value = p.get("q") || "";
        if (tech) tech.value = p.get("tech") || "";
        if (sort) sort.value = p.get("sort") || "featured";
        apply(false);
      });
      apply(false);
    }

    /* quick look preview */
    $$("[data-quicklook]").forEach((b) => b.addEventListener("click", () => {
      const tpl = b.closest(".proj-card").querySelector("template.ql-data");
      openQuickLook(tpl.content.cloneNode(true), b);
    }));

    /* reading progress + generated documentation table of contents */
    const prog = $("#read-progress");
    if (prog) {
      const upd = () => {
        const h = document.documentElement.scrollHeight - innerHeight;
        prog.style.width = (h > 0 ? (scrollY / h) * 100 : 0) + "%";
      };
      window.addEventListener("scroll", upd, { passive: true });
      upd();
    }
    const docToc = $("#doc-toc"), docs = $("#s-docs .md");
    if (docToc && docs) {
      const heads = $$("h2[id], h3[id]", docs);
      if (heads.length >= 3) {
        docToc.innerHTML = heads.slice(0, 24).map((h) => '<a href="#' + h.id + '" class="' + h.tagName.toLowerCase() + '">' + A.esc(h.textContent) + "</a>").join("");
      }
    }

    /* lightbox */
    $$("[data-lightbox]").forEach((b) => b.addEventListener("click", () => {
      const box = document.createElement("div");
      box.className = "lightbox";
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-label", "Screenshot");
      box.tabIndex = -1;
      const img = document.createElement("img");
      img.src = b.dataset.lightbox;
      img.alt = "";
      box.appendChild(img);
      const close = () => { box.remove(); b.focus(); };
      box.addEventListener("click", close);
      box.addEventListener("keydown", (e) => e.key === "Escape" && close());
      document.body.appendChild(box);
      box.focus();
    }));

    /* table of contents highlight */
    const toc = $$(".toc a");
    if (toc.length && "IntersectionObserver" in window) {
      const map = new Map(toc.map((a) => [a.getAttribute("href").slice(1), a]));
      const io = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            toc.forEach((a) => a.classList.remove("active"));
            map.get(e.target.id)?.classList.add("active");
          }
        });
      }, { rootMargin: "-30% 0px -60% 0px" });
      map.forEach((_, id) => { const el = document.getElementById(id); if (el) io.observe(el); });
    }

    initGuide();
  });

  function openQuickLook(content, opener) {
    const back = document.createElement("div");
    back.className = "modal-backdrop";
    back.innerHTML = '<div class="modal wide quicklook" role="dialog" aria-modal="true" aria-label="Project preview"><div class="modal-head"><span class="label">Quick look</span><span class="spacer"></span><button class="btn icon ghost sm" data-x aria-label="Close">&#x2715;</button></div><div class="modal-body"></div></div>';
    back.querySelector(".modal-body").appendChild(content);
    const close = () => {
      back.classList.add("closing");
      setTimeout(() => back.remove(), 170);
      document.removeEventListener("keydown", onKey);
      if (opener) opener.focus();
    };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
    back.querySelector("[data-x]").addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.appendChild(back);
    back.querySelector(".ql a, [data-x]").focus();
  }

  /* ---------- public AI guide ---------- */
  function initGuide() {
    const fab = $("#guide-fab"), panel = $("#guide-panel");
    if (!fab || !panel) return;
    const log = $("#guide-log"), form = $("#guide-form"), input = $("#guide-input"), suggest = $("#guide-suggest");
    const history = [];
    let busy = false, greeted = false;

    const add = (role, content, isHtml = false, cls = "") => {
      const el = document.createElement("div");
      el.className = `msg ${role === "user" ? "user" : "bot md"} ${cls}`;
      if (isHtml) el.innerHTML = content; // server-rendered & sanitised markdown
      else el.textContent = content;
      log.appendChild(el);
      log.scrollTop = log.scrollHeight;
      if (isHtml) A.enhanceMarkdown(el.parentElement);
      return el;
    };
    const open = () => {
      panel.classList.remove("hidden");
      fab.setAttribute("aria-expanded", "true");
      if (!greeted) {
        greeted = true;
        add("bot", panel.dataset.greeting || "Hello! Ask me about any project.");
        if (panel.dataset.online !== "1") add("bot", "The AI guide isn't connected yet — feel free to browse the projects directly.", false, "err");
      }
      setTimeout(() => input.focus(), 50);
    };
    const close = () => {
      panel.classList.add("hidden");
      fab.setAttribute("aria-expanded", "false");
      fab.focus();
    };
    fab.addEventListener("click", () => (panel.classList.contains("hidden") ? open() : close()));
    $("#guide-close").addEventListener("click", close);
    panel.addEventListener("keydown", (e) => e.key === "Escape" && close());
    $$("[data-open-guide]").forEach((b) => b.addEventListener("click", open));

    const send = async (text) => {
      if (busy || !text.trim()) return;
      busy = true;
      suggest.classList.add("hidden");
      add("user", text);
      const typing = add("bot", "");
      typing.innerHTML = '<span class="typing" aria-label="Thinking"><i></i><i></i><i></i></span>';
      try {
        const res = await A.api("POST", "/api/public/chat", { message: text, history: history.slice(-6) });
        typing.remove();
        add("bot", res.html, true);
        history.push({ role: "user", text }, { role: "assistant", text: res.reply });
      } catch (e) {
        typing.remove();
        add("bot", e.message || "Something went wrong.", false, "err");
      } finally {
        busy = false;
      }
    };
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = input.value;
      input.value = "";
      send(text);
    });
    $$(".chip", suggest).forEach((c) => c.addEventListener("click", () => send(c.textContent)));
  }
})();
