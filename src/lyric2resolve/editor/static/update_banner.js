/* In-browser update banner. Uses the launcher's updater logic (/api/update/status); "Update now" hands over
   to the launcher, which stops the editor, updates safely (rollback point, auto-rollback) and shows what changed. */
(function () {
  const banner = () => document.getElementById("update-banner");
  let timer = null;

  function describe(u) {
    if (!u || u.state === "not_checked") return "Not checked yet.";
    const v = u.version ? `Installed version ${u.version}. ` : "";
    switch (u.state) {
      case "up_to_date": return `${v}Up to date.`;
      case "behind": return `${v}Update available: ${u.behind} new change${u.behind === 1 ? "" : "s"}.`;
      case "diverged": return `${v}Update available (${u.message})`;
      case "ahead": return `${v}${u.message}`;
      case "offline": return `${v}Offline — could not check for updates.`;
      default: return `${v}${u.message || u.state}`;
    }
  }

  function dismissed(u) {
    try { return sessionStorage.getItem("l2r-update-later") === String(u.behind) + (u.commits || [])[0]; }
    catch (e) { return false; }
  }

  function show(u) {
    const el = banner();
    if (!el) return;
    if (!u.update_available || dismissed(u)) { el.hidden = true; return; }
    el.hidden = false;
    el.innerHTML = `<b>Update available</b> <span class="hint"></span>
      <button class="primary" data-act="now">Update now</button>
      <button data-act="info">What's new</button> <button data-act="later">Later</button>
      <pre class="update-log" hidden></pre>`;
    el.querySelector(".hint").textContent = describe(u);
    el.querySelector("pre").textContent = (u.changelog || "").trim() + "\n\nChanges:\n" + (u.commits || []).join("\n");
    el.querySelector('[data-act="info"]').onclick = () => { const p = el.querySelector("pre"); p.hidden = !p.hidden; };
    el.querySelector('[data-act="later"]').onclick = () => {
      try { sessionStorage.setItem("l2r-update-later", String(u.behind) + (u.commits || [])[0]); } catch (e) { /* ok */ }
      el.hidden = true;
    };
    el.querySelector('[data-act="now"]').onclick = async () => {
      if (u.dirty && !confirm("Files in the app folder were changed locally; the update will refuse and explain. Continue?")) return;
      const res = await fetch("/api/update/request", { method: "POST" });
      const j = await res.json().catch(() => ({}));
      el.querySelector(".hint").textContent = res.ok ? j.message : (j.detail || "Could not start the update.");
      if (res.ok) el.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    };
  }

  async function check(refresh = false) {
    clearTimeout(timer);
    try {
      const res = await fetch(`/api/update/status${refresh ? "?refresh=true" : ""}`);
      if (!res.ok) return;
      const u = await res.json();
      document.dispatchEvent(new CustomEvent("l2r-update", { detail: u }));
      show(u);
      if (u.checking || refresh) timer = setTimeout(() => check(false), 2500);
    } catch (e) { /* editor stopped (e.g. while updating) */ }
  }

  window.L2RUpdate = { check, describe };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => check(false));
  else check(false);
})();
