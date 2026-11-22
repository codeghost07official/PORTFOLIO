/* Persistent personal-assistant HUD. Lives in the admin shell (outside #main), so client-side
   navigation never resets it. Text + speech for every reply, voice input, confirm-first actions. */
(function () {
  "use strict";
  const A = window.ASTRA, esc = A.esc;
  const $ = (s) => document.querySelector(s);
  const SS = {
    get: (k, d) => { try { const v = sessionStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
    set: (k, v) => { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* ignore */ } },
  };
  const synth = "speechSynthesis" in window ? window.speechSynthesis : null;
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  let cfg = { name: "ASTRA", voice: { enabled: true, autospeak: true, voice_name: "", rate: 1, pitch: 1, volume: 1 } };
  let cid = SS.get("astra.hud.cid", null), busy = false, rec = null, listening = false, loadedFor = null;
  let muted = SS.get("astra.hud.muted", false);

  const setState = (s, text) => {
    $("#hud").dataset.state = s;
    $("#hud-status").textContent = text || { idle: "Standing by", listening: "Listening…", thinking: "Thinking…", speaking: "Speaking" }[s];
  };

  /* ---------------- voice output ---------------- */
  let voiceList = [];
  const loadVoices = () => new Promise((resolve) => {
    if (!synth) return resolve([]);
    const got = synth.getVoices();
    if (got.length) { voiceList = got; return resolve(got); }
    synth.addEventListener("voiceschanged", () => { voiceList = synth.getVoices(); resolve(voiceList); }, { once: true });
    setTimeout(() => resolve(synth.getVoices()), 1500);
  });
  /* Voice ranking: British English first, then known female voices, then natural/neural quality.
     Known male voices are pushed down. The winner is cached so the voice never changes between replies. */
  const FEMALE = /(libby|sonia|maisie|hazel|susan|kate|serena|martha|emily|amy|abbi|bella|hollie|olivia|ellie|mia|female|uk english female)/i;
  const MALE = /(george|ryan|thomas|oliver|alfie|elliot|ethan|noah|daniel|arthur|male\b|uk english male)/i;
  function scoreVoice(x) {
    let s = 0;
    if (/en[-_]GB/i.test(x.lang)) s += 100; else if (/^en/i.test(x.lang)) s += 20; else return -1;
    if (FEMALE.test(x.name)) s += 50;
    if (MALE.test(x.name)) s -= 80;
    if (/natural|neural|online/i.test(x.name)) s += 15;
    if (x.localService === false) s += 2;
    return s;
  }
  const rankVoices = (list) => list.map((x) => ({ v: x, s: scoreVoice(x) })).filter((r) => r.s >= 0).sort((a, b) => b.s - a.s);
  const isBritishFemale = (x) => /en[-_]GB/i.test(x.lang) && FEMALE.test(x.name) && !MALE.test(x.name);
  let chosen = null;
  function pickVoice(v) {
    const list = voiceList.length ? voiceList : (synth ? synth.getVoices() : []);
    if (v.voice_name) { const exact = list.find((x) => x.name === v.voice_name); if (exact) return exact; }
    if (chosen && list.includes(chosen)) return chosen;
    const top = rankVoices(list)[0];
    chosen = top ? top.v : null;
    return chosen;
  }
  const plain = (t) => String(t || "").replace(/```[\s\S]*?```/g, " (code shown on screen) ").replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/[#*_>~|]/g, "").replace(/\s+/g, " ").trim();
  function speak(text, override) {
    const v = { ...cfg.voice, ...(override || {}) };
    if (!synth || (!override && (muted || !v.enabled))) return;
    try { speakNow(text, v); } catch (_) { setState("idle"); } // speech is optional: text is already on screen
  }
  function speakNow(text, v) {
    synth.cancel();
    const voice = pickVoice(v);
    const parts = plain(text).match(/[^.!?]+[.!?]*\s*/g) || [plain(text)]; // short chunks avoid Chrome's long-utterance cut-off
    parts.forEach((p, i) => {
      const u = new SpeechSynthesisUtterance(p);
      if (voice) u.voice = voice;
      u.lang = voice ? voice.lang : "en-GB";
      u.rate = v.rate; u.pitch = v.pitch; u.volume = v.volume;
      if (i === 0) u.onstart = () => setState("speaking");
      if (i === parts.length - 1) { u.onend = () => setState("idle"); u.onerror = () => setState("idle"); }
      synth.speak(u);
    });
  }
  const stopSpeaking = () => { if (synth) synth.cancel(); if ($("#hud").dataset.state === "speaking") setState("idle"); };

  /* ---------------- voice input ---------------- */
  function toggleMic() {
    if (!Rec) return A.toast("Voice input isn't supported in this browser. Try Chrome or Edge.", "warn");
    if (listening) { rec && rec.stop(); return; }
    stopSpeaking();
    rec = new Rec();
    rec.lang = navigator.language || "en-GB";
    rec.interimResults = true;
    rec.continuous = false;
    const ta = $("#hud-text");
    let finalText = "";
    rec.onstart = () => { listening = true; $("#hud-mic").setAttribute("aria-pressed", "true"); setState("listening"); };
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript; else interim += e.results[i][0].transcript;
      }
      ta.value = (finalText + interim).trim();
    };
    rec.onerror = (e) => { if (e.error !== "no-speech" && e.error !== "aborted") A.toast(`Microphone: ${e.error}`, "warn"); };
    rec.onend = () => {
      listening = false;
      $("#hud-mic").setAttribute("aria-pressed", "false");
      if ($("#hud").dataset.state === "listening") setState("idle");
      if (finalText.trim()) send(finalText.trim());
    };
    rec.start();
  }

  /* ---------------- conversation ---------------- */
  const log = () => $("#hud-log");
  function bubble(m) {
    if (m.role === "user") return A.h(`<div class="hud-msg user"><div class="hud-b">${esc(m.content)}</div></div>`);
    const el = A.h(`<div class="hud-msg ai" data-mid="${m.id}"><div class="hud-b md">${m.html || esc(m.content)}</div>
      <div class="hud-meta">${(m.sources || []).slice(0, 3).map((s) => `<span class="hud-src" title="${esc(s.origin)}">${esc(s.title)}</span>`).join("")}
      <button class="hud-mini" type="button" data-replay title="Replay" aria-label="Replay this reply">▶</button></div></div>`);
    el.querySelector("[data-replay]").addEventListener("click", () => speak(m.content, { enabled: true }));
    (m.actions || []).forEach((a, i) => el.appendChild(actionCard(m.id, a, i)));
    A.enhanceMarkdown(el);
    return el;
  }
  function actionCard(mid, a, i) {
    const c = A.h(`<div class="hud-action ${a.destructive ? "danger" : ""} ${a.status}"><span>${a.destructive ? "⚠ " : ""}${esc(a.summary)}</span><span class="hud-action-btns"></span></div>`);
    const btns = c.querySelector(".hud-action-btns");
    if (a.status === "pending") {
      const yes = A.h(`<button type="button" class="hud-mini on">${a.destructive ? "Delete" : "Confirm"}</button>`), no = A.h('<button type="button" class="hud-mini">Dismiss</button>');
      const go = async (decision) => {
        if (decision === "confirm" && a.destructive && !(await A.confirm(`${a.summary}. This cannot be undone.`, { danger: true, confirmLabel: "Delete" }))) return;
        yes.disabled = no.disabled = true;
        try {
          const r = await A.api("POST", `/api/admin/ai/messages/${mid}/actions/${i}`, { decision });
          c.replaceWith(actionCard(mid, r.action, i));
          if (decision === "confirm") { A.toast(r.result.message, "ok"); document.dispatchEvent(new CustomEvent("astra:changed", { detail: { entity: "todos" } })); }
        } catch (e) { A.toast(e.message, "err"); yes.disabled = no.disabled = false; }
      };
      yes.addEventListener("click", () => go("confirm"));
      no.addEventListener("click", () => go("dismiss"));
      btns.append(no, yes);
    } else btns.innerHTML = a.status === "done" ? `<span class="ok">✓ Done</span>${a.result && a.result.link ? ` <a href="${esc(a.result.link)}">Open</a>` : ""}` : '<span class="dim">Dismissed</span>';
    return c;
  }
  function greet() {
    log().innerHTML = `<div class="hud-hello"><b>${esc(cfg.name)}</b> at your service, Sir.<br><span>Type or tap the mic. Try “What’s due today?”, “Add a task to call the bank tomorrow”, or “Summarise my project journal”.</span></div>`;
  }
  async function loadConversation() {
    if (!cid) { greet(); loadedFor = null; return; }
    if (loadedFor === cid) return;
    try {
      const d = await A.api("GET", `/api/admin/ai/conversations/${cid}/messages`);
      log().innerHTML = "";
      d.messages.slice(-40).forEach((m) => log().appendChild(bubble(m)));
      if (!d.messages.length) greet();
      loadedFor = cid;
      log().scrollTop = log().scrollHeight;
    } catch (_) { cid = null; SS.set("astra.hud.cid", null); greet(); }
  }
  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true;
    stopSpeaking();
    $("#hud-text").value = "";
    autoGrow();
    try {
      if (!cid) {
        const c = await A.api("POST", "/api/admin/ai/conversations", {});
        cid = c.id; loadedFor = cid; SS.set("astra.hud.cid", cid);
        log().innerHTML = "";
      }
      log().querySelector(".hud-hello")?.remove();
      log().appendChild(bubble({ role: "user", content: text }));
      const typing = A.h('<div class="hud-msg ai"><div class="hud-b hud-wait"><span class="typing"><i></i><i></i><i></i></span><span class="hud-elapsed">Thinking…</span></div></div>');
      const t0 = Date.now(), ctl = new AbortController();
      const tick = setInterval(() => {
        const sec = Math.round((Date.now() - t0) / 1000);
        typing.querySelector(".hud-elapsed").textContent = sec < 6 ? "Thinking…" : sec < 20 ? `Thinking… ${sec}s` : `Still working, the model is busy… ${sec}s`;
        $("#hud-status").textContent = `Thinking… ${sec}s`;
      }, 1000);
      const kill = setTimeout(() => ctl.abort(), 70000);
      log().appendChild(typing);
      log().scrollTop = log().scrollHeight;
      setState("thinking");
      try {
        const r = await A.api("POST", `/api/admin/ai/conversations/${cid}/messages`, { message: text, today: A.today() },
          { signal: ctl.signal, abortMessage: "No answer after 70 seconds. The AI service may be overloaded; please try again." });
        clearInterval(tick); clearTimeout(kill);
        typing.replaceWith(bubble(r.message));
        log().scrollTop = log().scrollHeight;
        setState("idle");
        if (cfg.voice.autospeak) setTimeout(() => speak(r.message.content), 0); // text first, speech never blocks it
      } catch (e) {
        clearInterval(tick); clearTimeout(kill);
        typing.replaceWith(A.h(`<div class="hud-msg ai"><div class="hud-b err">${esc(e.message)}</div></div>`));
        setState("idle", "Couldn't answer");
        $("#hud-text").value = text;
      }
      log().scrollTop = log().scrollHeight;
    } finally { busy = false; }
  }
  const autoGrow = () => { const t = $("#hud-text"); t.style.height = "auto"; t.style.height = Math.min(140, t.scrollHeight) + "px"; };

  /* ---------------- open / close ---------------- */
  function open() {
    $("#hud-panel").classList.remove("hidden");
    $("#hud-launcher").setAttribute("aria-expanded", "true");
    $("#hud").classList.add("open");
    SS.set("astra.hud.open", true);
    loadConversation();
    setTimeout(() => $("#hud-text").focus(), 60);
  }
  function close() {
    $("#hud-panel").classList.add("hidden");
    $("#hud-launcher").setAttribute("aria-expanded", "false");
    $("#hud").classList.remove("open");
    SS.set("astra.hud.open", false);
    stopSpeaking();
    if (listening && rec) rec.stop();
  }
  function applySettings(next) {
    cfg = next;
    $("#hud-name").textContent = cfg.name;
    $("#hud-volume").value = cfg.voice.volume;
    $("#hud-rate").value = cfg.voice.rate;
    paintMute();
    fillVoices();
  }
  const paintMute = () => {
    const b = $("#hud-mute");
    b.textContent = muted || !cfg.voice.enabled ? "🔇" : "🔊";
    b.setAttribute("aria-pressed", String(muted));
    b.title = muted ? "Unmute voice" : "Mute voice";
  };
  async function fillVoices() {
    const list = await loadVoices();
    $("#hud-voice").innerHTML = `<option value="">Auto (British female)</option>` + rankVoices(list).map(({ v }) => `<option value="${esc(v.name)}" ${v.name === cfg.voice.voice_name ? "selected" : ""}>${esc(v.name)}</option>`).join("");
  }
  const persistVoice = A.debounce(async () => {
    try { cfg = await A.api("PUT", "/api/admin/settings/assistant", cfg); } catch (_) { /* keep local */ }
  }, 800);

  A.hud = {
    open, close, speak, applySettings, voices: loadVoices,
    rankVoices: (list) => rankVoices(list).map((r) => r.v), isBritishFemale,
    activeVoice: () => pickVoice(cfg.voice),
    autoVoice: () => { const top = rankVoices(voiceList.length ? voiceList : synth ? synth.getVoices() : [])[0]; return top ? top.v : null; },
    openConversation: (id) => { cid = id; loadedFor = null; SS.set("astra.hud.cid", id); open(); },
    forget: (id) => { if (cid === id) { cid = null; loadedFor = null; SS.set("astra.hud.cid", null); greet(); } },
  };

  document.addEventListener("DOMContentLoaded", async () => {
    if (!$("#hud")) return;
    $("#hud-launcher").addEventListener("click", () => ($("#hud-panel").classList.contains("hidden") ? open() : close()));
    $("#hud-close").addEventListener("click", close);
    $("#hud-new").addEventListener("click", () => { cid = null; loadedFor = null; SS.set("astra.hud.cid", null); stopSpeaking(); greet(); $("#hud-text").focus(); });
    $("#hud-mute").addEventListener("click", () => { muted = !muted; SS.set("astra.hud.muted", muted); if (muted) stopSpeaking(); paintMute(); });
    $("#hud-settings-btn").addEventListener("click", () => { const c = $("#hud-controls"); c.classList.toggle("hidden"); $("#hud-settings-btn").setAttribute("aria-expanded", String(!c.classList.contains("hidden"))); });
    $("#hud-stop").addEventListener("click", stopSpeaking);
    $("#hud-volume").addEventListener("input", (e) => { cfg.voice.volume = Number(e.target.value); persistVoice(); });
    $("#hud-rate").addEventListener("input", (e) => { cfg.voice.rate = Number(e.target.value); persistVoice(); });
    $("#hud-voice").addEventListener("change", (e) => { cfg.voice.voice_name = e.target.value; chosen = null; persistVoice(); speak("Voice selected, Sir.", { enabled: true }); });
    $("#hud-mic").addEventListener("click", toggleMic);
    if (!Rec) $("#hud-mic").title = "Voice input needs Chrome or Edge";
    const ta = $("#hud-text");
    ta.addEventListener("input", autoGrow);
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(ta.value); } });
    $("#hud-form").addEventListener("submit", (e) => { e.preventDefault(); send(ta.value); });
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j") { e.preventDefault(); $("#hud-panel").classList.contains("hidden") ? open() : close(); }
      if (e.key === "Escape" && !$("#hud-panel").classList.contains("hidden") && !document.querySelector(".modal-backdrop")) close();
    });
    try { applySettings((await A.api("GET", "/api/admin/settings")).settings.assistant); } catch (_) { paintMute(); }
    if (SS.get("astra.hud.open", false)) open();
  });
})();
