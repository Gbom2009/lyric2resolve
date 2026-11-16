/* Karaoke player: word-by-word highlight, gap countdown, Web Audio mix (instrumental + vocals with a
   vocal volume slider, sample-accurate because both buffers start on the same AudioContext clock),
   playlists/queue with search + reorder, keyboard shortcuts. Works offline from saved projects. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);

  // ------------------------------------------------------------------ pure timing logic (unit-tested via the page)
  const K = (window.K = {});
  K.stateAt = (data, t) => {
    const lines = data.lines;
    let cur = -1, next = -1;
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (l.start <= t && t < l.end + 0.25) cur = i;
      if (l.start > t && next === -1) next = i;
    }
    let word = -1, progress = 0;
    if (cur >= 0) {
      const ws = lines[cur].words;
      for (let j = 0; j < ws.length; j++) if (ws[j].start <= t) word = j;
      if (word >= 0) {
        const w = ws[word];
        progress = Math.max(0, Math.min(1, (t - w.start) / Math.max(0.05, w.end - w.start)));
      }
    }
    // countdown when nothing is being sung and the next line is more than 2 s away
    const upcoming = next >= 0 ? lines[next] : null;
    const prevEnd = cur >= 0 ? lines[cur].end : (next > 0 ? lines[next - 1].end : (next === -1 && lines.length ? lines[lines.length - 1].end : 0));
    const inGap = (data.gaps || []).some((g) => g.start <= t && t < g.end);
    const wait = upcoming ? upcoming.start - t : null;
    const countdown = cur < 0 && upcoming && (wait > 2 || inGap || next === 0) ? { seconds: Math.ceil(wait), fraction: Math.min(1, Math.max(0, (t - prevEnd) / Math.max(0.1, upcoming.start - prevEnd))), label: t < (lines[0] || {}).start ? "Get ready" : "Instrumental" } : null;
    let cdown = countdown;
    if (!cdown && inGap && cur < 0) {          // gap with no lyrics after it: count down to the gap's end
      const g = data.gaps.find((x) => x.start <= t && t < x.end);
      cdown = { seconds: Math.ceil(g.end - t), fraction: (t - g.start) / Math.max(0.1, g.end - g.start), label: "Instrumental" };
    }
    return { current: cur, next: next, word, progress, countdown: cdown, inGap };
  };

  // ------------------------------------------------------------------ state
  const S = { data: null, path: null, playlists: null, projects: [], ctx: null, bufs: {}, nodes: [], gains: {},
              playing: false, startedAt: 0, offset: 0, index: -1, raf: 0 };
  K.S = S;
  const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  async function api(method, url, body) {
    const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => null);
    if (!r.ok) throw new Error((d && d.detail) || r.statusText);
    return d;
  }

  // ------------------------------------------------------------------ audio (Web Audio)
  function ctx() {
    if (!S.ctx) {
      S.ctx = new (window.AudioContext || window.webkitAudioContext)();
      S.gains.music = S.ctx.createGain();
      S.gains.vocals = S.ctx.createGain();
      S.gains.music.connect(S.ctx.destination);
      S.gains.vocals.connect(S.ctx.destination);
      applyVolumes(true);
    }
    return S.ctx;
  }
  async function loadBuffer(kind) {
    const res = await fetch(`/api/karaoke/audio/${kind}?path=${encodeURIComponent(S.path)}`);
    if (!res.ok) return null;
    return ctx().decodeAudioData(await res.arrayBuffer());
  }
  function applyVolumes(instant = false) {
    if (!S.ctx) return;
    const v = Number($("#k-vocals").value) / 100, m = Number($("#k-music").value) / 100;
    const now = S.ctx.currentTime;
    // fades: ~0.15 s time constant so moving the slider never clicks
    S.gains.vocals.gain.setTargetAtTime(S.musicIsSong ? 0 : v, now, instant ? 0.001 : 0.15);
    S.gains.music.gain.setTargetAtTime(m, now, instant ? 0.001 : 0.15);
    $("#k-vocals-val").textContent = S.musicIsSong ? "n/a" : `${Math.round(v * 100)}%`;
  }
  function stopNodes() { S.nodes.forEach((n) => { try { n.stop(); } catch (e) { /* already stopped */ } }); S.nodes = []; }
  function startAt(offset) {
    stopNodes();
    const c = ctx();
    const when = c.currentTime + 0.05;
    const add = (buf, gain) => {
      if (!buf) return;
      const n = c.createBufferSource();
      n.buffer = buf;
      n.connect(gain);
      n.start(when, Math.max(0, offset));
      S.nodes.push(n);
    };
    add(S.bufs.music, S.gains.music);
    add(S.bufs.vocals, S.gains.vocals);
    S.startedAt = when - offset;
    S.playing = true;
    if (S.nodes[0]) S.nodes[0].onended = () => { if (S.playing && K.time() >= S.data.duration - 0.2) next(); };
    $("#k-play").textContent = "⏸";
  }
  K.time = () => (S.playing && S.ctx ? S.ctx.currentTime - S.startedAt : S.offset);
  function pause() { if (!S.playing) return; S.offset = K.time(); stopNodes(); S.playing = false; $("#k-play").textContent = "▶"; }
  async function toggle() {
    if (!S.data) { if (S.playlists && current().length) await load(0); else return; }
    await ctx().resume();
    if (S.playing) pause(); else startAt(S.offset);
  }
  function seek(t) { t = Math.max(0, Math.min(S.data ? S.data.duration : 0, t)); S.offset = t; if (S.playing) startAt(t); render(true); }

  // ------------------------------------------------------------------ songs
  const current = () => (S.playlists ? S.playlists.playlists[S.playlists.current] || [] : []);
  async function load(i) {
    const list = current();
    if (i < 0 || i >= list.length) return;
    pause();
    S.index = i;
    S.path = list[i];
    S.offset = 0;
    try {
      S.data = await api("GET", `/api/karaoke/data?path=${encodeURIComponent(S.path)}`);
    } catch (e) { $("#empty").textContent = `Cannot load: ${e.message}`; $("#empty").hidden = false; return; }
    $("#song-title").textContent = S.data.name;
    $("#k-dur").textContent = fmt(S.data.duration);
    $("#empty").textContent = "Loading audio…";
    $("#empty").hidden = false;
    // instrumental + acapella by default; fall back to the full song (vocal slider disabled)
    const [inst, voc] = await Promise.all([S.data.audio.instrumental ? loadBuffer("instrumental") : null,
      S.data.audio.vocals ? loadBuffer("vocals") : null]);
    if (inst) { S.bufs = { music: inst, vocals: voc }; S.musicIsSong = false; }
    else { S.bufs = { music: await loadBuffer("song"), vocals: null }; S.musicIsSong = true; }
    $("#empty").hidden = true;
    applyVolumes(true);
    renderQueue();
    render(true);
  }
  async function next() { if (S.index + 1 < current().length) { await load(S.index + 1); startAt(0); } else pause(); }
  async function prev() { if (K.time() > 3) return seek(0); if (S.index > 0) { await load(S.index - 1); startAt(0); } }

  // ------------------------------------------------------------------ rendering
  let lastLine = -2;
  function lineHtml(line, wordIdx, progress) {
    const el = document.createDocumentFragment();
    line.words.forEach((w, j) => {
      const s = document.createElement("span");
      s.className = "w" + (wordIdx > j ? " sung" : wordIdx === j ? " now" : "");
      if (wordIdx === j) s.style.setProperty("--p", `${Math.round(progress * 100)}%`);
      s.textContent = w.text + (j < line.words.length - 1 ? " " : "");
      el.appendChild(s);
    });
    return el;
  }
  function render(force = false) {
    if (!S.data) return;
    const t = K.time();
    const st = K.stateAt(S.data, t);
    $("#k-time").textContent = fmt(t);
    $("#k-seek").value = S.data.duration ? Math.round((t / S.data.duration) * 1000) : 0;
    const cd = $("#countdown");
    cd.hidden = !st.countdown;
    if (st.countdown) {
      $("#cd-num").textContent = st.countdown.seconds;
      $("#cd-label").textContent = st.countdown.label;
      $("#cd-fill").style.width = `${Math.round(st.countdown.fraction * 100)}%`;
    }
    const curEl = $("#line-current"), nextEl = $("#line-next");
    const showIdx = st.current >= 0 ? st.current : (st.countdown ? -1 : st.next);
    curEl.replaceChildren(showIdx >= 0 ? lineHtml(S.data.lines[showIdx], st.current >= 0 ? st.word : -1, st.progress) : "");
    const upcomingIdx = st.current >= 0 ? st.current + 1 : st.next;
    const up = S.data.lines[upcomingIdx];
    if (force || lastLine !== upcomingIdx) nextEl.textContent = up && upcomingIdx !== showIdx ? up.text : "";
    lastLine = upcomingIdx;
    K.last = st;
  }
  function loop() { render(); S.raf = requestAnimationFrame(loop); }

  // ------------------------------------------------------------------ queue / playlists
  async function savePlaylists() { S.playlists = await api("PUT", "/api/karaoke/playlists", S.playlists); renderQueue(); }
  function renderQueue() {
    const sel = $("#q-list");
    sel.replaceChildren(...Object.keys(S.playlists.playlists).map((n) => { const o = document.createElement("option"); o.value = n; o.textContent = n; o.selected = n === S.playlists.current; return o; }));
    const byPath = Object.fromEntries(S.projects.map((p) => [p.path, p]));
    const ol = $("#q-items");
    ol.replaceChildren(...current().map((path, i) => {
      const li = document.createElement("li");
      li.className = i === S.index ? "playing" : "";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = (byPath[path] || {}).name || path.split(/[\\/]/).slice(-2, -1)[0];
      const btn = (label, title, fn) => { const b = document.createElement("button"); b.textContent = label; b.title = title; b.onclick = fn; return b; };
      li.append(btn("▶", "Play", async () => { await load(i); await ctx().resume(); startAt(0); }), name,
        btn("↑", "Move up", () => move(i, -1)), btn("↓", "Move down", () => move(i, 1)), btn("✕", "Remove", () => remove(i)));
      return li;
    }));
    const q = $("#q-search").value.toLowerCase();
    const ul = $("#q-projects");
    ul.replaceChildren(...S.projects.filter((p) => p.name.toLowerCase().includes(q)).map((p) => {
      const li = document.createElement("li");
      const name = document.createElement("span"); name.className = "name"; name.textContent = p.name;
      const b = document.createElement("button"); b.textContent = "+ add"; b.onclick = () => { current().push(p.path); savePlaylists(); };
      li.append(name, b);
      return li;
    }));
  }
  function move(i, d) {
    const l = current(), j = i + d;
    if (j < 0 || j >= l.length) return;
    [l[i], l[j]] = [l[j], l[i]];
    if (S.index === i) S.index = j; else if (S.index === j) S.index = i;
    savePlaylists();
  }
  function remove(i) { current().splice(i, 1); if (i < S.index) S.index--; else if (i === S.index) S.index = -1; savePlaylists(); }
  K.move = move;

  // ------------------------------------------------------------------ wiring
  $("#k-play").onclick = toggle;
  $("#k-next").onclick = next;
  $("#k-prev").onclick = prev;
  $("#k-vocals").oninput = () => applyVolumes();
  $("#k-music").oninput = () => applyVolumes();
  $("#k-seek").oninput = (e) => S.data && seek((Number(e.target.value) / 1000) * S.data.duration);
  $("#k-queue").onclick = () => { $("#queue").hidden = !$("#queue").hidden; };
  $("#k-full").onclick = () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {}));
  document.addEventListener("fullscreenchange", () => document.body.classList.toggle("fs", !!document.fullscreenElement));
  $("#q-search").oninput = renderQueue;
  $("#q-list").onchange = (e) => { S.playlists.current = e.target.value; S.index = -1; savePlaylists(); };
  $("#q-new").onclick = () => { const n = prompt("Name of the new playlist:"); if (n && !S.playlists.playlists[n]) { S.playlists.playlists[n] = []; S.playlists.current = n; savePlaylists(); } };
  document.addEventListener("keydown", (ev) => {
    if (ev.target.closest("input[type=search], select")) return;
    const k = ev.key.toLowerCase();
    const vol = (d) => { const v = $("#k-vocals"); v.value = Math.max(0, Math.min(100, +v.value + d)); applyVolumes(); };
    if (ev.code === "Space") { ev.preventDefault(); toggle(); }
    else if (k === "n") next();
    else if (k === "p") prev();
    else if (ev.key === "ArrowUp") { ev.preventDefault(); vol(10); }
    else if (ev.key === "ArrowDown") { ev.preventDefault(); vol(-10); }
    else if (ev.key === "ArrowRight") seek(K.time() + 5);
    else if (ev.key === "ArrowLeft") seek(K.time() - 5);
    else if (k === "f") $("#k-full").click();
    else if (k === "q") $("#k-queue").click();
  });

  async function boot() {
    S.playlists = await api("GET", "/api/karaoke/playlists");
    S.projects = (await api("GET", "/api/projects")).projects;
    const params = new URLSearchParams(location.search);
    if (params.get("path")) {           // opened from the editor: play this project
      if (!current().includes(params.get("path"))) { current().push(params.get("path")); await savePlaylists(); }
      await load(current().indexOf(params.get("path")));
    } else if (current().length) await load(0);
    else $("#queue").hidden = false;
    renderQueue();
    loop();
  }
  K.ready = boot();
})();
