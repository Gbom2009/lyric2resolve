/* Asset library browser: CC0 textures/HDRIs (library + custom) and fonts with live previews. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  let textures = [], fonts = [];
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

  function renderTextures() {
    const q = $("#tex-search").value.toLowerCase(), cat = $("#tex-cat").value;
    const list = textures.filter((t) => (!cat || t.category === cat) && `${t.name} ${t.category} ${t.source}`.toLowerCase().includes(q));
    $("#tex-grid").replaceChildren(...list.map((t) => {
      const tile = el("div", "tile");
      tile.dataset.id = t.id;
      const img = el("div", "img", t.kind === "hdri" ? "HDRI" : "");
      const color = t.maps && t.maps.color;
      if (color && /\.(jpe?g|png)$/i.test(color)) img.style.backgroundImage = `url("/api/textures/file/${color.split("/").map(encodeURIComponent).join("/")}")`;
      const meta = el("div", "meta");
      meta.append(el("b", "", t.name), el("span", "", `${t.category} · ${t.source} · ${t.resolution || ""} · ${t.license}`), el("div", "maps", Object.keys(t.maps || {}).join(", ")));
      tile.append(img, meta);
      return tile;
    }));
    $("#tex-empty").hidden = textures.length > 0;
  }
  function renderFonts() {
    const q = $("#font-search").value.toLowerCase(), sample = $("#font-sample").value;
    $("#font-list").replaceChildren(...fonts.filter((f) => f.family.toLowerCase().includes(q)).map((f) => {
      const row = el("div", "font-row");
      const s = el("div", "sample", sample);
      s.style.fontFamily = `"${f.family}", sans-serif`;
      row.append(s, el("div", "info", `${f.family} · ${f.source} · ${f.license}`));
      return row;
    }));
  }
  async function boot() {
    const t = await (await fetch("/api/textures")).json();
    textures = t.textures;
    $("#tex-folder").textContent = t.folder;
    [...new Set(textures.map((x) => x.category))].sort().forEach((c) => { const o = el("option", "", c); o.value = c; $("#tex-cat").append(o); });
    renderTextures();
    fonts = (await (await fetch("/api/fonts")).json()).fonts;
    for (const f of fonts) for (const file of f.files) {
      try { const face = new FontFace(f.family, `url(/api/fonts/file/${file})`); document.fonts.add(face); face.load().catch(() => {}); } catch (e) { /* skip */ }
    }
    renderFonts();
  }
  const tab = (on) => { $("#pane-tex").hidden = on !== "tex"; $("#pane-fonts").hidden = on !== "fonts"; $("#tab-tex").classList.toggle("on", on === "tex"); $("#tab-fonts").classList.toggle("on", on === "fonts"); };
  $("#tab-tex").onclick = () => tab("tex");
  $("#tab-fonts").onclick = () => tab("fonts");
  $("#tex-search").oninput = renderTextures;
  $("#tex-cat").onchange = renderTextures;
  $("#font-search").oninput = renderFonts;
  $("#font-sample").oninput = renderFonts;
  window.LIB = { ready: boot() };
})();
