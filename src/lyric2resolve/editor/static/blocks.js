/* Block/word editing: toolbar, selection inspector, shortcuts. Depends on app.js (window.L2R). */
(() => {
  "use strict";
  const L = window.L2R;
  const $ = (s, r = document) => r.querySelector(s);

  // tiny DOM helper shared by the other panels
  L.h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, "");
      else if (v !== false && v !== null && v !== undefined) el.setAttribute(k, v);
    }
    kids.flat().forEach((c) => el.append(c instanceof Node ? c : document.createTextNode(String(c))));
    return el;
  };
  L.card = (id, title) => {
    let c = document.getElementById(id);
    if (!c) {
      c = L.h("section", { class: "card", id }, L.h("h3", {}, title), L.h("div", { class: "card-body" }));
      $("#side").appendChild(c);
    }
    return $(".card-body", c);
  };

  // ------------------------------------------------------------------ helpers
  const sel = () => L.selectedWordIds();
  const blockOfWord = (wid) => L.state.blocks.find((b) => b.word_ids.includes(wid)) || null;
  const selBlocks = () => {
    const ids = new Set();
    return sel().map(blockOfWord).filter((b) => b && !ids.has(b.id) && ids.add(b.id));
  };

  const A = (L.actions = {
    merge: () => sel().length && L.op("merge_words", { word_ids: sel() }, "merge"),
    split: () => {
      const ids = sel();
      if (!ids.length) return;
      const b = blockOfWord(ids[0]);
      if (!b) return L.setStatus("That word is not in a block", true);
      if (b.word_ids[0] === ids[0]) {
        // selection starts a block: split after the selection instead
        const last = ids[ids.length - 1];
        const k = b.word_ids.indexOf(last);
        if (k < 0 || k === b.word_ids.length - 1) return L.setStatus("Select the word that should start the new block", true);
        return L.op("split_block", { block_id: b.id, before_word_id: b.word_ids[k + 1] }, "split");
      }
      return L.op("split_block", { block_id: b.id, before_word_id: ids[0] }, "split");
    },
    splitWords: () => { const b = blockOfWord(sel()[0]); if (b) L.op("split_block_words", { block_id: b.id }, "split into words"); },
    movePrev: () => { const ids = sel(); if (ids.length) L.op("move_word", { word_id: ids[0], direction: "prev" }, "move word"); },
    moveNext: () => { const ids = sel(); if (ids.length) L.op("move_word", { word_id: ids[ids.length - 1], direction: "next" }, "move word"); },
    removeBlocks: async () => {
      const bs = selBlocks();
      for (const b of bs) await L.op("remove_block", { block_id: b.id }, "remove block");
    },
    nudge: (delta, edge = "both") => sel().length && L.op("nudge_words", { word_ids: sel(), delta, edge }, `nudge ${delta > 0 ? "+" : ""}${Math.round(delta * 1000)} ms`),
    gapFromSelection: () => {
      const span = L.selectedSpan();
      if (span) L.op("add_gap", { start: span[0], end: span[1] }, "add gap");
    },
    edit: () => { const inp = $("#insp-word-text") || $("#insp-block-text"); if (inp) { inp.focus(); inp.select(); } },
  });

  // ------------------------------------------------------------------ toolbar
  const tb = $("#block-toolbar");
  const btn = (label, title, fn, id) => tb.appendChild(L.h("button", { title, id, onclick: fn }, label));
  btn("Merge", "Merge selected words into one block (M)", A.merge, "btn-merge");
  btn("Split", "Split the block at the selected word (S)", A.split, "btn-split");
  btn("Words", "Split the block into single words (W)", A.splitWords, "btn-split-words");
  btn("← Move", "Move the first selected word to the previous block (Alt+←)", A.movePrev, "btn-move-prev");
  btn("Move →", "Move the last selected word to the next block (Alt+→)", A.moveNext, "btn-move-next");
  btn("Edit", "Edit text (E or Enter)", A.edit, "btn-edit");
  btn("Remove", "Remove the block(s) from the timeline; words stay in the project (Delete)", A.removeBlocks, "btn-remove");
  btn("+ Gap", "Make the selected time an instrumental gap (G)", A.gapFromSelection, "btn-gap");

  function updateToolbar(range) {
    const has = !!range;
    tb.querySelectorAll("button").forEach((b) => { b.disabled = !has; });
  }
  L.hooks.selection.push(updateToolbar);
  updateToolbar(null);

  // ------------------------------------------------------------------ inspector
  function renderInspector() {
    const body = L.card("card-selection", "Selection");
    body.innerHTML = "";
    const ids = sel();
    if (!ids.length) {
      body.append(L.h("p", { class: "hint" }, "Click, drag or Shift+click words to select them."));
      return;
    }
    const words = L.state.project.words;
    const r = L.selectedRange();
    const span = L.selectedSpan();
    body.append(L.h("p", {}, `${ids.length} word(s) · ${L.fmt(span[0])} – ${L.fmt(span[1])}`));
    if (ids.length === 1) {
      const w = words[r[0]];
      const save = () => {
        const text = $("#insp-word-text").value, s = parseFloat($("#insp-start").value), e = parseFloat($("#insp-end").value);
        (async () => {
          if (text !== w.text) await L.op("set_word_text", { word_id: w.id, text }, "edit word");
          if (s !== w.start || e !== w.end) await L.op("set_word_timing", { word_id: w.id, start: s, end: e }, "set timing");
        })();
      };
      const enter = (ev) => { if (ev.key === "Enter") { ev.preventDefault(); save(); } if (ev.key === "Escape") ev.target.blur(); };
      body.append(
        L.h("label", { class: "field" }, "Word", L.h("input", { id: "insp-word-text", value: w.text, onkeydown: enter })),
        L.h("div", { class: "row" },
          L.h("label", { class: "field" }, "Start (s)", L.h("input", { id: "insp-start", type: "number", step: "0.01", value: w.start, onkeydown: enter })),
          L.h("label", { class: "field" }, "End (s)", L.h("input", { id: "insp-end", type: "number", step: "0.01", value: w.end, onkeydown: enter }))),
        L.h("p", { class: "hint" }, `Confidence ${Math.round(w.confidence * 100)}%`),
        L.h("button", { class: "primary", onclick: save }, "Save word"));
    }
    const nud = L.h("div", { class: "row" },
      L.h("button", { title: "[ (Shift = 100 ms)", onclick: () => A.nudge(-0.02) }, "◀ 20 ms"),
      L.h("button", { title: "] (Shift = 100 ms)", onclick: () => A.nudge(0.02) }, "20 ms ▶"),
      L.h("button", { title: "Move only the start earlier", onclick: () => A.nudge(-0.02, "start") }, "start −"),
      L.h("button", { title: "Move only the end later", onclick: () => A.nudge(0.02, "end") }, "end +"));
    body.append(L.h("p", { class: "hint" }, "Nudge timing"), nud);
    const blocks = selBlocks();
    if (blocks.length === 1) {
      const b = blocks[0];
      const saveBlock = () => L.op("set_block_text", { block_id: b.id, text: $("#insp-block-text").value }, "edit block text");
      body.append(
        L.h("label", { class: "field" }, "Block text (as shown in the video)",
          L.h("input", { id: "insp-block-text", value: b.text,
            onkeydown: (ev) => { if (ev.key === "Enter") { ev.preventDefault(); saveBlock(); } if (ev.key === "Escape") ev.target.blur(); } })),
        L.h("div", { class: "row" },
          L.h("button", { onclick: saveBlock }, "Save block text"),
          b.overridden ? L.h("button", { onclick: () => L.op("set_block_text", { block_id: b.id, text: null }, "reset block text") }, "Reset to words") : ""),
        L.h("p", { class: "hint" }, `Export text: “${b.display}”`));
    }
  }
  L.hooks.selection.push(renderInspector);
  L.hooks.render.push(renderInspector);

  // ------------------------------------------------------------------ shortcuts
  L.hooks.keydown.push((ev) => {
    if (ev.ctrlKey || ev.metaKey) return false;
    const k = ev.key.toLowerCase();
    if (!sel().length) return false;
    if (ev.altKey && ev.key === "ArrowLeft") { A.movePrev(); return true; }
    if (ev.altKey && ev.key === "ArrowRight") { A.moveNext(); return true; }
    if (ev.altKey) return false;
    if (k === "m") { A.merge(); return true; }
    if (k === "s") { A.split(); return true; }
    if (k === "w") { A.splitWords(); return true; }
    if (k === "g") { A.gapFromSelection(); return true; }
    if (k === "e" || ev.key === "Enter") { A.edit(); return true; }
    if (ev.key === "Delete" || ev.key === "Backspace") { A.removeBlocks(); return true; }
    if (ev.key === "[" || ev.key === "{") { A.nudge(ev.shiftKey ? -0.1 : -0.02); return true; }
    if (ev.key === "]" || ev.key === "}") { A.nudge(ev.shiftKey ? 0.1 : 0.02); return true; }
    return false;
  });
})();
