/* ASTRA — shared client utilities (public + admin). No inline scripts are used (strict CSP). */
(function () {
  "use strict";
  const ASTRA = (window.ASTRA = window.ASTRA || {});

  ASTRA.reducedMotion = () =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    document.documentElement.dataset.effects === "off";

  ASTRA.esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  ASTRA.csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

  /** fetch wrapper: JSON in/out, CSRF header, readable errors */
  ASTRA.api = async (method, url, data, opts = {}) => {
    const init = { method, headers: { "X-CSRF-Token": ASTRA.csrf(), Accept: "application/json" }, credentials: "same-origin" };
    if (opts.signal) init.signal = opts.signal;
    if (data instanceof FormData) init.body = data;
    else if (data !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(data);
    }
    let res;
    try {
      res = await fetch(url, init);
    } catch (e) {
      if (e.name === "AbortError") throw Object.assign(new Error(opts.abortMessage || "Request cancelled."), { status: 0, aborted: true });
      throw Object.assign(new Error("Network error — check your connection."), { status: 0 });
    }
    if (res.status === 401 && !opts.allow401) {
      window.location.href = (document.body.dataset.loginPath || "/") + "?next=" + encodeURIComponent(location.pathname);
      throw new Error("Session expired");
    }
    const type = res.headers.get("Content-Type") || "";
    const payload = type.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      const err = new Error((payload && payload.error) || `Request failed (${res.status})`);
      err.status = res.status;
      err.errors = payload && payload.errors;
      throw err;
    }
    return payload;
  };

  /* ---------- Toasts ---------- */
  ASTRA.toast = (msg, kind = "info", ms = 3800) => {
    let box = document.querySelector(".toasts");
    if (!box) {
      box = document.createElement("div");
      box.className = "toasts";
      box.setAttribute("role", "status");
      box.setAttribute("aria-live", "polite");
      document.body.appendChild(box);
    }
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    t.innerHTML = `<div>${ASTRA.esc(msg)}</div>`;
    box.appendChild(t);
    setTimeout(() => {
      t.classList.add("out");
      setTimeout(() => t.remove(), 320);
    }, ms);
  };

  /* ---------- Markdown enhancement: code blocks, copy buttons, external links ---------- */
  ASTRA.enhanceMarkdown = (root = document) => {
    root.querySelectorAll(".md pre > code, pre.snippet-code > code").forEach((code) => {
      const pre = code.parentElement;
      if (pre.parentElement.classList.contains("code-block")) return;
      const lang = ((code.className.match(/language-([\w+#-]+)/) || [])[1] || "").toLowerCase();
      if (window.hljs) {
        try {
          if (lang && window.hljs.getLanguage(lang)) window.hljs.highlightElement(code);
          else if (!lang) window.hljs.highlightElement(code);
        } catch (_) { /* ignore */ }
      }
      const wrap = document.createElement("div");
      wrap.className = "code-block";
      const head = document.createElement("div");
      head.className = "code-head";
      head.innerHTML = `<span><span class="dots"><i></i><i></i><i></i></span>${ASTRA.esc(lang || "code")}</span>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-btn";
      btn.textContent = "Copy";
      btn.setAttribute("aria-label", "Copy code to clipboard");
      btn.addEventListener("click", () => ASTRA.copy(code.innerText, btn));
      head.appendChild(btn);
      pre.parentNode.insertBefore(wrap, pre);
      wrap.appendChild(head);
      wrap.appendChild(pre);
    });
    root.querySelectorAll(".md a[href]").forEach((a) => {
      try {
        const u = new URL(a.getAttribute("href"), location.href);
        if (u.origin !== location.origin) {
          a.target = "_blank";
          a.rel = "noopener noreferrer nofollow";
        }
      } catch (_) { /* ignore */ }
    });
    root.querySelectorAll(".md img").forEach((img) => img.setAttribute("loading", "lazy"));
  };

  ASTRA.copy = async (text, btn) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    if (btn) {
      const old = btn.textContent;
      btn.textContent = "Copied";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = old;
        btn.classList.remove("copied");
      }, 1600);
    }
  };

  /* ---------- Animated counters ---------- */
  ASTRA.countUp = (el) => {
    const target = parseFloat(el.dataset.count || "0");
    if (ASTRA.reducedMotion() || !target) {
      el.textContent = target.toLocaleString();
      return;
    }
    const start = performance.now();
    const dur = 1400;
    const step = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased).toLocaleString();
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  ASTRA.observeCounters = (root = document) => {
    const els = root.querySelectorAll("[data-count]");
    if (!("IntersectionObserver" in window)) return els.forEach(ASTRA.countUp);
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          ASTRA.countUp(e.target);
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.4 });
    els.forEach((el) => io.observe(el));
  };

  /* ---------- Multi-page navigation polish ----------
     Real links + real routes (back/forward/refresh are native). We only add:
     a progress bar while the next page loads, and an exit fade on browsers
     without cross-document View Transitions. */
  const supportsVT = "CSSViewTransitionRule" in window;
  ASTRA.navigate = (href) => {
    const bar = document.getElementById("nav-progress");
    bar && bar.classList.add("on");
    if (!supportsVT && !ASTRA.reducedMotion()) {
      document.documentElement.classList.add("is-leaving");
      setTimeout(() => (location.href = href), 130);
    } else location.href = href;
  };
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download") || a.dataset.noTransition !== undefined) return;
    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin || url.pathname.startsWith("/api/") || url.pathname.startsWith("/media/")) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return; // in-page anchor
    e.preventDefault();
    ASTRA.navigate(url.href);
  });
  window.addEventListener("pageshow", () => { // restore state when returning via back/forward cache
    document.documentElement.classList.remove("is-leaving");
    document.getElementById("nav-progress")?.classList.remove("on");
  });

  document.addEventListener("DOMContentLoaded", () => {
    ASTRA.enhanceMarkdown();
    ASTRA.observeCounters();
  });
})();
