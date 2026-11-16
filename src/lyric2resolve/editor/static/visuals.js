/* Visuals page: choose a scene + options, estimate, render in the background, watch progress, play results. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  let opts = null, template = null, timer = null, lastRunning = false;

  async function api(method, url, body) {
    const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => null);
    if (!r.ok) throw new Error((d && d.detail) || r.statusText);
    return d;
  }
  const status = (msg, bad = false) => { $("#status").textContent = msg; $("#status").classList.toggle("error", bad); };
  const fmtEta = (s) => (s == null || !isFinite(s)) ? "" : (s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor(s % 3600 / 60)} min` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);
  const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

  function renderOptions() {
    const tools = $("#tools");
    tools.innerHTML = "";
    if (!opts.tools.blender) tools.append(el("div", "warn-box", opts.tools.blender_help));
    if (!opts.tools.ffmpeg) tools.append(el("div", "warn-box", "ffmpeg was not found (needed to make the MP4).\n" + opts.tools.ffmpeg_help));
    const want = new URLSearchParams(location.search).get("template");
    template = template || (opts.templates.find((t) => t.id === want) || opts.templates[0]).id;
    $("#templates").replaceChildren(...opts.templates.map((t) => {
      const b = el("button", "tpl" + (t.id === template ? " on" : ""));
      b.type = "button";
      b.dataset.template = t.id;
      b.append(el("b", "", t.name), el("span", "", t.description));
      b.onclick = () => { template = t.id; $$(".tpl").forEach((x) => x.classList.toggle("on", x === b)); };
      return b;
    }));
    const pre = $("#preset");
    pre.replaceChildren(...opts.presets.map((p) => { const o = el("option", "", `${p.name[0].toUpperCase()}${p.name.slice(1)} — ${p.height}p ${p.engine}`); o.value = p.name; return o; }));
    const desc = () => { const p = opts.presets.find((x) => x.name === pre.value); $("#preset-desc").textContent = p ? p.description : ""; };
    pre.onchange = desc;
    desc();
    $$("input[name=aspect]").forEach((c) => { c.checked = c.value === "16:9"; });
    const secs = $("#sections");
    secs.replaceChildren(secs.firstElementChild);
    const labels = [...new Set(opts.sections.map((s) => s.label))];
    labels.forEach((lab) => {
      const parts = opts.sections.filter((s) => s.label === lab);
      const l = el("label");
      const r = el("input"); r.type = "radio"; r.name = "part"; r.value = lab;
      l.append(r, ` ${lab} only (${parts.map((s) => `${mmss(s.start)}–${mmss(s.end)}`).join(", ")})`);
      secs.append(l);
    });
    if (!labels.length) secs.append(el("span", "hint", "(sections appear after the music analysis)"));
  }

  function body(estimateOnly) {
    const aspects = $$("input[name=aspect]:checked").map((c) => c.value);
    const part = ($("input[name=part]:checked") || {}).value;
    return { template, preset: $("#preset").value, aspects: aspects.length ? aspects : ["16:9"],
             sections: part ? [part] : null, estimate_only: estimateOnly,
             lyrics_3d: !!(document.getElementById("lyrics3d") || {}).checked };
  }

  function showProgress(p) {
    const running = !!p.running;
    $("#render").disabled = running;
    $("#estimate").disabled = running;
    $("#stop").disabled = !running;
    $("#bar").style.width = `${Math.round((p.fraction || 0) * 100)}%`;
    let txt = "";
    if (running) txt = p.total ? `${p.aspect || ""} · ${p.done}/${p.total} frames (${Math.round(p.fraction * 100)}%)` + (p.eta_s ? ` · about ${fmtEta(p.eta_s)} left` : "") : "Building the Blender scene…";
    else if (p.error) txt = "Failed: " + p.error;
    else if (p.report) {
      const r = p.report;
      const est = Object.entries(r.estimates || {}).map(([a, s]) => `${a}: ${s}`).join("\n");
      txt = r.cancelled ? "Stopped. Click Render again (same options) to continue." :
        (p.estimate_only ? "Estimate:\n" + est : (r.ok ? `Done · ${r.videos.length} video(s)` : "Render failed")) ;
      if (!p.estimate_only && est) txt += "\n" + est;
    }
    $("#progress-text").textContent = txt;
    $("#progress-text").style.whiteSpace = "pre-wrap";
    const log = (p.log || []).concat(p.report && p.report.messages ? p.report.messages : []);
    $("#log").hidden = !log.length;
    $("#log").textContent = log.join("\n");
    if (lastRunning && !running) loadVideos();
    lastRunning = running;
  }

  async function poll() {
    clearTimeout(timer);
    try {
      const p = await api("GET", "/api/render/progress");
      showProgress(p);
      if (p.running) timer = setTimeout(poll, 1000);
    } catch (e) { status(e.message, true); }
  }

  async function start(estimateOnly) {
    try {
      await api("POST", "/api/render", body(estimateOnly));
      status(estimateOnly ? "Estimating…" : "Rendering in the background — you can keep editing in the editor.");
      lastRunning = true;
      poll();
    } catch (e) { status(e.message, true); }
  }

  async function loadVideos() {
    const d = await api("GET", "/api/visuals/videos");
    const box = $("#videos");
    if (!d.videos.length) { box.replaceChildren(el("p", "hint", "Nothing rendered yet.")); return; }
    box.replaceChildren(...d.videos.map((v) => {
      const card = el("div", "video");
      const vid = el("video"); vid.controls = true; vid.preload = "metadata"; vid.src = `/api/visuals/file/${encodeURI(v.path)}`;
      const open = el("button", "", "Open folder");
      open.onclick = () => api("POST", "/api/visuals/open-folder", { folder: v.folder }).catch((e) => status(e.message, true));
      card.append(vid, el("div", "", v.name), el("div", "hint", `${v.size_mb} MB · ${v.modified} · ${v.folder}`), open);
      return card;
    }));
  }

  $("#estimate").onclick = () => start(true);
  $("#render").onclick = () => start(false);
  $("#stop").onclick = () => api("POST", "/api/render/cancel").then(() => status("Stopping…")).catch((e) => status(e.message, true));
  $("#open-folder").onclick = () => api("POST", "/api/visuals/open-folder", {}).catch((e) => status(e.message, true));

  (async () => {
    try {
      opts = await api("GET", "/api/visuals/options");
      renderOptions();
      await loadVideos();
      poll();
    } catch (e) {
      $("#title").textContent = e.message.includes("no project") ? "Open a project in the editor first." : e.message;
    }
  })();
})();
