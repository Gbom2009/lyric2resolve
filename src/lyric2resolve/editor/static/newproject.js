/* New project dialog: upload song (+ acapella, lyrics), run the pipeline in the background, open the result. */
(() => {
  "use strict";
  const L = window.L2R;
  const $ = (s, r = document) => r.querySelector(s);
  let timer = null;

  function setBusy(busy) {
    $("#new-go").disabled = busy;
    $("#new-form").querySelectorAll("input, textarea, select").forEach((el) => { el.disabled = busy; });
  }

  function showLog(lines, extra = "") {
    const pre = $("#new-log");
    pre.hidden = false;
    pre.textContent = lines.join("\n") + (extra ? "\n\n" + extra : "");
    pre.scrollTop = pre.scrollHeight;
  }

  async function poll() {
    clearTimeout(timer);
    let st;
    try { st = await L.api("GET", "/api/projects/new/status"); }
    catch (e) { showLog([e.message]); setBusy(false); return; }
    showLog(st.log || [], st.running ? "Working… (you can leave this open)" : "");
    if (st.running) { timer = setTimeout(poll, 1000); return; }
    setBusy(false);
    if (st.ok) {
      try {
        L.setState(await L.api("POST", "/api/projects/new/open"));
        L.clearSelection();
        L.loadAudio();
        L.setStatus(`Project "${st.title}" ready — every edit is saved automatically`);
        $("#new-dialog").close();
        $("#new-form").reset();
        $("#new-log").hidden = true;
      } catch (e) { showLog(st.log || [], "Could not open the project: " + e.message); }
    } else if (st.done) {
      showLog(st.log || [], "FAILED: " + (st.error || "unknown error"));
      L.setStatus("New project failed — see the dialog", true);
    }
  }

  L.showNewProject = async () => {
    if ($("#project-dialog").open) $("#project-dialog").close();
    $("#new-dialog").showModal();
    try {  // a job may still be running (e.g. after a page reload)
      const st = await L.api("GET", "/api/projects/new/status");
      if (st.running) { setBusy(true); poll(); }
    } catch (e) { /* ignore */ }
  };

  $("#btn-new-project").onclick = () => L.showNewProject();
  $("#new-close").onclick = () => $("#new-dialog").close();
  $("#new-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = $("#new-form");
    const data = new FormData(form);
    const aca = form.elements.acapella.files[0];
    if (!aca) data.delete("acapella");
    setBusy(true);
    showLog(["Uploading the audio…"]);
    try {
      const res = await fetch("/api/projects/new", { method: "POST", body: data });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.detail || `${res.status} ${res.statusText}`);
      poll();
    } catch (e) {
      setBusy(false);
      showLog(["Could not start: " + e.message]);
    }
  });
})();
