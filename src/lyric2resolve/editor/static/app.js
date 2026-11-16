/* lyric2resolve editor — core: state, waveform, word selection, playback, shortcuts.
   Plain JS (no build step). Other files (blocks.js, gaps.js, review.js) hook in via L2R.hooks. */
(() => {
  "use strict";
  const $ = (s, root = document) => root.querySelector(s);

  const L2R = (window.L2R = {
    state: null,            // last /api/state response
    sel: { anchor: null, focus: null },   // word indices (project word order)
    ws: null, regions: null,
    audioReady: false,
    hooks: { render: [], selection: [], keydown: [], ready: [] },
    wordEls: [],
  });

  // ------------------------------------------------------------------ helpers
  L2R.fmt = (t) => {
    if (!isFinite(t)) t = 0;
    t = Math.round(t * 100) / 100;  // round first, so 59.996 shows as 1:00.00 (not 0:60.00)
    const m = Math.floor(t / 60), s = t - m * 60;
    return `${m}:${s.toFixed(2).padStart(5, "0")}`;
  };
  // "1:23.45", "83.45" or "83,45" -> seconds (NaN when invalid)
  L2R.parseTime = (txt) => {
    const t = String(txt || "").trim().replace(",", ".");
    if (!t) return NaN;
    const parts = t.split(":").map(Number);
    if (parts.some((x) => !isFinite(x) || x < 0)) return NaN;
    return parts.reduce((acc, x) => acc * 60 + x, 0);
  };
  L2R.setStatus = (msg, isError = false) => {
    const el = $("#status");
    el.textContent = msg;
    el.classList.toggle("error", !!isError);
  };
  L2R.api = async (method, url, body) => {
    const res = await fetch(url, {
      method, headers: body !== undefined ? { "Content-Type": "application/json" } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* not json */ }
    if (!res.ok) {
      const err = new Error((data && data.detail) || `${res.status} ${res.statusText}`);
      err.status = res.status;
      throw err;
    }
    return data;
  };
  L2R.words = () => (L2R.state ? L2R.state.project.words : []);

  // apply an edit operation; returns true when it worked
  L2R.op = async (name, args = {}, label = name) => {
    try {
      const st = await L2R.api("POST", `/api/op/${name}`, args);
      L2R.setState(st);
      L2R.setStatus(`${label.replace(/_/g, " ")} ✓ — saved`);
      return true;
    } catch (e) {
      L2R.setStatus(e.message, true);
      return false;
    }
  };
  L2R.undo = async () => { L2R.setState(await L2R.api("POST", "/api/undo")); L2R.setStatus("Undone — saved"); };
  L2R.redo = async () => { L2R.setState(await L2R.api("POST", "/api/redo")); L2R.setStatus("Redone — saved"); };

  // ------------------------------------------------------------------ selection
  L2R.selectedRange = () => {
    const { anchor, focus } = L2R.sel;
    if (anchor === null || focus === null) return null;
    return [Math.min(anchor, focus), Math.max(anchor, focus)];
  };
  L2R.selectedWordIds = () => {
    const r = L2R.selectedRange();
    if (!r) return [];
    return L2R.words().slice(r[0], r[1] + 1).map((w) => w.id);
  };
  L2R.selectedSpan = () => {
    const r = L2R.selectedRange();
    if (!r) return null;
    const ws = L2R.words();
    return [ws[r[0]].start, ws[r[1]].end];
  };
  L2R.setSelection = (anchor, focus = anchor) => {
    const n = L2R.words().length;
    const clamp = (i) => (i === null ? null : Math.max(0, Math.min(n - 1, i)));
    L2R.sel = { anchor: clamp(anchor), focus: clamp(focus) };
    paintSelection();
    L2R.hooks.selection.forEach((fn) => fn(L2R.selectedRange()));
  };
  L2R.clearSelection = () => L2R.setSelection(null, null);

  function paintSelection() {
    const r = L2R.selectedRange();
    L2R.wordEls.forEach((el, i) => el && el.classList.toggle("selected", !!r && i >= r[0] && i <= r[1]));
    if (L2R.regions) {
      const old = L2R.regions.getRegions().find((x) => x.id === "selection");
      if (old) old.remove();
      const span = L2R.selectedSpan();
      if (span && L2R.audioReady) {
        L2R.regions.addRegion({ id: "selection", start: span[0], end: Math.max(span[1], span[0] + 0.01),
          color: "rgba(255, 216, 77, 0.35)", drag: false, resize: false });
      }
    }
    const span = L2R.selectedSpan();
    if (span) {
      const n = r[1] - r[0] + 1;
      $("#status").classList.remove("error");
      $("#status").textContent = `${n} word${n > 1 ? "s" : ""} selected · ${L2R.fmt(span[0])} – ${L2R.fmt(span[1])}`;
    }
  }

  // ------------------------------------------------------------------ rendering
  L2R.setState = (st) => {
    L2R.state = st;
    document.body.classList.toggle("no-project", !st);
    $("#project-name").textContent = st.project.name || "Untitled";
    $("#btn-undo").disabled = !st.history.can_undo;
    $("#btn-redo").disabled = !st.history.can_redo;
    $("#btn-undo").title = st.history.undo_label ? `Undo ${st.history.undo_label} (Ctrl+Z)` : "Undo (Ctrl+Z)";
    $("#btn-redo").title = st.history.redo_label ? `Redo ${st.history.redo_label} (Ctrl+Y)` : "Redo (Ctrl+Y)";
    // keep the selection valid after edits
    const n = st.project.words.length;
    if (L2R.sel.anchor !== null && L2R.sel.anchor >= n) L2R.sel = { anchor: null, focus: null };
    render();
  };

  function render() {
    const st = L2R.state;
    const host = $("#lyrics");
    const scroll = host.scrollTop;
    host.innerHTML = "";
    const words = st.project.words;
    const blockOf = new Map();
    st.blocks.forEach((b, bi) => b.word_ids.forEach((id) => blockOf.set(id, bi)));
    const flagged = new Map();
    (st.flags || []).forEach((f) => flagged.set(f.word_id, (flagged.get(f.word_id) || []).concat(f.message)));
    const gaps = [...st.project.gaps].sort((a, b) => a.start - b.start);
    let gi = 0;
    L2R.wordEls = new Array(words.length);

    const addGapsBefore = (t) => {
      while (gi < gaps.length && gaps[gi].start <= t) {
        const g = gaps[gi++];
        const row = document.createElement("div");
        row.className = "gap-row";
        row.dataset.gapId = g.id;
        row.textContent = `♪ instrumental gap ${L2R.fmt(g.start)} – ${L2R.fmt(g.end)} (${(g.end - g.start).toFixed(1)} s, ${g.source}) — nothing is placed here`;
        host.appendChild(row);
      }
    };

    let i = 0;
    while (i < words.length) {
      const keyOf = (k) => (blockOf.has(words[k].id) ? blockOf.get(words[k].id) : null);
      const bi = keyOf(i);
      let j = i;
      while (j + 1 < words.length && keyOf(j + 1) === bi) j++;   // same block, or a run of hidden words
      addGapsBefore(words[i].start);
      const row = document.createElement("div");
      const block = bi !== null ? st.blocks[bi] : null;
      row.className = "block" + (block ? "" : " hidden-words");
      if (block) row.dataset.blockId = block.id;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.innerHTML = block
        ? `#${bi + 1}<br>${L2R.fmt(block.start)}<br>${L2R.fmt(block.end)}`
        : "not shown";
      row.appendChild(meta);
      const wrap = document.createElement("div");
      wrap.className = "words";
      for (let k = i; k <= j; k++) {
        const w = words[k];
        const el = document.createElement("span");
        el.className = "word";
        el.dataset.i = k;
        el.dataset.wordId = w.id;
        el.textContent = w.text;
        el.title = `${L2R.fmt(w.start)} – ${L2R.fmt(w.end)} · confidence ${Math.round(w.confidence * 100)}%`;
        if (w.confidence < 0.45) el.classList.add("lowconf");
        if (flagged.has(w.id)) { el.classList.add("flagged"); el.title += "\n⚠ " + flagged.get(w.id).join("\n⚠ "); }
        wrap.appendChild(el);
        L2R.wordEls[k] = el;
      }
      row.appendChild(wrap);
      if (block && block.overridden) {
        const o = document.createElement("div");
        o.className = "override";
        o.textContent = `shown as: “${block.text}”`;
        row.appendChild(o);
      }
      host.appendChild(row);
      i = j + 1;
    }
    addGapsBefore(Infinity);
    host.scrollTop = scroll;
    paintSelection();
    L2R.hooks.render.forEach((fn) => fn(st));
  }
  L2R.render = render;

  // ------------------------------------------------------------------ mouse selection
  let dragging = false;
  $("#lyrics").addEventListener("mousedown", (ev) => {
    const el = ev.target.closest(".word");
    if (!el) { if (!ev.shiftKey && ev.target === $("#lyrics")) L2R.clearSelection(); return; }
    ev.preventDefault();
    $("#lyrics").focus({ preventScroll: true });
    const i = Number(el.dataset.i);
    if (ev.shiftKey && L2R.sel.anchor !== null) L2R.setSelection(L2R.sel.anchor, i);
    else L2R.setSelection(i, i);
    dragging = true;
    if (L2R.ws && L2R.audioReady && !L2R.ws.isPlaying()) L2R.ws.setTime(L2R.words()[i].start);
  });
  $("#lyrics").addEventListener("mouseover", (ev) => {
    if (!dragging) return;
    const el = ev.target.closest(".word");
    if (el) L2R.setSelection(L2R.sel.anchor, Number(el.dataset.i));
  });
  document.addEventListener("mouseup", () => { dragging = false; });

  // ------------------------------------------------------------------ waveform + playback
  function initWave() {
    if (!window.WaveSurfer) { $("#audio-note").textContent = "waveform library missing"; return; }
    L2R.regions = WaveSurfer.Regions.create();
    L2R.ws = WaveSurfer.create({
      container: "#waveform", height: 96, waveColor: getCss("--wave"), progressColor: getCss("--wave-progress"),
      cursorColor: getCss("--text"), minPxPerSec: Number($("#zoom").value), autoScroll: true, autoCenter: true,
      plugins: [L2R.regions, WaveSurfer.Timeline.create({
        container: "#wave-timeline", height: 18, timeInterval: 1, primaryLabelInterval: 5, secondaryLabelInterval: 0,
        formatTimeCallback: (sec) => { const m = Math.floor(sec / 60), s = Math.round(sec % 60); return `${m}:${String(s).padStart(2, "0")}`; },
      })],
    });
    L2R.ws.on("ready", (d) => {
      L2R.audioReady = true;
      $("#time-total").textContent = L2R.fmt(d);
      $("#audio-note").textContent = "";
      paintSelection();
      L2R.hooks.ready.forEach((fn) => fn());
    });
    L2R.ws.on("error", () => {
      L2R.audioReady = false;
      $("#audio-note").textContent = "· no audio for this project (editing still works)";
    });
    L2R.ws.on("timeupdate", onTime);
    L2R.ws.on("play", () => { $("#btn-play").textContent = "Pause"; });
    L2R.ws.on("pause", () => { $("#btn-play").textContent = "Play"; });
  }
  function getCss(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  L2R.loadAudio = () => {
    if (!L2R.ws) return;
    L2R.audioReady = false;
    L2R.ws.load(`/api/audio/${$("#audio-source").value}?t=${Date.now()}`).catch(() => {});
  };

  let playingIdx = -1;
  function onTime(t) {
    $("#time-cur").textContent = L2R.fmt(t);
    const ws = L2R.words();
    let lo = 0, hi = ws.length - 1, found = -1;
    while (lo <= hi) {               // last word with start <= t
      const mid = (lo + hi) >> 1;
      if (ws[mid].start <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    if (found >= 0 && t > ws[found].end + 0.15) found = -1;
    if (found !== playingIdx) {
      if (playingIdx >= 0 && L2R.wordEls[playingIdx]) L2R.wordEls[playingIdx].classList.remove("playing");
      playingIdx = found;
      const el = found >= 0 ? L2R.wordEls[found] : null;
      if (el) {
        el.classList.add("playing");
        if (L2R.ws.isPlaying()) el.scrollIntoView({ block: "nearest" });
      }
    }
  }
  L2R.togglePlay = () => { if (L2R.ws && L2R.audioReady) L2R.ws.playPause(); };
  L2R.playSelection = () => {
    const span = L2R.selectedSpan();
    if (!span || !L2R.ws || !L2R.audioReady) return;
    L2R.ws.play(Math.max(0, span[0] - 0.05), span[1] + 0.05);
  };

  // ------------------------------------------------------------------ keyboard
  const isTyping = (ev) => ev.target.closest("input, textarea, select, [contenteditable=true]");
  document.addEventListener("keydown", (ev) => {
    if (isTyping(ev) || document.querySelector("dialog[open]")) return;
    const ctrl = ev.ctrlKey || ev.metaKey;
    const r = L2R.selectedRange();
    const n = L2R.words().length;
    for (const fn of L2R.hooks.keydown) { if (fn(ev) === true) { ev.preventDefault(); return; } }
    if (ctrl && ev.key.toLowerCase() === "z" && !ev.shiftKey) { ev.preventDefault(); L2R.undo(); }
    else if (ctrl && (ev.key.toLowerCase() === "y" || (ev.key.toLowerCase() === "z" && ev.shiftKey))) { ev.preventDefault(); L2R.redo(); }
    else if (ev.code === "Space" && ev.shiftKey) { ev.preventDefault(); L2R.playSelection(); }
    else if (ev.code === "Space") { ev.preventDefault(); L2R.togglePlay(); }
    else if (ev.key === "Escape") { L2R.clearSelection(); }
    else if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
      if (!n) return;
      ev.preventDefault();
      const d = ev.key === "ArrowRight" ? 1 : -1;
      if (!r) L2R.setSelection(d > 0 ? 0 : n - 1);
      else if (ev.shiftKey) L2R.setSelection(L2R.sel.anchor, L2R.sel.focus + d);
      else { const i = d > 0 ? r[1] + 1 : r[0] - 1; L2R.setSelection(i, i); }
      const el = L2R.wordEls[L2R.sel.focus];
      if (el) el.scrollIntoView({ block: "nearest" });
      if (L2R.ws && L2R.audioReady && !L2R.ws.isPlaying()) L2R.ws.setTime(L2R.words()[L2R.sel.focus].start);
    }
    else if (ev.key === "+" || ev.key === "=") { const z = $("#zoom"); z.value = Math.min(400, +z.value + 20); z.dispatchEvent(new Event("input")); }
    else if (ev.key === "-") { const z = $("#zoom"); z.value = Math.max(10, +z.value - 20); z.dispatchEvent(new Event("input")); }
  });

  // ------------------------------------------------------------------ buttons + projects
  // Without an open project, buttons explain what to do instead of silently doing nothing.
  L2R.requireProject = () => {
    if (L2R.state) return true;
    L2R.setStatus("No project open — open one or make a new one first", true);
    showProjects();
    return false;
  };
  $("#btn-undo").onclick = () => L2R.requireProject() && L2R.undo();
  $("#btn-redo").onclick = () => L2R.requireProject() && L2R.redo();
  $("#btn-play").onclick = () => {
    if (!L2R.requireProject()) return;
    if (!L2R.audioReady) { L2R.setStatus("No audio loaded for this project (editing still works)", true); return; }
    L2R.togglePlay();
  };
  $("#btn-play-sel").onclick = () => {
    if (!L2R.requireProject()) return;
    if (!L2R.selectedSpan()) { L2R.setStatus("Select some words first (click or drag over them)"); return; }
    L2R.playSelection();
  };
  $("#audio-source").onchange = () => L2R.loadAudio();
  $("#zoom").addEventListener("input", () => { if (L2R.ws && L2R.audioReady) L2R.ws.zoom(Number($("#zoom").value)); });
  $("#btn-projects").onclick = () => showProjects();

  async function showProjects() {
    let data;
    try { data = await L2R.api("GET", "/api/projects"); }
    catch (e) { L2R.setStatus(e.message, true); return; }
    const list = $("#project-list");
    list.innerHTML = "";
    $("#project-dir").textContent = data.projects_dir ? `Projects folder: ${data.projects_dir}` : "";
    if (!data.projects.length) list.innerHTML = "<li class='hint'>No projects yet — click <b>+ New project…</b> to make your first one.</li>";
    data.projects.forEach((p) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.textContent = `${p.name} — ${p.words} words, ${p.blocks} blocks · ${p.modified}`;
      b.onclick = async () => {
        try {
          L2R.setState(await L2R.api("POST", "/api/open", { path: p.path }));
          $("#project-dialog").close();
          L2R.clearSelection();
          L2R.loadAudio();
          L2R.setStatus("Ready — every edit is saved automatically");
        } catch (e) { L2R.setStatus(e.message, true); }
      };
      li.appendChild(b);
      list.appendChild(li);
    });
    if (!$("#project-dialog").open) $("#project-dialog").showModal();
  }
  L2R.showProjects = showProjects;

  async function boot() {
    initWave();
    try {
      L2R.setState(await L2R.api("GET", "/api/state"));
      L2R.setStatus("Ready — every edit is saved automatically");
      L2R.loadAudio();
    } catch (e) {
      if (e.status === 409) {
        document.body.classList.add("no-project");
        L2R.setStatus("No project open — open one or make a new one");
        showProjects();
      }
      else L2R.setStatus(e.message, true);
    }
  }
  L2R.boot = boot;
  document.addEventListener("DOMContentLoaded", boot);
})();
