"""Claude link: CLI discovery/args/stream parsing, CLAUDE.md notes, session store, MCP server
(in-process + over the live editor API), the Assistant with a fake `claude` executable, render jobs."""

from __future__ import annotations

import io
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from lyric2resolve import project as proj
from lyric2resolve.claude_link import Assistant, cli, mcp_server, notes
from lyric2resolve.render.jobs import RenderJobs
from lyric2resolve.settings import AppSettings, load_settings, save_settings
from tests.e2e.conftest import free_port, make_project

FAKE = Path(__file__).parent / "data" / "fake_claude.py"


def make_fake_claude(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        exe = folder / "claude.cmd"
        exe.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
    else:
        exe = folder / "claude"
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


@pytest.fixture
def project_path(tmp_path):
    return make_project(tmp_path)


@pytest.fixture
def settings_dir(tmp_path):
    d = tmp_path / "settings"
    save_settings(AppSettings(claude_cli_path=str(make_fake_claude(tmp_path / "bin"))), d)
    return d


def env_with(**extra):
    env = dict(os.environ)
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + str(Path(__file__).resolve().parents[1])
    env.update(extra)
    return env


# ------------------------------------------------------------------ discovery + args
def test_find_claude_order(tmp_path):
    conf = tmp_path / "my" / "claude.exe"
    conf.parent.mkdir()
    conf.write_text("x")
    assert cli.find_claude(str(conf), {}, which=lambda n: "/usr/bin/claude") == conf
    assert cli.find_claude("", {}, which=lambda n: "/usr/bin/claude") == Path("/usr/bin/claude")
    home = tmp_path / "home"
    native = home / ".local" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_text("x")
    assert cli.find_claude("", {"USERPROFILE": str(home)}, which=lambda n: None) == native
    npm = tmp_path / "AppData" / "npm" / "claude.cmd"
    npm.parent.mkdir(parents=True)
    npm.write_text("x")
    assert cli.find_claude("", {"APPDATA": str(npm.parents[1])}, which=lambda n: None) == npm
    assert cli.find_claude("", {}, which=lambda n: None) is None


def test_status_missing_and_found(tmp_path):
    st = cli.status("", {}, which=lambda n: None)
    assert not st.installed and "install" in st.message.lower()
    exe = make_fake_claude(tmp_path)
    st = cli.status(str(exe), {}, which=lambda n: None)
    assert st.installed and st.version.startswith("2.1")


def test_build_args_new_and_resume(tmp_path):
    a = cli.build_args(Path("claude"), tmp_path / "m.json", "sid-1", resume=False)
    assert a[:5] == ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    assert a[a.index("--session-id") + 1] == "sid-1" and "--resume" not in a
    assert a[a.index("--allowedTools") + 1] == "mcp__lyric2resolve"
    assert a[a.index("--mcp-config") + 1] == str(tmp_path / "m.json")
    b = cli.build_args(Path("claude"), None, "sid-1", resume=True, model="sonnet", permission_mode="acceptEdits",
                       extra_allowed=["mcp__blender"])
    assert b[b.index("--resume") + 1] == "sid-1" and "--session-id" not in b and "--mcp-config" not in b
    assert b[b.index("--allowedTools") + 1] == "mcp__lyric2resolve,mcp__blender"
    assert b[b.index("--model") + 1] == "sonnet" and b[b.index("--permission-mode") + 1] == "acceptEdits"


def test_mcp_config_file(project_path):
    path = cli.write_mcp_config(project_path, editor_url="http://127.0.0.1:9/", blender_mcp={"command": "uvx"})
    cfg = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
    srv = cfg["lyric2resolve"]
    assert srv["args"][:2] == ["-m", "lyric2resolve.claude_link.mcp_server"]
    assert srv["args"][srv["args"].index("--editor-url") + 1] == "http://127.0.0.1:9/"
    assert Path(srv["env"]["PYTHONPATH"], "lyric2resolve").is_dir()
    assert cfg["blender"] == {"command": "uvx"}


# ------------------------------------------------------------------ stream parsing
def ev(obj):
    return cli.parse_line(json.dumps(obj))


def test_parse_events():
    (s,) = ev({"type": "system", "subtype": "init", "session_id": "abc", "model": "m",
               "mcp_servers": [{"name": "lyric2resolve", "status": "failed"}]})
    assert s.kind == "session" and s.text == "abc" and s.data["mcp"] == "failed"
    out = ev({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"},
                                                           {"type": "tool_use", "id": "t", "name": "x", "input": {"a": 1}}]}})
    assert [(e.kind, e.text) for e in out] == [("text", "hi"), ("tool_use", "x")] and out[1].data["input"] == {"a": 1}
    (r,) = ev({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "is_error": True,
                                                         "content": [{"type": "text", "text": "bad"}]}]}})
    assert r.kind == "tool_result" and r.text == "bad" and r.data["is_error"]
    (u,) = ev({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning", "rateLimitType": "five_hour",
                                                               "unifiedWindows": {"five_hour": {"utilization": 0.9}}}})
    assert u.kind == "usage" and u.data["utilization"] == 0.9
    (lim,) = ev({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}})
    assert lim.kind == "limit"
    login = ev({"type": "result", "is_error": True, "result": "Invalid API key · Please run /login"})
    assert [e.kind for e in login] == ["login", "result"]
    limit = ev({"type": "result", "is_error": True, "result": "Claude usage limit reached"})
    assert [e.kind for e in limit] == ["limit", "result"]
    ok = ev({"type": "result", "is_error": False, "result": "fine", "permission_denials": [{"tool_name": "Bash"}]})
    assert ok[0].data["permission_denials"] == ["Bash"]
    assert cli.parse_line("") == [] and cli.parse_line("not json")[0].kind == "info"
    assert ev({"type": "stream_event", "event": {}}) == [] and ev([1, 2]) == []


