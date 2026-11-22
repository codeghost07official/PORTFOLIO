/* AI Assistant section: personality & context, voice, memory bank, conversation history. */
(function () {
  "use strict";
  const A = window.ASTRA, esc = A.esc, $$ = A.$$;
  const CTX = [["projects", "Projects", "Project names, status and exhibits"], ["project_journals", "Project journals", "Technical development notes"],
    ["tasks", "Tasks", "Your to-do list"], ["diary", "Personal journal", "Your private daily entries (off by default)"],
    ["medicines", "Medicines", "Today’s schedule and doses (off by default)"], ["expenses", "Expenses", "Financial summaries (off by default)"],
    ["conversations", "Past conversations", "Recall earlier chats"], ["memory", "Memory bank", "Facts you asked it to remember"]];

  A.page("assistant", async (main) => {
    const view = main.dataset.view, box = main.querySelector("#sec");
    main.querySelector("[data-open-hud]")?.addEventListener("click", () => A.hud && A.hud.open());
    const all = (await A.api("GET", "/api/admin/settings")).settings;
    const cfg = all.assistant;
    const save = async (patch, msg = "Saved") => {
      const next = await A.api("PUT", "/api/admin/settings/assistant", { ...cfg, ...patch });
      Object.assign(cfg, next);
      A.hud && A.hud.applySettings(next);
      A.toast(msg, "ok");
    };

    if (view === "settings") {
      box.innerHTML = `<form id="as-form" class="stack" novalidate>
        <section class="panel pad"><h3 class="panel-title">Identity & personality</h3><div class="form-grid">
          <div class="field" data-field="name"><label>Assistant name</label><input name="name" value="${esc(cfg.name)}" maxlength="40"></div>
          <div class="field"><label>Reply length (max sentences)</label><input name="max_sentences" type="number" min="1" max="8" value="${cfg.max_sentences}"><span class="hint">Default 2. It goes longer only when you ask for detail.</span></div>
          <div class="field full"><label>Personality</label><textarea name="personality" rows="3">${esc(cfg.personality)}</textarea></div>
          <div class="field full"><label>About me (what the assistant should know about you)</label><textarea name="about_me" rows="5" placeholder="Interests, goals, how you like to work, preferences…">${esc(cfg.about_me)}</textarea></div>
          <div class="field full"><label>Extra system instructions</label><textarea name="instructions" rows="3" placeholder="Optional rules, e.g. “Always give me the next concrete step.”">${esc(cfg.instructions)}</textarea></div>
          <div class="field"><label>Model override (blank = default chain)</label><input name="model" value="${esc(cfg.model)}" placeholder="gemini-3.8-flash"></div>
          <div class="field"><label>Creativity (temperature 0–1.5)</label><input name="temperature" type="number" step="0.1" min="0" max="1.5" value="${cfg.temperature}"></div>
        </div></section>
        <section class="panel pad"><h3 class="panel-title">Context: what the assistant may read</h3><p class="muted small" style="margin-top:0">It retrieves only the relevant pieces from enabled sources for each question, never the whole database. Sensitive areas are off by default.</p>
          <div class="ctx-grid">${CTX.map(([k, l, d]) => `<label class="ctx-item"><span class="switch"><input type="checkbox" name="ctx_${k}" ${cfg.context[k] ? "checked" : ""}><span class="track"></span></span><span><b>${l}</b><small>${d}</small></span></label>`).join("")}</div></section>
        <div class="row"><span class="spacer"></span><button class="btn primary" type="submit">Save assistant settings</button></div></form>`;
      const f = box.querySelector("#as-form");
      f.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await save({ name: f.name.value, max_sentences: Number(f.max_sentences.value), personality: f.personality.value, about_me: f.about_me.value,
            instructions: f.instructions.value, model: f.model.value.trim(), temperature: Number(f.temperature.value),
            context: Object.fromEntries(CTX.map(([k]) => [k, f[`ctx_${k}`].checked])) }, "Assistant updated");
        } catch (err) { A.showErrors(f, err); A.toast(err.message, "err"); }
      });
      return;
    }

    if (view === "voice") {
      const v = cfg.voice;
      const all = A.hud ? await A.hud.voices() : [];
      const voices = A.hud ? A.hud.rankVoices(all) : all;
      const auto = A.hud?.autoVoice(), brit = voices.filter((x) => A.hud.isBritishFemale(x));
      const note = !("speechSynthesis" in window) ? "" : !voices.length
        ? '<div class="error-state">No English voices are installed in this browser, so replies will be text only.</div>'
        : brit.length ? `<p class="muted small">Auto picks <b>${esc(auto?.name || "")}</b>. ${brit.length} British female voice${brit.length > 1 ? "s" : ""} found on this device.</p>`
        : `<p class="small" style="color:var(--warn)">No British female voice is installed on this device. Auto uses the closest match: <b>${esc(auto?.name || "none")}</b> (${esc(auto?.lang || "")}). Microsoft Edge on Windows includes natural British voices such as Libby and Sonia.</p>`;
      box.innerHTML = `<section class="panel pad"><h3 class="panel-title">Voice</h3>
        ${!("speechSynthesis" in window) ? '<div class="error-state">This browser has no speech synthesis, so replies will be text only.</div>' : ""}
        ${note}
        <form id="vf" class="form-grid" novalidate>
          <div class="field full"><label class="switch"><input type="checkbox" name="enabled" ${v.enabled ? "checked" : ""}><span class="track"></span>Voice enabled</label></div>
          <div class="field full"><label class="switch"><input type="checkbox" name="autospeak" ${v.autospeak ? "checked" : ""}><span class="track"></span>Speak every reply automatically</label></div>
          <div class="field full"><label>Voice</label><select name="voice_name"><option value="">Auto: female British English, nearest available</option>${voices.map((x) => `<option value="${esc(x.name)}" ${x.name === v.voice_name ? "selected" : ""}>${esc(x.name)} (${esc(x.lang)})${A.hud.isBritishFemale(x) ? " · British female" : ""}</option>`).join("")}</select>
            <span class="hint">Available voices depend on your OS and browser. Microsoft Edge on Windows offers natural British voices such as “Libby” or “Sonia”.</span></div>
          <div class="field"><label>Speed <span class="mono" id="rate-v">${v.rate}</span></label><input type="range" name="rate" min="0.6" max="1.6" step="0.05" value="${v.rate}"></div>
          <div class="field"><label>Pitch <span class="mono" id="pitch-v">${v.pitch}</span></label><input type="range" name="pitch" min="0.5" max="1.5" step="0.05" value="${v.pitch}"></div>
          <div class="field"><label>Volume <span class="mono" id="vol-v">${v.volume}</span></label><input type="range" name="volume" min="0" max="1" step="0.05" value="${v.volume}"></div>
          <div class="field full"><div class="row"><button class="btn" type="button" id="v-test">▶ Test voice</button><span class="spacer"></span><button class="btn primary" type="submit">Save voice</button></div></div>
        </form></section>`;
      const f = box.querySelector("#vf");
      const read = () => ({ enabled: f.enabled.checked, autospeak: f.autospeak.checked, voice_name: f.voice_name.value, lang: "en-GB",
        rate: Number(f.rate.value), pitch: Number(f.pitch.value), volume: Number(f.volume.value) });
      f.addEventListener("input", () => { box.querySelector("#rate-v").textContent = f.rate.value; box.querySelector("#pitch-v").textContent = f.pitch.value; box.querySelector("#vol-v").textContent = f.volume.value; });
      box.querySelector("#v-test").addEventListener("click", () => A.hud && A.hud.speak(`Good day, Sir. ${cfg.name} online and at your service.`, read()));
      f.addEventListener("submit", async (e) => { e.preventDefault(); try { await save({ voice: read() }, "Voice saved"); } catch (err) { A.toast(err.message, "err"); } });
      return;
    }

    if (view === "memory") {
      const render = async () => {
        const rows = await A.api("GET", "/api/admin/e/memories");
        box.innerHTML = `<div class="toolbar"><input type="search" id="mq" placeholder="Search memories…" aria-label="Search memories"><span class="spacer"></span><button class="btn primary" id="m-add">${A.icon("plus")} Add memory</button></div>
          <p class="muted small">Stored in Turso and given to the assistant as durable context. The assistant can propose new memories; nothing is saved without your confirmation.</p>
          <div class="panel table-wrap"><table class="data"><thead><tr><th>Memory</th><th>Kind</th><th>Added</th><th></th></tr></thead><tbody id="mbody"></tbody></table></div>`;
        const paint = (q = "") => {
          const list = rows.filter((r) => !q || r.content.toLowerCase().includes(q));
          box.querySelector("#mbody").innerHTML = list.map((r) => `<tr data-id="${r.id}"><td style="white-space:normal">${esc(r.content)}</td><td><span class="badge plain">${esc(r.kind)}</span></td><td class="dim small">${A.rel(r.created_at)}</td>
            <td><div class="row"><button class="btn sm icon ghost" data-e aria-label="Edit">${A.icon("edit")}</button><button class="btn sm icon ghost" data-d aria-label="Delete">${A.icon("trash")}</button></div></td></tr>`).join("") || '<tr><td colspan="4" class="dim">No memories yet.</td></tr>';
          $$("tr[data-id]", box).forEach((tr) => {
            const r = rows.find((x) => String(x.id) === tr.dataset.id);
            tr.querySelector("[data-e]").addEventListener("click", async () => { if (await A.editEntity("memories", r, {}, "Edit memory")) render(); });
            tr.querySelector("[data-d]").addEventListener("click", async () => { if (await A.deleteEntity("memories", r, A.excerpt(r.content, 50))) render(); });
          });
        };
        paint();
        box.querySelector("#mq").addEventListener("input", (e) => paint(e.target.value.toLowerCase()));
        box.querySelector("#m-add").addEventListener("click", async () => { if (await A.editEntity("memories", null, { kind: "fact" }, "New memory")) render(); });
      };
      return render();
    }

    // history
    const cid = main.dataset.conversationId;
    const convs = await A.api("GET", "/api/admin/ai/conversations");
    box.innerHTML = `<div class="hist"><aside class="panel hist-list"><input type="search" id="hq" placeholder="Search conversations…" aria-label="Search conversations"><div id="hl"></div></aside><section class="panel pad hist-view" id="hv"></section></div>`;
    const paintList = (rows) => {
      box.querySelector("#hl").innerHTML = rows.map((c) => `<a class="conv ${String(c.id) === cid ? "on" : ""}" href="/admin/assistant/history/${c.id}"><div class="ct">${esc(c.title)}<small>${A.rel(c.updated_at)} · ${c.message_count} messages</small></div></a>`).join("") || '<p class="dim small" style="padding:.8rem">No conversations yet.</p>';
    };
    paintList(convs);
    box.querySelector("#hq").addEventListener("input", A.debounce(async (e) => paintList(await A.api("GET", "/api/admin/ai/conversations" + A.qs({ q: e.target.value }))), 250));
    const hv = box.querySelector("#hv");
    if (!cid) { hv.innerHTML = '<div class="empty"><h4>Pick a conversation</h4><p>Full transcripts of your chats with the assistant are stored in Turso.</p></div>'; return; }
    const data = await A.api("GET", `/api/admin/ai/conversations/${cid}/messages`);
    hv.innerHTML = `<div class="row wrap"><h3 style="margin:0">${esc(data.conversation.title)}</h3><span class="spacer"></span>
      <button class="btn sm" id="h-cont">Continue in HUD</button><button class="btn sm ghost" id="h-ren">Rename</button><button class="btn sm danger" id="h-del">Delete</button></div>
      <div class="transcript">${data.messages.map((m) => `<div class="tr-msg ${m.role}"><span class="label">${m.role === "user" ? "Sir" : esc(cfg.name)} · ${A.fmtDate(m.created_at)} ${A.fmtTime(m.created_at)}</span><div class="${m.role === "assistant" ? "md" : ""}">${m.role === "assistant" ? m.html : esc(m.content)}</div></div>`).join("") || '<p class="dim">Empty conversation.</p>'}</div>`;
    A.enhanceMarkdown(hv);
    hv.querySelector("#h-cont").addEventListener("click", () => A.hud && A.hud.openConversation(Number(cid)));
    hv.querySelector("#h-ren").addEventListener("click", async () => {
      const r = await A.formModal({ title: "Rename conversation", fields: [{ name: "title", label: "Title", required: true, full: true }], values: { title: data.conversation.title },
        onSubmit: (d) => A.api("PATCH", `/api/admin/ai/conversations/${cid}`, d) });
      if (r) A.reload();
    });
    hv.querySelector("#h-del").addEventListener("click", async () => {
      if (!(await A.confirm("Delete this conversation and its memory index permanently?", { danger: true, confirmLabel: "Delete" }))) return;
      await A.api("DELETE", `/api/admin/ai/conversations/${cid}`);
      if (A.hud) A.hud.forget(Number(cid));
      A.toast("Conversation deleted", "ok");
      A.go("/admin/assistant/history");
    });
  });
})();
