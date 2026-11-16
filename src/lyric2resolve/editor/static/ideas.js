/* Visual ideas page: brief per section, Claude Code prompts (copy), project templates. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  let data = null, which = "blender";
  async function api(method, url, body) {
    const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => null);
    if (!r.ok) throw new Error((d && d.detail) || r.statusText);
    return d;
  }
  function render() {
    const b = data.brief;
    $("#title").textContent = b.title;
    const meta = $("#meta");
    meta.replaceChildren(el("span", "", `${b.duration} s`), el("span", "", `BPM ${b.bpm || "?"} (${b.tempo_feel})`),
      el("span", "", `Key ${b.key}`), el("span", "", `Mood: ${b.mood}`), el("span", "", `Themes: ${b.themes.join(", ") || "–"}`));
    const pal = el("span", "", "Palette ");
    b.palette.forEach((c) => { const s = el("span", "swatch"); s.style.background = c; s.title = c; pal.append(s, " "); });
    meta.append(pal);
    $("#sections").replaceChildren(...b.sections.map((s) => {
      const box = el("section", "sec");
      box.append(el("h3", "", `${s.label} · ${s.start.toFixed(1)}–${s.end.toFixed(1)} s · energy ${s.level}`));
      const grid = el("div", "concepts");
      s.concepts.forEach((c) => {
        const card = el("div", "concept");
        card.append(el("b", "", c.name), el("div", "", c.idea));
        const code = el("code", "", `lyric2resolve render project.json --template ${c.template} --render-preset preview`);
        card.append(code);
        grid.append(card);
      });
      box.append(grid, el("p", "hint", "Text animation: " + s.text_animation.join(" / ")));
      return box;
    }));
    showPrompt();
  }
  function showPrompt() {
    $("#prompt").value = which === "blender" ? data.blender_prompt : data.threejs_prompt;
    $("#t-blender").classList.toggle("on", which === "blender");
    $("#t-three").classList.toggle("on", which === "three");
  }
  async function loadTemplates() {
    const t = await api("GET", "/api/templates");
    $("#tpl-list").replaceChildren(...t.templates.map((n) => { const o = el("option", "", n); o.value = n; return o; }));
  }
  $("#t-blender").onclick = () => { which = "blender"; showPrompt(); };
  $("#t-three").onclick = () => { which = "three"; showPrompt(); };
  $("#copy").onclick = async () => {
    try { await navigator.clipboard.writeText($("#prompt").value); $("#copied").textContent = "Copied ✓"; }
    catch (e) { $("#prompt").select(); document.execCommand("copy"); $("#copied").textContent = "Copied ✓"; }
  };
  $("#tpl-save").onclick = async () => {
    try { await api("POST", "/api/templates/save", { name: $("#tpl-name").value }); $("#tpl-msg").textContent = "Saved ✓"; await loadTemplates(); }
    catch (e) { $("#tpl-msg").textContent = e.message; }
  };
  $("#tpl-apply").onclick = async () => {
    const name = $("#tpl-list").value;
    if (!name) return;
    try { await api("POST", "/api/op/apply_template", { name }); $("#tpl-msg").textContent = `Applied “${name}” ✓ (Undo in the editor if needed)`; }
    catch (e) { $("#tpl-msg").textContent = e.message; }
  };
  window.IDEAS = { ready: (async () => {
    try { data = await api("GET", "/api/ideas"); render(); }
    catch (e) { $("#title").textContent = e.message.includes("no project") ? "Open a project in the editor first." : e.message; }
    await loadTemplates();
  })() };
})();
