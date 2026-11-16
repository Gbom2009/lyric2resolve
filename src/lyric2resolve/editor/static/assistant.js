/* Assistant card: chat with the real Claude Code CLI (optional). Claude edits the project through
   the app's MCP server -> this editor's API, so after every tool call we reload the state. */
(function () {
  const L2R = window.L2R;
  const $ = (s, r = document) => r.querySelector(s);
  let polling = false, seen = 0, turn = 0, available = false;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function build() {
    const body = $("#card-assistant .card-body");
    if (!body || body.dataset.built) return;
    body.dataset.built = "1";
    body.innerHTML = `
      <p class="hint" id="asst-status">Checking for Claude Code…</p>
      <div id="asst-log" class="asst-log" aria-live="polite"></div>
      <textarea id="asst-input" rows="3" placeholder="e.g. Make every chorus one word per block and use a bold glowing style for it"></textarea>
      <div class="row">
        <button class="primary" id="asst-send">Send</button>
        <button id="asst-stop" disabled>Stop</button>
        <button id="asst-new" title="Forget this project's Claude conversation (CLAUDE.md notes are kept)">New conversation</button>
      </div>
      <p class="hint" id="asst-usage">Optional: uses your own Claude login (Claude Pro has usage limits). The app works fully without it.</p>`;
    $("#asst-send").addEventListener("click", send);
    $("#asst-stop").addEventListener("click", () => L2R.api("POST", "/api/assistant/cancel").catch(() => {}));
    $("#asst-new").addEventListener("click", async () => {
      if (!confirm("Start a new conversation with Claude for this project?")) return;
      try { await L2R.api("POST", "/api/assistant/reset"); $("#asst-log").innerHTML = ""; note("New conversation started."); }
      catch (e) { note(e.message, "asst-error"); }
    });
    $("#asst-input").addEventListener("keydown", (ev) => {
      ev.stopPropagation(); // editor shortcuts must not fire while typing
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) send();
    });
  }

  function bubble(role, text) {
    const b = el("div", `asst-msg asst-${role}`);
    b.textContent = text;
    $("#asst-log").appendChild(b);
    $("#asst-log").scrollTop = $("#asst-log").scrollHeight;
    return b;
  }
  const note = (text, cls = "asst-note") => bubble(cls.replace("asst-", ""), text);

  function setBusy(busy) {
    $("#asst-send").disabled = busy || !available;
    $("#asst-stop").disabled = !busy;
    $("#asst-new").disabled = busy;
    $("#asst-input").disabled = !available;
  }

  async function refreshProject() {
    try { L2R.setState(await L2R.api("GET", "/api/state")); } catch (e) { /* project closed */ }
  }

  function show(ev) {
    switch (ev.kind) {
      case "text": bubble("assistant", ev.text); break;
      case "tool_use": bubble("tool", `⚙ ${ev.text.replace(/^mcp__lyric2resolve__/, "")}`); break;
      case "tool_result":
        if (ev.data.is_error) bubble("error", ev.text.slice(0, 400));
        else refreshProject();
        break;
      case "usage":
        if (ev.data.utilization) $("#asst-usage").textContent =
          `Claude usage: ${Math.round(ev.data.utilization * 100)}% of the ${String(ev.data.window || "").replace("_", "-")} window` +
          (ev.data.status === "allowed_warning" ? " — getting close to the limit." : ".");
        break;
      case "limit": case "login": case "error": bubble("error", ev.text); break;
      case "session":
        if (ev.data.mcp && ev.data.mcp !== "connected") bubble("error", `The app's tools did not connect (status: ${ev.data.mcp}). Claude can answer, but cannot edit.`);
        break;
      case "result":
        if (ev.data.permission_denials && ev.data.permission_denials.length)
          bubble("note", `Claude was not allowed to use: ${ev.data.permission_denials.join(", ")}`);
        break;
      case "info": if (ev.text) bubble("note", ev.text); break;
    }
  }

  async function poll() {
    if (polling) return;
    polling = true;
    try {
      for (;;) {
        const r = await L2R.api("GET", `/api/assistant/events?after=${seen}`);
        if (r.turn !== turn) { turn = r.turn; seen = 0; continue; }
        r.events.forEach(show);
        seen = r.next;
        setBusy(r.busy);
        if (!r.busy) break;
        await new Promise((res) => setTimeout(res, 600));
      }
    } catch (e) { bubble("error", e.message); setBusy(false); }
    polling = false;
    refreshProject();
  }

  async function send() {
    const input = $("#asst-input");
    const msg = input.value.trim();
    if (!msg || !available) return;
    try {
      const r = await L2R.api("POST", "/api/assistant/send", { message: msg });
      bubble("user", msg);
      input.value = "";
      turn = r.turn; seen = 0;
      setBusy(true);
      poll();
    } catch (e) { bubble("error", e.message); }
  }

  let projectKey = null;
  async function init() {
    build();
    $("#asst-log").innerHTML = "";
    try {
      const st = await L2R.api("GET", "/api/assistant/status");
      available = st.installed;
      $("#asst-status").textContent = st.installed ? `Claude Code ${st.version}` : st.message;
      const h = await L2R.api("GET", "/api/assistant/history");
      (h.history || []).slice(-20).forEach((m) => bubble(m.role, m.text));
      setBusy(st.busy);
      if (st.busy) poll();
    } catch (e) {
      $("#asst-status").textContent = e.message;
      available = false;
      setBusy(false);
    }
  }

  // (re)initialise when a project is opened (state key changes), not on every edit
  L2R.hooks.render.push((st) => {
    const key = st && st.project ? `${st.project.name}|${st.project.created}` : null;
    if (key && key !== projectKey) { projectKey = key; init(); }
  });
})();
