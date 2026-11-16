/* "Add your own text": words/lines Whisper missed, placed at a time range you choose (undoable). */
(() => {
  "use strict";
  const L = window.L2R;
  const $ = (s, r = document) => r.querySelector(s);

  const playhead = () => (L.ws && L.audioReady ? L.ws.getCurrentTime() : 0);

  // free time around t: from the end of the last word before t to the start of the next word
  function freeAround(t) {
    const ws = L.words();
    let prevEnd = 0, nextStart = Infinity;
    for (const w of ws) {
      if (w.end <= t) prevEnd = Math.max(prevEnd, w.end);
      else if (w.start >= t) { nextStart = Math.min(nextStart, w.start); }
      else return null; // t is inside a word
    }
    return [prevEnd, nextStart];
  }

  function fill(start) {
    const free = freeAround(start);
    let end = start + 2;
    if (free && isFinite(free[1])) end = Math.min(end, Math.max(start + 0.2, free[1] - 0.02));
    $("#addtext-start").value = L.fmt(start);
    $("#addtext-end").value = L.fmt(end);
    $("#addtext-free").textContent = free
      ? `Free time here: ${L.fmt(free[0])} – ${isFinite(free[1]) ? L.fmt(free[1]) : "end of song"}`
      : "The playhead is inside a word: pick a time between words (move the playhead or type the times).";
  }

  L.showAddText = (start, end) => {
    if (!L.requireProject()) return;
    $("#addtext-msg").textContent = "";
    if (typeof start === "number" && typeof end === "number") {  // e.g. "missed lyrics" from the Review card
      fill(start);
      $("#addtext-end").value = L.fmt(end);
    } else {
      // after a selection: start right after it; otherwise at the playhead
      const span = L.selectedSpan();
      fill(span ? span[1] + 0.02 : playhead());
    }
    $("#addtext-dialog").showModal();
    $("#addtext-text").focus();
  };

  $("#addtext-playhead").onclick = () => fill(playhead());
  $("#addtext-close").onclick = () => $("#addtext-dialog").close();
  $("#addtext-start").addEventListener("change", () => {
    const s = L.parseTime($("#addtext-start").value);
    if (isFinite(s)) { const free = freeAround(s); $("#addtext-free").textContent = free ? `Free time here: ${L.fmt(free[0])} – ${isFinite(free[1]) ? L.fmt(free[1]) : "end of song"}` : "That start time is inside a word."; }
  });
  $("#addtext-dialog").addEventListener("keydown", (ev) => { ev.stopPropagation(); });
  $("#addtext-go").onclick = async () => {
    const text = $("#addtext-text").value;
    const start = L.parseTime($("#addtext-start").value), end = L.parseTime($("#addtext-end").value);
    if (!text.trim()) { $("#addtext-msg").textContent = "Type some text first."; return; }
    if (!isFinite(start) || !isFinite(end)) { $("#addtext-msg").textContent = "Times look like 1:23.45 (or 83.45 seconds)."; return; }
    try {
      const st = await L.api("POST", "/api/op/add_text", { text, start, end, mode: $("#addtext-mode").value });
      L.setState(st);
      L.setStatus(`Added “${text.trim().split(/\s+/).slice(0, 4).join(" ")}…” at ${L.fmt(start)} — saved (Ctrl+Z undoes it)`);
      $("#addtext-text").value = "";
      $("#addtext-dialog").close();
      const i = L.words().findIndex((w) => w.start >= start - 1e-3);
      if (i >= 0) { L.setSelection(i); const el = L.wordEls[i]; if (el) el.scrollIntoView({ block: "center" }); }
    } catch (e) { $("#addtext-msg").textContent = e.message; }
  };
})();
