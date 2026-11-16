/* Text styles: styling level, preset editor with live 16:9 + 9:16 preview, per-section and per-block styles,
   font picker (library + custom + Windows fonts). */
(() => {
  "use strict";
  const L = window.L2R;
  const h = (...a) => L.h(...a);
  const $ = (s, r = document) => r.querySelector(s);
  let fonts = [];
  let editing = null;     // preset name shown in the editor
  let draft = null;       // unsaved edits of that preset

  const WEIGHTS = { thin: 100, extralight: 200, light: 300, regular: 400, medium: 500, semibold: 600, bold: 700,
    extrabold: 800, black: 900 };
  const weightOf = (fontStyle) => {
    const k = String(fontStyle || "").toLowerCase().replace(/italic|\s|-/g, "");
    return WEIGHTS[k] || 400;
  };
  const italicOf = (fontStyle) => /italic/i.test(fontStyle || "");

  async function loadFonts() {
    try { fonts = (await L.api("GET", "/api/fonts")).fonts; } catch (e) { fonts = []; }
    for (const f of fonts) {
      for (const file of f.files) {
        const m = /-(\w+?)(Italic)?\.(ttf|otf)$/i.exec(file);
        const weight = m ? (WEIGHTS[m[1].toLowerCase()] || 400) : 400;
        try {
          const face = new FontFace(f.family, `url(/api/fonts/file/${file})`, { weight: String(weight), style: m && m[2] ? "italic" : "normal" });
          document.fonts.add(face);
          face.load().catch(() => {});
        } catch (e) { /* ignore broken font */ }
      }
    }
  }

  const hexA = (hex, a) => {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  // CSS for a style inside a preview frame whose real width is frameW px, shown at boxW px.
  L.styleCss = (s, layout, boxW) => {
    const frameW = layout === "9:16" ? 1080 : 1920, frameH = layout === "9:16" ? 1920 : 1080;
    const k = boxW / frameW;
    const auto = layout === "9:16" ? Math.round(frameH * 0.044) : Math.round(frameH * 0.075);
    const px = (s.size_px || (L.state && L.state.project.settings.font_size_px) || auto) * k;
    const shadows = [];
    if (s.shadow_opacity > 0) shadows.push(`${s.shadow_offset_x * k}px ${s.shadow_offset_y * k}px ${s.shadow_blur * k}px ${hexA(s.shadow_color, s.shadow_opacity)}`);
    if (s.glow_size > 0) {
      const g = s.glow_size * k;
      for (let i = 0; i < Math.max(1, Math.round(s.glow_strength * 2)); i++) shadows.push(`0 0 ${g * (i + 1) / 2}px ${s.glow_color}`);
    }
    return {
      fontFamily: `"${s.font_family}", sans-serif`, fontWeight: weightOf(s.font_style),
      fontStyle: italicOf(s.font_style) ? "italic" : "normal", fontSize: `${px}px`,
      color: hexA(s.fill, s.fill_opacity), textAlign: s.align, lineHeight: s.line_spacing,
      letterSpacing: `${s.letter_spacing}em`,
      webkitTextStroke: s.outline_width > 0 ? `${s.outline_width * 2 * k}px ${s.outline_color}` : "0",
      paintOrder: "stroke fill", textShadow: shadows.join(", ") || "none",
      top: `${(layout === "9:16" ? s.position_y_9x16 : s.position_y_16x9) * 100}%`,
    };
  };

  function previewText() {
    const ids = L.selectedWordIds();
    const st = L.state;
    if (ids.length) {
      const b = st.blocks.find((x) => x.word_ids.includes(ids[0]));
      if (b) return b.display;
    }
    return st.blocks.length ? st.blocks[0].display : "Your lyrics here";
  }

  function paintPreview() {
    const s = draft;
    if (!s) return;
    document.querySelectorAll(".style-preview").forEach((box) => {
      const layout = box.dataset.layout;
      const t = $(".pv-text", box);
      t.textContent = previewText();
      Object.assign(t.style, L.styleCss(s, layout, box.clientWidth || 300));
    });
  }
  L.paintPreview = paintPreview;

  function field(label, key, type = "text", attrs = {}) {
    const val = draft[key];
    const input = type === "select"
      ? h("select", { "data-key": key }, attrs.options.map((o) => h("option", { value: o, selected: o === val }, o)))
      : h("input", Object.assign({ "data-key": key, type, value: val }, attrs));
    input.addEventListener("input", () => {
      draft[key] = type === "number" || type === "range" ? parseFloat(input.value) : input.value;
      paintPreview();
    });
    return h("label", { class: "field" }, label, input);
  }

  function render(st) {
    const body = L.card("card-style", "Text style");
    if (body.contains(document.activeElement) && document.activeElement.tagName !== "BUTTON") { paintPreview(); return; }
    body.innerHTML = "";
    const S = st.styles;
    const names = Object.keys(S.presets);
    if (!editing || !S.presets[editing]) editing = S.default;
    draft = Object.assign({}, S.presets[editing]);
    const isBuiltin = S.builtin.includes(editing);
    const level = st.project.settings.styling_level;

    body.append(
      h("div", { class: "row" },
        h("label", { class: "field" }, "Styling level in Resolve",
          h("select", { id: "style-level", onchange: (e) => L.op("set_styling_level", { level: e.target.value }, "styling level") },
            [["basic", "BASIC – plain Text+"], ["styled", "STYLED – preset look"], ["full", "FULL – styled + animations"]]
              .map(([v, t]) => h("option", { value: v, selected: v === level }, t)))),
        h("label", { class: "field" }, "Default style",
          h("select", { id: "style-default", onchange: (e) => L.op("set_default_style", { name: e.target.value }, "default style") },
            names.map((n) => h("option", { value: n, selected: n === S.default }, n))))),
      h("div", { class: "previews" },
        h("div", { class: "style-preview p169", "data-layout": "16:9" }, h("div", { class: "pv-text" }), h("span", { class: "pv-tag" }, "16:9")),
        h("div", { class: "style-preview p916", "data-layout": "9:16" }, h("div", { class: "pv-text" }), h("span", { class: "pv-tag" }, "9:16"))),
      h("label", { class: "field" }, "Edit style",
        h("select", { id: "style-edit", onchange: (e) => { editing = e.target.value; render(L.state); } },
          names.map((n) => h("option", { value: n, selected: n === editing }, n + (S.builtin.includes(n) ? " (built-in)" : ""))))),
      h("datalist", { id: "font-families" }, fonts.map((f) => h("option", { value: f.family }, `${f.source} · ${f.license}`))),
      h("div", { class: "row" }, field("Font", "font_family", "text", { list: "font-families", id: "style-font" }),
        field("Weight / style", "font_style", "text", { list: "font-styles" })),
      h("datalist", { id: "font-styles" }, ["Regular", "Medium", "Semibold", "Bold", "Black", "Italic", "Bold Italic"].map((v) => h("option", { value: v }))),
      h("div", { class: "row" }, field("Size px (0 = auto)", "size_px", "number", { min: 0 }), field("Fill", "fill", "color"),
        field("Opacity", "fill_opacity", "number", { min: 0, max: 1, step: 0.05 })),
      h("div", { class: "row" }, field("Outline", "outline_color", "color"), field("Outline px", "outline_width", "number", { min: 0, step: 0.5 })),
      h("div", { class: "row" }, field("Shadow", "shadow_color", "color"), field("Shadow opacity", "shadow_opacity", "number", { min: 0, max: 1, step: 0.05 }),
        field("Blur", "shadow_blur", "number", { min: 0 })),
      h("div", { class: "row" }, field("Glow", "glow_color", "color"), field("Glow size", "glow_size", "number", { min: 0 }),
        field("Glow strength", "glow_strength", "number", { min: 0, step: 0.1 })),
      h("div", { class: "row" }, field("Align", "align", "select", { options: ["left", "center", "right"] }),
        field("Height 16:9 (0-1)", "position_y_16x9", "number", { min: 0, max: 1, step: 0.01 }),
        field("Height 9:16 (0-1)", "position_y_9x16", "number", { min: 0, max: 1, step: 0.01 })),
      h("div", { class: "row" }, field("Animation in", "animation_in", "select", { options: S.animations }),
        field("Animation out", "animation_out", "select", { options: S.animations }), field("Anim ms", "animation_ms", "number", { min: 0, step: 10 })),
      h("p", { class: "hint" }, level === "full" ? "Animations are used (FULL)." : "Animations are only used at level FULL."),
      h("div", { class: "row" },
        isBuiltin ? "" : h("button", { class: "primary", id: "style-save", onclick: () => L.op("save_style", { name: editing, style: draft }, "save style") }, "Save"),
        h("button", { id: "style-save-as", onclick: () => {
          const name = prompt("Name for this style:", isBuiltin ? `${editing} copy` : editing);
          if (name) { L.op("save_style", { name, style: draft }, "save style").then((ok) => { if (ok) { editing = name; render(L.state); } }); }
        } }, "Save as…"),
        isBuiltin ? "" : h("button", { id: "style-delete", onclick: () => { if (confirm(`Delete style ${editing}?`)) L.op("delete_style", { name: editing }, "delete style"); } }, "Delete")),
      h("h4", {}, "Where styles are used"),
      sectionStyles(st, names),
      blockStyle(st, names));
    paintPreview();
  }

  function sectionStyles(st, names) {
    const labels = [...new Set(st.project.sections.map((s) => s.label.toLowerCase()))];
    if (!labels.length) return h("p", { class: "hint" }, "No sections yet: every block uses the default style.");
    return h("div", {}, labels.map((lab) => h("label", { class: "field inline-field" }, lab,
      h("select", { "data-section-label": lab,
        onchange: (e) => L.op("set_section_style", { section_label: lab, name: e.target.value || null }, "section style") },
        [h("option", { value: "" }, "(default)")].concat(names.map((n) => h("option", { value: n, selected: st.styles.by_section[lab] === n }, n)))))));
  }

  function blockStyle(st, names) {
    const ids = L.selectedWordIds();
    const blocks = [...new Set(ids.map((id) => st.blocks.find((b) => b.word_ids.includes(id))).filter(Boolean))];
    if (!blocks.length) return h("p", { class: "hint" }, "Select words to give their block(s) their own style.");
    const cur = blocks[0].style || "";
    return h("label", { class: "field" }, `Style of ${blocks.length} selected block(s)`,
      h("select", { id: "style-block", onchange: async (e) => {
        for (const b of blocks) await L.op("set_block_style", { block_id: b.id, style: e.target.value || null }, "block style");
      } }, [h("option", { value: "" }, "(section / default)")].concat(names.map((n) => h("option", { value: n, selected: n === cur }, n)))));
  }

  L.hooks.render.push(render);
  L.hooks.selection.push(() => { if (L.state) render(L.state); });
  window.addEventListener("resize", paintPreview);
  loadFonts().then(() => { if (L.state) render(L.state); });
})();
