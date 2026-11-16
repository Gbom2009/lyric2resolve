/* Settings page: every change is saved immediately (PUT /api/settings with only the changed key). */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  let data = null;

  async function api(method, url, body) {
    const res = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined });
    let j = null;
    try { j = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) throw new Error((j && j.detail) || `${res.status}`);
    return j;
  }

  const saved = (msg = "Saved ✓", bad = false) => {
    const el = $("#saved");
    el.textContent = msg;
    el.className = bad ? "saved bad" : "saved";
    $("#status").textContent = msg;
  };

  function options(sel, values, labels) {
    sel.innerHTML = "";
    values.forEach((v) => {
      const o = document.createElement("option");
      o.value = String(v);
      o.textContent = labels ? labels[v] : String(v);
      sel.appendChild(o);
    });
  }

  function fill(d) {
    data = d;
    const s = d.settings;
    $("#data-dir").textContent = d.data_dir;
    $("#warnings").innerHTML = "";
    (d.warnings || []).forEach((w) => { const li = document.createElement("li"); li.textContent = w; $("#warnings").appendChild(li); });
    options($("#fps"), d.choices.fps);
    options($("#levels"), d.choices.styling_level);
    options($("#models"), d.choices.whisper_model);
    options($("#devices"), d.choices.device);
    options($("#perm"), Object.keys(d.choices.claude_permission_mode), d.choices.claude_permission_mode);
    $$("[data-key]").forEach((el) => {
      const v = s[el.dataset.key];
      if (el.type === "checkbox") el.checked = !!v;
      else if (el.tagName === "SELECT" && el.dataset.type === "number") {
        const match = Array.from(el.options).find((o) => Math.abs(Number(o.value) - Number(v)) < 1e-3);
        el.value = match ? match.value : String(v);
      } else el.value = v === null || v === undefined ? "" : String(v);
    });
    $$("[data-layout]").forEach((el) => { el.checked = (s.layouts || []).includes(el.dataset.layout); });
    $$("[data-upd]").forEach((el) => {
      const v = d.updater[el.dataset.upd];
      if (el.type === "checkbox") el.checked = !!v; else el.value = v;
    });
    const b = d.brand || {};
    $("#brand-source").textContent = b.error ? `problem: ${b.error}` : `${b.name} (${b.source || "config"})`;
    $("#brand-file").textContent = d.brand_file;
    if (b.logo) { $("#brand-logo").src = `/static/${b.logo}`; $("#brand-logo").hidden = false; }
    if (d.detected) tools(d.detected);
  }

  function tools(det) {
    $("#gpu").textContent = `GPU: ${det.gpu}`;
    const box = $("#tools");
    box.innerHTML = "";
    [["ffmpeg", "ffmpeg_path", "ffmpeg (audio conversion, video encoding)"],
     ["blender", "blender_path", "Blender (visuals + rendering)"],
     ["claude", "claude_cli_path", "Claude Code CLI (optional Assistant)"]].forEach(([k, key, label]) => {
      const t = det[k];
      const div = document.createElement("div");
      div.className = "tool";
      div.innerHTML = `<b>${label}</b>: <span class="${t.path ? "ok" : "bad"}"></span>
        <label class="field">Path (empty = find automatically) <input type="text" data-key="${key}"></label>
        <pre class="help"></pre>`;
      div.querySelector("span").textContent = t.path ? `found ${t.version || ""}` : "not found";
      div.querySelector("input").value = data.settings[key] || "";
      div.querySelector("input").placeholder = t.path || "";
      div.querySelector("pre").textContent = t.help || t.path;
      div.querySelector("input").addEventListener("change", onChange);
      box.appendChild(div);
    });
    $("#claude-status").textContent = det.claude.path ? `Claude Code ${det.claude.version} — log in once with \`claude\` in a terminal.`
      : "Claude Code not found (optional). See the Programs section.";
  }

  function valueOf(el) {
    if (el.type === "checkbox") return el.checked;
    if (el.dataset.type === "number") return Number(el.value);
    if (el.dataset.type === "int") return parseInt(el.value, 10);
    return el.value;
  }

  async function put(body) {
    try {
      const d = await api("PUT", "/api/settings", body);
      d.detected = data.detected;
      fill(d);
      saved(d.warnings && d.warnings.length ? "Saved with warnings (see top)" : "Saved ✓", !!(d.warnings && d.warnings.length));
      if ("funqtion_branding" in body) reloadTheme();
      if (Object.keys(body).some((k) => k.endsWith("_path"))) load(true);
    } catch (e) { saved(e.message, true); }
  }

  function onChange(ev) {
    const el = ev.target;
    if (el.dataset.key) put({ [el.dataset.key]: valueOf(el) });
  }

  function reloadTheme() {
    const link = document.querySelector('link[href^="/theme.css"]');
    if (link) link.href = `/theme.css?t=${Date.now()}`;
  }

  async function load(probe = true) {
    const d = await api("GET", `/api/settings?probe=${probe}`);
    fill(d);
  }

  function wire() {
    $$("[data-key]").forEach((el) => el.addEventListener("change", onChange));
    $$("[data-layout]").forEach((el) => el.addEventListener("change", () => {
      const layouts = $$("[data-layout]").filter((x) => x.checked).map((x) => x.dataset.layout);
      if (!layouts.length) { el.checked = true; saved("Keep at least one layout", true); return; }
      put({ layouts });
    }));
    $$("[data-upd]").forEach((el) => el.addEventListener("change", async () => {
      try {
        const r = await api("PUT", "/api/settings/updater", { [el.dataset.upd]: valueOf(el) });
        if (r.note) $("#upd-note").textContent = r.note;
        saved();
      } catch (e) { saved(e.message, true); }
    }));
    $("#brand-style").addEventListener("click", async () => {
      try {
        const b = await api("GET", "/api/brand");
        await api("POST", "/api/op/save_style", { name: b.name, style: b.video_text_style });
        $("#brand-msg").textContent = `Style "${b.name}" added to the open project (pick it in the editor's Text style card).`;
      } catch (e) { $("#brand-msg").textContent = e.message; }
    });
    $("#upd-check").addEventListener("click", () => window.L2RUpdate && window.L2RUpdate.check(true));
    document.addEventListener("l2r-update", (ev) => {
      const u = ev.detail;
      $("#upd-state").textContent = u.checking ? "Checking…" : (window.L2RUpdate.describe(u));
    });
  }

  wire();
  load().catch((e) => saved(e.message, true));
})();
