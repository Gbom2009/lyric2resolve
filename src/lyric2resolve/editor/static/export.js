/* Export dialog: choose layouts/formats, run the export, show the written files. */
(() => {
  "use strict";
  const L = window.L2R;
  const $ = (s, r = document) => r.querySelector(s);
  const LABELS = {
    fcpxml: "FCPXML for DaVinci Resolve (File > Import > Timeline)",
    resolve: "Resolve script with real Text+ clips + styling (Workspace > Scripts)",
    srt_csv_edl: "SRT (lines + words), CSV and EDL markers",
  };

  $("#btn-export").onclick = async () => {
    if (!L.requireProject()) return;
    const box = $("#export-formats");
    if (!box.childElementCount) {
      const { formats } = await L.api("GET", "/api/export/formats");
      formats.forEach((f) => box.append(L.h("label", { class: "check" },
        L.h("input", { type: "checkbox", name: "format", value: f, checked: f === "fcpxml" }), " ", LABELS[f] || f.toUpperCase())));
    }
    $("#export-result").textContent = "";
    $("#export-dialog").showModal();
  };
  $("#btn-karaoke").onclick = async () => {
    const { current } = await L.api("GET", "/api/projects");
    window.open(current ? `/karaoke?path=${encodeURIComponent(current)}` : "/karaoke", "l2r-karaoke");
  };
  $("#export-go").onclick = async () => {
    const pick = (n) => [...document.querySelectorAll(`#export-dialog input[name=${n}]:checked`)].map((i) => i.value);
    const out = $("#export-result");
    out.textContent = "Exporting…";
    try {
      const res = await L.api("POST", "/api/export", { layouts: pick("layout"), formats: pick("format"), beats: $("#export-beats").value });
      out.textContent = `Saved in ${res.folder}:\n` + res.files.map((f) => "  " + f.split(/[\\/]/).pop()).join("\n") +
        (res.resolve_script ? `\n\nResolve script installed. In Resolve: Workspace > Scripts > Utility > lyric2resolve_build_timeline` : "") +
        (res.warnings.length ? "\n\nNotes:\n" + res.warnings.map((w) => "  " + w).join("\n") : "");
      L.setStatus(`Exported ${res.files.length} file(s)`);
    } catch (e) {
      out.textContent = "Export failed: " + e.message;
      L.setStatus(e.message, true);
    }
  };
})();
