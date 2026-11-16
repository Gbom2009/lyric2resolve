/* Review list (sanity flags + safe-area warnings), sections & presets, text options. */
(() => {
  "use strict";
  const L = window.L2R;
  const h = (...a) => L.h(...a);
  const $ = (s, r = document) => r.querySelector(s);

  function jumpToWord(wordId) {
    const i = L.state.project.words.findIndex((w) => w.id === wordId);
    if (i < 0) return;
    L.setSelection(i, i);
    const el = L.wordEls[i];
    if (el) el.scrollIntoView({ block: "center" });
    if (L.ws && L.audioReady) L.ws.setTime(L.state.project.words[i].start);
  }
  function jumpToBlock(blockId) {
    const b = L.state.blocks.find((x) => x.id === blockId);
    if (!b) return;
    const ws = L.state.project.words;
    const a = ws.findIndex((w) => w.id === b.word_ids[0]);
    const z = ws.findIndex((w) => w.id === b.word_ids[b.word_ids.length - 1]);
    L.setSelection(a, z);
    const el = L.wordEls[a];
    if (el) el.scrollIntoView({ block: "center" });
  }
  L.jumpToWord = jumpToWord;

  // ------------------------------------------------------------------ review
  function renderReview(st) {
    const body = L.card("card-review", "Review");
    body.innerHTML = "";
    const flags = st.flags || [];
    const warns = st.layout_warnings || [];
    body.append(h("p", { class: "hint" },
      `${flags.length} word(s) to check · ${warns.length} line-length warning(s). Nothing is changed automatically.`));
    const list = h("ol", { class: "review-list", id: "review-list" });
    flags.forEach((f) => list.append(h("li", { class: `flag ${f.severity}` },
      h("button", { class: "linkish", "data-word-id": f.word_id, onclick: () => (f.start != null && L.ws && L.audioReady)
        ? L.ws.setTime(f.start) : jumpToWord(f.word_id) },
        h("b", {}, f.kind.replace(/_/g, " ")), " — ", f.message),
      f.kind === "missed_lyrics" && L.showAddText
        ? h("button", { class: "add-here", onclick: () => L.showAddText(f.start, f.end) }, "Add text here") : "")));
    warns.forEach((w) => list.append(h("li", { class: "flag layout" },
      h("button", { class: "linkish", "data-block-id": w.block_id, onclick: () => jumpToBlock(w.block_id) },
        h("b", {}, "too long"), " — ", w.message))));
    if (!flags.length && !warns.length) list.append(h("li", { class: "hint" }, "All good."));
    body.append(list);
    // mark blocks with layout warnings in the lyrics list
    const byBlock = new Map();
    warns.forEach((w) => byBlock.set(w.block_id, (byBlock.get(w.block_id) || []).concat(w.message)));
    document.querySelectorAll(".block[data-block-id]").forEach((row) => {
      const msgs = byBlock.get(row.dataset.blockId);
      row.classList.toggle("too-long", !!msgs);
      if (msgs) row.title = "⚠ " + msgs.join("\n⚠ ");
    });
  }

  // ------------------------------------------------------------------ sections & presets
  const PRESETS = ["", "word", "line", "phrase", "auto"];
  const LABELS = ["intro", "verse", "pre-chorus", "chorus", "drop", "bridge", "breakdown", "outro"];

  function renderSections(st) {
    const body = L.card("card-sections", "Sections & presets");
    body.innerHTML = "";
    const cfg = st.project.settings;
    const set = (k, v) => L.op("set_settings", { [k]: v }, `set ${k}`);
    body.append(
      h("div", { class: "row" },
        h("label", { class: "field" }, "Default preset",
          h("select", { id: "preset-default", onchange: (e) => set("granularity", e.target.value) },
            PRESETS.slice(1).map((p) => h("option", { value: p, selected: p === cfg.granularity }, p.toUpperCase())))),
        h("label", { class: "field" }, "PHRASE words",
          h("input", { type: "number", min: 1, max: 12, value: cfg.phrase_words, onchange: (e) => set("phrase_words", +e.target.value) })),
        h("label", { class: "field" }, "AUTO pause (s)",
          h("input", { type: "number", min: 0.1, step: 0.1, value: cfg.auto_pause_s, onchange: (e) => set("auto_pause_s", +e.target.value) }))));
    const table = h("table", { class: "sections" }, h("thead", {}, h("tr", {}, h("th", {}, "Section"), h("th", {}, "Time"), h("th", {}, "Preset"), h("th", {}, ""))));
    const tbody = h("tbody");
    st.project.sections.forEach((s) => tbody.append(h("tr", {},
      h("td", {}, h("input", { list: "section-labels", value: s.label, size: 9,
        onchange: (e) => L.op("update_section", { section_id: s.id, label: e.target.value }, "rename section") })),
      h("td", { class: "mono" }, `${L.fmt(s.start)}–${L.fmt(s.end)}`),
      h("td", {}, h("select", { onchange: (e) => L.op("set_section_preset", { section_id: s.id, preset: e.target.value || null }, "section preset") },
        PRESETS.map((p) => h("option", { value: p, selected: (s.preset || "") === p }, p ? p.toUpperCase() : "default")))),
      h("td", {}, h("button", { class: "small", title: "Rebuild blocks in this section from its preset",
        onclick: () => L.op("apply_presets", { section_id: s.id }, "apply preset to section") }, "Apply")))));
    if (!st.project.sections.length) tbody.append(h("tr", {}, h("td", { colspan: 4, class: "hint" }, "No sections yet (run analyze).")));
    table.append(tbody);
    body.append(table, h("datalist", { id: "section-labels" }, LABELS.map((l) => h("option", { value: l }))),
      h("div", { class: "row" },
        h("button", { id: "btn-apply-presets", onclick: () => {
          if (confirm("Rebuild ALL blocks from the presets? Your manual block edits are replaced (Undo brings them back)."))
            L.op("apply_presets", {}, "apply presets");
        } }, "Rebuild all blocks from presets")));
  }

  // ------------------------------------------------------------------ text options
  function renderOptions(st) {
    const body = L.card("card-options", "Text & timing options");
    body.innerHTML = "";
    const c = st.project.settings;
    const set = (k, v) => L.op("set_settings", { [k]: v }, `set ${k.replace(/_/g, " ")}`);
    const num = (k, label, attrs = {}) => h("label", { class: "field" }, label,
      h("input", Object.assign({ id: `opt-${k}`, type: "number", value: c[k], onchange: (e) => set(k, +e.target.value) }, attrs)));
    const chk = (k, label) => h("label", { class: "check" },
      h("input", { type: "checkbox", checked: !!c[k], onchange: (e) => set(k, e.target.checked) }), " ", label);
    body.append(
      h("div", { class: "row" },
        h("label", { class: "field" }, "Case", h("select", { onchange: (e) => set("case", e.target.value) },
          [["keep", "As typed"], ["upper", "UPPERCASE"], ["lower", "lowercase"], ["title", "Title Case"]]
            .map(([v, t]) => h("option", { value: v, selected: c.case === v }, t)))),
        num("max_chars", "Max chars/block", { min: 0 })),
      chk("strip_punctuation", "Strip punctuation"),
      h("div", { class: "row" }, num("min_clip_frames", "Min clip (frames)", { min: 1 }),
        h("button", { onclick: () => L.op("merge_short_blocks", {}, "merge short blocks") }, "Merge shorter blocks")),
      chk("hold_until_next", "Hold text until the next block (not inside gaps)"),
      h("div", { class: "row" }, num("fade_after_ms", "Fade after (ms)", { min: 0, step: 50 }),
        num("sync_offset_ms", "Global sync offset (ms)", { step: 10 })),
      h("div", { class: "row" }, num("pre_roll_ms", "Pre-roll (ms)", { min: 0, step: 10 }), num("post_roll_ms", "Post-roll (ms)", { min: 0, step: 10 })),
      h("div", { class: "row" }, num("font_size_px", "Font size px (0 = auto)", { min: 0 }), num("max_lines", "Max lines", { min: 1, max: 4 })),
      h("p", { class: "hint" }, `Layouts: ${c.layouts.join(" + ")} · ${c.fps} fps`));
  }

  L.hooks.render.push((st) => { renderReview(st); renderSections(st); renderOptions(st); });
})();
