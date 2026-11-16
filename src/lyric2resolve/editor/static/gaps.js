/* Instrumental gaps: draggable/resizable regions on the waveform + list with add/remove. */
(() => {
  "use strict";
  const L = window.L2R;
  const h = (...a) => L.h(...a);
  let syncing = false;

  function syncRegions() {
    if (!L.regions || !L.audioReady || !L.state) return;
    syncing = true;
    L.regions.getRegions().filter((r) => String(r.id).startsWith("gap-")).forEach((r) => r.remove());
    L.state.project.gaps.forEach((g) => {
      L.regions.addRegion({
        id: `gap-${g.id}`, start: g.start, end: g.end, drag: true, resize: true,
        color: g.source === "manual" ? "rgba(80, 80, 80, 0.28)" : "rgba(120, 120, 120, 0.20)",
        content: "gap",
      });
    });
    syncing = false;
  }

  function wire() {
    if (!L.regions || L.regions._l2rGapWired) return;
    L.regions._l2rGapWired = true;
    L.regions.on("region-updated", (r) => {
      if (syncing || !String(r.id).startsWith("gap-")) return;
      const gapId = String(r.id).slice(4);
      L.op("update_gap", { gap_id: gapId, start: +r.start.toFixed(3), end: +r.end.toFixed(3) }, "resize gap");
    });
    L.regions.on("region-double-clicked", (r, ev) => {
      if (!String(r.id).startsWith("gap-")) return;
      if (ev) ev.stopPropagation();
      if (confirm("Remove this instrumental gap?")) L.op("remove_gap", { gap_id: String(r.id).slice(4) }, "remove gap");
    });
  }

  function renderList() {
    const body = L.card("card-gaps", "Instrumental gaps");
    body.innerHTML = "";
    const gaps = L.state.project.gaps;
    body.append(h("p", { class: "hint" },
      "No text or clips are placed inside gaps. Drag/resize gaps on the waveform; double-click one to remove it."));
    const list = h("ul", { class: "plain-list", id: "gap-list" });
    gaps.forEach((g) => list.append(h("li", {},
      h("button", { class: "linkish", title: "Jump to gap", onclick: () => { if (L.ws && L.audioReady) L.ws.setTime(g.start); } },
        `${L.fmt(g.start)} – ${L.fmt(g.end)}`),
      h("span", { class: "hint" }, ` ${(g.end - g.start).toFixed(1)} s · ${g.source} `),
      h("button", { class: "small", title: "Remove gap", onclick: () => L.op("remove_gap", { gap_id: g.id }, "remove gap") }, "✕"))));
    if (!gaps.length) list.append(h("li", { class: "hint" }, "No gaps."));
    body.append(list,
      h("div", { class: "row" },
        h("button", { onclick: () => {
          const span = L.selectedSpan();
          if (span) return L.op("add_gap", { start: span[0], end: span[1] }, "add gap");
          const t = L.ws && L.audioReady ? L.ws.getCurrentTime() : 0;
          L.op("add_gap", { start: t, end: t + 4 }, "add gap");
        } }, "Add gap (selection or 4 s at cursor)")));
  }

  L.hooks.render.push(() => { renderList(); wire(); syncRegions(); });
  L.hooks.ready.push(() => { wire(); syncRegions(); });
})();
