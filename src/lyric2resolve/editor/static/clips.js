/* Clips track: videos on the timeline (your own files or rendered/Claude-made scenes), shown as regions on the
   waveform and in the Clips card. A clip can replace the lyrics while it plays ("hide lyrics"). */
(() => {
  "use strict";
  const L = window.L2R;
  const h = (...a) => L.h(...a);
  const byId = (id) => document.getElementById(id);
  let syncing = false, renderWasRunning = false, pollTimer = null;

  const clips = () => (L.state ? L.state.project.clips || [] : []);
  const playhead = () => (L.ws && L.audioReady ? L.ws.getCurrentTime() : 0);
  const range = () => { const s = L.selectedSpan(); return s ? [s[0], s[1]] : [playhead(), playhead() + 4]; };
  const bars = () => (L.state && L.state.project.analysis && (L.state.project.analysis.downbeats || L.state.project.analysis.beats)) || [];
  const snap = (t) => { const b = bars(); return b.length ? b.reduce((best, x) => Math.abs(x - t) < Math.abs(best - t) ? x : best, b[0]) : t; };

  function syncRegions() {
    if (!L.regions || !L.audioReady || !L.state) return;
    syncing = true;
    L.regions.getRegions().filter((r) => String(r.id).startsWith("clip-")).forEach((r) => r.remove());
    clips().forEach((c) => L.regions.addRegion({
      id: `clip-${c.id}`, start: c.start, end: c.end, drag: true, resize: true,
      color: c.hide_lyrics ? "rgba(140, 60, 220, 0.30)" : "rgba(140, 60, 220, 0.16)",
      content: `🎬 ${c.name}${c.hide_lyrics ? " (no lyrics)" : ""}`,
    }));
    syncing = false;
  }

  function wire() {
    if (!L.regions || L.regions._l2rClipWired) return;
    L.regions._l2rClipWired = true;
    L.regions.on("region-updated", (r) => {
      if (syncing || !String(r.id).startsWith("clip-")) return;
      L.op("update_clip", { clip_id: String(r.id).slice(5), start: +r.start.toFixed(3), end: +r.end.toFixed(3) }, "move clip");
    });
  }

  async function upload(file) {
    const [s, e] = range();
    const fd = new FormData();
    fd.append("file", file);
    fd.append("start", String(s));
    fd.append("end", String(L.selectedSpan() ? e : 0));
    fd.append("hide_lyrics", byId("clip-hide-default") && byId("clip-hide-default").checked ? "true" : "false");
    fd.append("snap", byId("clip-snap-default") && byId("clip-snap-default").checked ? "true" : "false");
    L.setStatus("Adding clip…");
    try {
      const r = await fetch("/api/clips/upload", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.statusText);
      L.setState(j);
      L.setStatus(`Clip added at ${L.fmt(s)} — saved (Ctrl+Z undoes it)`);
    } catch (e) { L.setStatus("Clip: " + e.message, true); }
  }

  function renderCard() {
    const body = L.card("card-clips", "Clips (videos on the timeline)");
    body.innerHTML = "";
    body.append(h("p", { class: "hint" }, "Rendered scenes and your own videos/images, placed on the song. They go to Resolve on the track under the lyrics. Drag or resize them on the waveform."));
    const fileIn = h("input", { type: "file", id: "clip-file", accept: "video/*,image/*", hidden: true,
      onchange: (ev) => { const f = ev.target.files[0]; if (f) upload(f); ev.target.value = ""; } });
    body.append(
      h("div", { class: "row" },
        h("button", { onclick: () => fileIn.click(), title: "At the playhead (or over the selected words)" }, "+ Add video/image"),
        h("button", { class: "primary", id: "btn-claude-clip", onclick: () => openClaudeDialog() }, "✨ Make a clip with Claude"),
        fileIn),
      h("div", { class: "row" },
        h("label", { class: "check" }, h("input", { type: "checkbox", id: "clip-snap-default", checked: true }), " snap to bars"),
        h("label", { class: "check" }, h("input", { type: "checkbox", id: "clip-hide-default" }), " clip replaces the lyrics")));
    const list = h("div", { class: "clip-list" });
    clips().forEach((c) => {
      const save = (args) => L.op("update_clip", { clip_id: c.id, ...args }, "edit clip");
      const t = (v) => { const x = L.parseTime(v); return isFinite(x) ? x : null; };
      list.append(h("div", { class: "clip-item" },
        h("video", { src: `/api/clips/file/${c.id}`, muted: true, preload: "metadata", controls: true }),
        h("div", { class: "clip-meta" },
          h("b", {}, `${c.source === "render" ? "🎬" : "📁"} ${c.name}`),
          h("div", { class: "row" },
            h("input", { value: L.fmt(c.start), title: "start", onchange: (ev) => t(ev.target.value) != null && save({ start: t(ev.target.value) }) }),
            "–",
            h("input", { value: L.fmt(c.end), title: "end", onchange: (ev) => t(ev.target.value) != null && save({ end: t(ev.target.value) }) })),
          h("label", { class: "check" }, h("input", { type: "checkbox", checked: c.hide_lyrics,
            onchange: (ev) => save({ hide_lyrics: ev.target.checked }) }), " replaces the lyrics here"),
          h("div", { class: "row" },
            h("button", { class: "small", onclick: () => { if (L.ws && L.audioReady) L.ws.setTime(c.start); } }, "Go to"),
            h("button", { class: "small", onclick: () => save({ start: snap(c.start), end: snap(c.end) }) }, "Snap to bars"),
            h("button", { class: "small", onclick: () => confirm(`Remove clip ${c.name}?`) && L.op("remove_clip", { clip_id: c.id }, "remove clip") }, "Remove")))));
    });
    if (!clips().length) list.append(h("p", { class: "hint" }, "No clips yet."));
    body.append(list, h("p", { class: "hint", id: "clip-render-status" }));
  }

  // ------------------------------------------------------------------ "Make a clip with Claude"
  function openClaudeDialog() {
    if (!L.requireProject()) return;
    let [s, e] = range();
    if (byId("clip-snap-default").checked) { s = snap(s); e = snap(e); if (e <= s) e = s + 2; }
    byId("cc-start").value = L.fmt(s);
    byId("cc-end").value = L.fmt(e);
    byId("cc-msg").textContent = bars().length ? "" : "(No bar grid yet - run the music analysis for snapping.)";
    byId("cc-dialog").showModal();
    byId("cc-desc").focus();
  }

  async function sendClaudeClip() {
    const name = (byId("cc-name").value || "clip").trim();
    const desc = byId("cc-desc").value.trim();
    const s = L.parseTime(byId("cc-start").value), e = L.parseTime(byId("cc-end").value);
    if (!desc) { byId("cc-msg").textContent = "Describe what you want to see."; return; }
    if (!isFinite(s) || !isFinite(e) || e <= s) { byId("cc-msg").textContent = "Check the start/end times."; return; }
    // reference files: upload into context/ (the Assistant card's attachment folder)
    const files = Array.from(byId("cc-files").files || []);
    let names = [];
    if (files.length) {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const r = await fetch("/api/assistant/attachments", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) { byId("cc-msg").textContent = j.detail || "upload failed"; return; }
      names = j.saved.map((x) => x.name);
    }
    const hide = byId("cc-hide").checked, preset = byId("cc-preset").value, snapIt = byId("cc-snap").checked;
    const msg = [
      `Make a custom Blender clip called "${name}" for ${L.fmt(s)}–${L.fmt(e)} (${(e - s).toFixed(2)} s; seconds ${s.toFixed(3)}-${e.toFixed(3)}).`,
      `What I want: ${desc}`,
      "Steps: 1) call custom_scene_guide and read it; 2) check list_clips for the bars/BPM if timing matters;",
      `3) write scenes/${name.replace(/[^\w-]+/g, "_")}/scene.py; 4) call render_clip with name "${name}", start ${s.toFixed(3)}, end ${e.toFixed(3)}, preset "${preset}", snap ${snapIt}, hide_lyrics ${hide}.`,
      "Then tell me briefly what you made. If the render fails, read the error, fix the script and render again.",
    ].join("\n");
    try {
      await L.api("POST", "/api/assistant/send", { message: msg, attachments: names });
      byId("cc-dialog").close();
      L.setStatus("Sent to Claude — follow it in the Assistant card; the clip appears on the timeline when it is rendered.");
      const card = byId("card-assistant");
      if (card) card.scrollIntoView({ block: "start" });
      if (L.assistantPoll) L.assistantPoll();
      watchRender();
    } catch (err) { byId("cc-msg").textContent = err.message; }
  }

  // refresh the project when a background render (e.g. Claude's clip) finishes
  async function watchRender() {
    clearTimeout(pollTimer);
    try {
      const p = await L.api("GET", "/api/render/progress");
      const st = byId("clip-render-status");
      if (st) st.textContent = p.running ? `Rendering ${p.name || p.template || ""}… ${p.total ? Math.round(p.fraction * 100) + "%" : ""}` : (p.error ? "Render failed: " + p.error : "");
      if (renderWasRunning && !p.running) L.setState(await L.api("GET", "/api/state"));
      renderWasRunning = !!p.running;
    } catch (e) { /* no project */ }
    pollTimer = setTimeout(watchRender, renderWasRunning ? 1500 : 5000);
  }

  function wireDialog() {
    byId("cc-go").onclick = sendClaudeClip;
    byId("cc-close").onclick = () => byId("cc-dialog").close();
    byId("cc-dialog").addEventListener("keydown", (ev) => ev.stopPropagation());
  }

  L.hooks.render.push(() => { renderCard(); wire(); syncRegions(); });
  L.hooks.ready.push(() => { wire(); syncRegions(); });
  wireDialog();
  watchRender();
})();