# ------------------------------------------------------------------ notes + session
def test_notes_keep_user_part(project_path):
    path = notes.write_notes(project_path)
    text = path.read_text(encoding="utf-8")
    assert "E2E song" in text and "Words: 9" in text and notes.NOTES_HEADER in text
    path.write_text(text.replace("- (nothing yet)", "- chorus = one word per block, neon style"), encoding="utf-8")
    p = proj.load(project_path)
    p.name = "Renamed"
    notes.write_notes(project_path, p)
    text2 = path.read_text(encoding="utf-8")
    assert "Renamed" in text2 and "neon style" in text2 and text2.count(notes.STATE_BEGIN) == 1
    assert notes.read_user_notes(project_path.parent) == "- chorus = one word per block, neon style"


def test_notes_wraps_existing_free_text(tmp_path, project_path):
    (project_path.parent / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    text = notes.write_notes(project_path).read_text(encoding="utf-8")
    assert text.startswith(notes.STATE_BEGIN) and "my own notes" in text


def test_session_store(tmp_path):
    info = notes.load_session(tmp_path)
    assert info.session_id == ""
    info.session_id = "s1"
    for i in range(notes.SessionInfo.MAX_HISTORY + 5):
        info.add("user", f"m{i}")
    notes.save_session(tmp_path, info)
    back = notes.load_session(tmp_path)
    assert back.session_id == "s1" and len(back.history) == notes.SessionInfo.MAX_HISTORY
    notes.reset_session(tmp_path)
    notes.reset_session(tmp_path)  # idempotent
    assert notes.load_session(tmp_path).session_id == ""
    (tmp_path / notes.SESSION_FILE).write_text("[broken", encoding="utf-8")
    assert notes.load_session(tmp_path).session_id == ""


# ------------------------------------------------------------------ MCP server (in-process)
class FakeRender:
    def __init__(self):
        self.calls = []

    def __call__(self, path, **kw):
        self.calls.append(kw)
        from lyric2resolve.render.runner import Progress

        for i in range(1, 4):
            if kw["cancel"].is_set():
                return {"ok": False, "cancelled": True}
            kw["on_progress"]("16:9", Progress(i, 3, i, 0.1 * i, 0.1))
            kw["log"](f"frame {i}")
            time.sleep(0.02)
        if kw["template"] == "boom":
            raise RuntimeError("unknown template boom")
        return {"ok": True, "videos": ["x.mp4"]}


def rpc(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def call(server, tool, /, **args):
    res = rpc(server, "tools/call", {"name": tool, "arguments": args})["result"]
    text = res["content"][0]["text"]
    return (json.loads(text) if not res["isError"] else text), res["isError"]


def test_mcp_protocol_basics(project_path):
    srv = mcp_server.McpServer(mcp_server.FileBackend(project_path))
    init = rpc(srv, "initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"]
    assert rpc(srv, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == \
        mcp_server.PROTOCOL_VERSIONS[0]
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert rpc(srv, "ping")["result"] == {}
    assert rpc(srv, "nope")["error"]["code"] == -32601
    names = {t["name"] for t in rpc(srv, "tools/list")["result"]["tools"]}
    for needed in ("get_project", "list_blocks", "list_words", "merge_words", "split_block", "add_gap", "remove_gap",
                   "get_flags", "apply_section_presets", "set_style", "export", "preview_render", "render_progress",
                   "list_textures", "list_fonts", "undo"):
        assert needed in names
    for t in rpc(srv, "tools/list")["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object" and t["description"]


def test_mcp_tools_edit_and_undo(project_path):
    srv = mcp_server.McpServer(mcp_server.FileBackend(project_path))
    info, err = call(srv, "get_project")
    assert not err and info["name"] == "E2E song" and info["blocks"] == 3 and info["gaps"][0]["id"] == "g0100"
    words, _ = call(srv, "list_words", start=0, end=3)
    assert words["items"][0]["text"] == "We" and all(w["start"] <= 3 for w in words["items"])
    ids = [w["id"] for w in call(srv, "list_words")[0]["items"][:2]]
    res, err = call(srv, "merge_words", word_ids=ids)
    assert not err and res["ok"] and res["can_undo"]
    blocks, _ = call(srv, "list_blocks", limit=1)
    assert blocks["items"][0]["text"] == "We sing" and blocks["more"]
    assert proj.load(project_path).blocks[0].word_ids == ids  # saved immediately
    call(srv, "undo")
    assert len(proj.load(project_path).blocks) == 3
    res, err = call(srv, "add_gap", start=1.0, end=1.1)
    assert not err
    msg, err = call(srv, "merge_words", word_ids=["nope"])
    assert err and "nope" in msg
    msg, err = call(srv, "edit_project", op="rm_rf")
    assert err and "unknown op" in msg
    msg, err = call(srv, "list_blocks", bogus=1)
    assert err and "bad arguments" in msg
    msg, err = call(srv, "set_style", name="Club", style={"font": "Arial"})
    assert err and "font_family" in msg
    msg, err = call(srv, "set_style", name="Neon", style={"font_family": "Arial"})
    assert err and "built-in" in msg
    _, err = call(srv, "set_style", name="Club", style={"font_family": "Arial", "size_px": 80, "glow_size": 8},
                  section_label="chorus", make_default=True)
    assert not err
    styles, _ = call(srv, "list_styles")
    assert styles["default"] == "Club" and styles["by_section"]["chorus"] == "Club"
    assert styles["presets"]["Club"]["glow_size"] == 8
    msg, err = call(srv, "set_style", name="Club")
    assert err
    _, err = call(srv, "set_styling_level", level="full")
    assert not err and proj.load(project_path).settings.styling_level == "full"
    flags, _ = call(srv, "get_flags")
    assert any(f["kind"] == "low_confidence" for f in flags["flags"])


def test_mcp_export_and_render(project_path):
    fake = FakeRender()
    be = mcp_server.FileBackend(project_path, jobs=RenderJobs(fake))
    srv = mcp_server.McpServer(be)
    res, err = call(srv, "export", formats=["srt_csv_edl"], layouts=["16:9"])
    assert not err and any(f.endswith(".srt") for f in res["files"])
    res, err = call(srv, "preview_render", template="tunnel")
    assert not err and res["running"]
    be.jobs.wait(5)
    prog, _ = call(srv, "render_progress")
    assert not prog["running"] and prog["done"] == 3 and prog["report"]["ok"] and "frame 3" in prog["log"]
    assert fake.calls[0]["template"] == "tunnel" and fake.calls[0]["preset_name"] == "preview"
    _, _ = call(srv, "preview_render", template="boom")
    be.jobs.wait(5)
    assert "boom" in call(srv, "render_progress")[0]["error"]
    tex, err = call(srv, "list_textures")
    assert not err and "textures" in tex
    fonts, err = call(srv, "list_fonts")
    assert not err and isinstance(fonts["fonts"], list)


def test_render_jobs_cancel_and_single():
    slow = threading.Event()

    def render(path, **kw):
        slow.wait(5)
        return {"ok": not kw["cancel"].is_set()}

    jobs = RenderJobs(render)
    jobs.start(Path("p.json"))
    with pytest.raises(RuntimeError):
        jobs.start(Path("p.json"))
    jobs.cancel()
    slow.set()
    assert jobs.wait(5) and jobs.progress()["report"] == {"ok": False}


def test_mcp_stdio_loop(project_path):
    srv = mcp_server.McpServer(mcp_server.FileBackend(project_path))
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}), "", "{bad json",
             json.dumps([{"jsonrpc": "2.0", "id": 2, "method": "ping"}, {"jsonrpc": "2.0", "id": 3, "method": "ping"}])]
    out = io.StringIO()
    srv.serve(io.StringIO("\n".join(lines) + "\n"), out)
    resp = [json.loads(x) for x in out.getvalue().splitlines()]
    assert resp[0]["id"] == 1 and resp[1]["error"]["code"] == -32700 and [r["id"] for r in resp[2]] == [2, 3]


# ------------------------------------------------------------------ live editor (HTTP backend + Assistant)
@pytest.fixture
def live_editor(project_path, settings_dir):
    uvicorn = pytest.importorskip("uvicorn")
    from lyric2resolve.editor.app import EditorSession, create_app

    session = EditorSession(project_path)
    asst = Assistant(settings_dir=settings_dir, env=env_with())
    jobs = RenderJobs(FakeRender())
    app = create_app(session, project_path.parents[1], settings_dir=settings_dir, assistant=asst, jobs=jobs)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/", app, asst
    server.should_exit = True
    th.join(timeout=5)


def current_session(app):
    return app.state.holder["session"]


def test_http_backend_shares_editor_state(live_editor, project_path):
    url, app, _ = live_editor
    srv = mcp_server.McpServer(mcp_server.HttpBackend(url, project_path))
    ids = [w["id"] for w in call(srv, "list_words")[0]["items"][2:4]]
    res, err = call(srv, "merge_words", word_ids=ids)
    assert not err and res["ok"]
    s = current_session(app)
    assert any(b.word_ids == ids for b in s.project.blocks) and s.history.state()["can_undo"]
    msg, err = call(srv, "remove_gap", gap_id="nope")
    assert err and "nope" in msg
    res, err = call(srv, "preview_render", preset="draft")
    assert not err
    for _ in range(100):
        if not call(srv, "render_progress")[0]["running"]:
            break
        time.sleep(0.05)
    assert call(srv, "render_progress")[0]["report"]["ok"]
    bad = mcp_server.McpServer(mcp_server.HttpBackend("http://127.0.0.1:9/", project_path, timeout=2))
    msg, err = call(bad, "get_project")
    assert err and "not reachable" in msg


def run_turn(asst, project_path, prompt, project=None, timeout=60):
    asst.send(project_path, prompt, project)
    assert asst.wait(timeout), "assistant turn did not finish"
    return asst.poll(0)["events"]


def test_assistant_turns_resume_and_tools(live_editor, project_path, tmp_path):
    url, app, asst = live_editor
    asst.editor_url = url
    log = tmp_path / "argv.log"
    asst.env = env_with(FAKE_CLAUDE_LOG=str(log), ANTHROPIC_API_KEY="must-not-leak")
    evs = run_turn(asst, project_path, "hello there")
    assert [e for e in evs if e["kind"] == "text"][0]["text"] == "echo: hello there"
    assert any(e["kind"] == "usage" for e in evs)
    sid = notes.load_session(project_path.parent).session_id
    assert sid
    words = current_session(app).project.words
    run_turn(asst, project_path, "TOOL merge_words " + json.dumps({"word_ids": [words[0].id, words[1].id]}))
    assert current_session(app).project.blocks[0].word_ids == [words[0].id, words[1].id]  # edited via the editor
    argvs = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert argvs[0][argvs[0].index("--session-id") + 1] == sid
    assert argvs[1][argvs[1].index("--resume") + 1] == sid
    hist = Assistant.history(project_path)
    assert [m["role"] for m in hist["history"]] == ["user", "assistant", "user", "assistant"] and hist["runs"] == 2
    assert (project_path.parent / "CLAUDE.md").is_file() and (project_path.parent / cli.MCP_CONFIG_FILE).is_file()
    assert "ANTHROPIC_API_KEY" not in asst._env()


@pytest.mark.parametrize("mode,kind", [("login", "login"), ("limit", "limit")])
def test_assistant_login_and_limit(project_path, settings_dir, mode, kind):
    asst = Assistant(settings_dir=settings_dir, env=env_with(FAKE_CLAUDE_MODE=mode))
    evs = run_turn(asst, project_path, "hi")
    assert any(e["kind"] == kind for e in evs)


def test_assistant_recovers_lost_session(project_path, settings_dir):
    notes.save_session(project_path.parent, notes.SessionInfo(session_id="old-gone"))
    asst = Assistant(settings_dir=settings_dir, env=env_with(FAKE_CLAUDE_MODE="nosession"))
    evs = run_turn(asst, project_path, "hi")
    assert any("new Claude session" in e["text"] for e in evs)
    assert any(e["kind"] == "text" and e["text"] == "echo: hi" for e in evs)
    assert notes.load_session(project_path.parent).session_id not in ("", "old-gone")


def test_assistant_busy_cancel_and_missing(project_path, settings_dir, tmp_path):
    asst = Assistant(settings_dir=settings_dir, env=env_with(FAKE_CLAUDE_MODE="slow"))
    asst.send(project_path, "wait")
    with pytest.raises(RuntimeError):
        asst.send(project_path, "again")
    time.sleep(0.3)
    asst.cancel()
    assert asst.wait(10)
    assert any(e["text"] == "Cancelled." for e in asst.poll(0)["events"])
    with pytest.raises(ValueError):
        asst.send(project_path, "   ")
    nod = tmp_path / "nod"
    save_settings(AppSettings(claude_cli_path=""), nod)
    missing = Assistant(settings_dir=nod, which=lambda n: None, env={})
    with pytest.raises(FileNotFoundError):
        missing.send(project_path, "hi")
    assert not missing.status()["installed"]


def test_editor_assistant_endpoints(live_editor, project_path):
    import urllib.request

    url, app, asst = live_editor

    def api(method, route, body=None):
        req = urllib.request.Request(url + route, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    code, st = api("GET", "api/assistant/status")
    assert code == 200 and st["installed"] and not st["busy"]
    code, r = api("POST", "api/assistant/send", {"message": "ping"})
    assert code == 200 and r["turn"] == 1
    assert asst.wait(60)
    assert asst.editor_url == url
    code, r = api("GET", "api/assistant/events?after=0")
    assert any(e["kind"] == "text" and e["text"] == "echo: ping" for e in r["events"]) and not r["busy"]
    code, r = api("GET", "api/assistant/events?after=" + str(r["next"]))
    assert r["events"] == []
    code, h = api("GET", "api/assistant/history")
    assert h["session_id"] and len(h["history"]) == 2
    code, h = api("POST", "api/assistant/reset")
    assert code == 200 and h["session_id"] == ""
    code, r = api("POST", "api/assistant/send", {"message": ""})
    assert code == 400
    code, r = api("POST", "api/render", {"template": "tunnel", "evil": 1})
    assert code == 200 and r["template"] == "tunnel"


def test_settings_permission_mode_validation(tmp_path):
    save_settings(AppSettings(claude_permission_mode="bypassPermissions"), tmp_path)
    s, warnings = load_settings(tmp_path)
    assert s.claude_permission_mode == "" and any("claude_permission_mode" in w for w in warnings)


def test_cli_status_command(settings_dir, monkeypatch, capsys):
    from lyric2resolve.__main__ import main

    monkeypatch.setattr("lyric2resolve.claude_link.Assistant.__init__.__defaults__",
                        ("", settings_dir, None, None, cli.ClaudeRun))
    assert main(["claude", "status"]) == 0
    assert "2.1.325" in capsys.readouterr().out


def test_verify_checks_claude_and_mcp(settings_dir, monkeypatch):
    from lyric2resolve import verify

    monkeypatch.setattr("lyric2resolve.settings.load_settings",
                        lambda d=None, _orig=load_settings: _orig(settings_dir))
    ctx = verify.Context(repo=Path(__file__).resolve().parents[1])
    res = {r.name: r for r in verify.run_checks(ctx, only={"claude_cli", "mcp_server"})}
    assert res["claude_cli"].status == verify.OK and "2.1.325" in res["claude_cli"].detail
    assert res["mcp_server"].status == verify.OK, res["mcp_server"].detail
