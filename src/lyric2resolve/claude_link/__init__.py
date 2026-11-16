"""Claude Code link: the optional in-app Assistant (real `claude` CLI, your own login, no API key).

`Assistant` runs one background turn at a time for a project: it refreshes the project's CLAUDE.md,
writes the MCP config (the app's own MCP server, + the optional Blender MCP), and starts
`claude -p` with the project's saved session id (`--session-id` the first time, `--resume` after),
so the conversation continues across app restarts. The browser polls `events(after=n)`.

CLI:  lyric2resolve claude status | ask <project.json> "prompt" | mcp-config <project.json> | reset <project.json>
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from . import cli, notes

# Community Blender MCP server (optional; github.com/ahujasid/blender-mcp - verify against its README).
BLENDER_MCP = {"type": "stdio", "command": "uvx", "args": ["blender-mcp"]}


class Assistant:
    def __init__(self, editor_url: str = "", settings_dir: Path | None = None,
                 which: Callable[[str], str | None] | None = None, env: dict | None = None,
                 run_factory: Callable[..., cli.ClaudeRun] = cli.ClaudeRun):
        self.editor_url = editor_url
        self.settings_dir = settings_dir
        self.which = which
        self.env = env
        self.run_factory = run_factory
        self.events: list[cli.Event] = []
        self.run: cli.ClaudeRun | None = None
        self.project_path: Path | None = None
        self.turn = 0
        self._lock = threading.Lock()
        self._busy = threading.Event()

    # ---------------------------------------------------------------- config
    def _settings(self):
        from lyric2resolve.settings import load_settings

        return load_settings(self.settings_dir)[0]

    def status(self) -> dict:
        s = self._settings()
        st = cli.status(s.claude_cli_path, self.env, self.which)
        return {**st.to_dict(), "busy": self.busy(), "blender_mcp": bool(s.claude_blender_mcp),
                "model": s.claude_model}

    def busy(self) -> bool:
        return self._busy.is_set()

    # ---------------------------------------------------------------- one turn
    def send(self, project_path: Path, prompt: str, project=None) -> dict:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("empty message")
        if self.busy():
            raise RuntimeError("the Assistant is still answering - wait or press Stop")
        s = self._settings()
        exe = cli.find_claude(s.claude_cli_path, self.env, self.which)
        if not exe:
            raise FileNotFoundError(cli.INSTALL_HELP)
        project_path = Path(project_path)
        notes.write_notes(project_path, project)
        cfg = cli.write_mcp_config(project_path, editor_url=self.editor_url,
                                   blender_mcp=BLENDER_MCP if s.claude_blender_mcp else None)
        info = notes.load_session(project_path.parent)
        info.add("user", prompt)
        notes.save_session(project_path.parent, info)
        with self._lock:
            self.events = []
            self.turn += 1
            self.project_path = project_path
        self._busy.set()
        threading.Thread(target=self._turn, args=(exe, cfg, project_path, prompt, s), daemon=True).start()
        return {"turn": self.turn}

    def _turn(self, exe: Path, cfg: Path, project_path: Path, prompt: str, s) -> None:
        folder = project_path.parent
        try:
            for attempt in range(2):
                info = notes.load_session(folder)
                resume = bool(info.session_id)
                sid = info.session_id or cli.new_session_id()
                args = cli.build_args(exe, cfg, sid, resume, s.claude_model, s.claude_permission_mode,
                                      ["mcp__blender"] if s.claude_blender_mcp else None)
                run = self.run_factory(args, prompt, folder, self._env(), self._on_event)
                self.run = run
                run.start().wait()
                if run.cancelled:
                    break
                if not resume and any(e.kind == "result" for e in run.events):
                    info = notes.load_session(folder)
                    if not info.session_id:  # the CLI did not report an init event: keep the id we chose
                        info.session_id = sid
                        notes.save_session(folder, info)
                if any(e.data.get("no_session") for e in run.events) and attempt == 0:
                    notes.reset_session(folder)
                    self._emit(cli.Event("info", "Started a new Claude session (the old one was not found)."))
                    continue
                break
            text = run.final_text() if self.run else ""
            info = notes.load_session(folder)
            if text:
                info.add("assistant", text)
            info.runs += 1
            info.last_used = notes._now()
            notes.save_session(folder, info)
        finally:
            self._busy.clear()

    def _env(self) -> dict:
        env = dict(os.environ if self.env is None else self.env)
        env.pop("ANTHROPIC_API_KEY", None)  # always the user's own Claude login, never an API key
        return env

    def _on_event(self, ev: cli.Event) -> None:
        if ev.kind == "session" and ev.text and self.project_path:
            info = notes.load_session(self.project_path.parent)
            if info.session_id != ev.text:
                info.session_id = ev.text
                info.created = info.created or notes._now()
                notes.save_session(self.project_path.parent, info)
        self._emit(ev)

    def _emit(self, ev: cli.Event) -> None:
        with self._lock:
            self.events.append(ev)

    def poll(self, after: int = 0) -> dict:
        with self._lock:
            evs = [e.to_dict() for e in self.events[after:]]
            n = len(self.events)
        return {"turn": self.turn, "events": evs, "next": n, "busy": self.busy()}

    def cancel(self) -> None:
        if self.run and self.busy():
            self.run.cancel()

    def wait(self, timeout: float | None = None) -> bool:
        if not self.busy():
            return True
        import time

        end = None if timeout is None else time.time() + timeout
        while self.busy():
            if end is not None and time.time() > end:
                return False
            time.sleep(0.02)
        return True

    # ---------------------------------------------------------------- per project
    @staticmethod
    def history(project_path: Path) -> dict:
        folder = Path(project_path).parent
        info = notes.load_session(folder)
        return {"session_id": info.session_id, "runs": info.runs, "history": info.history,
                "notes": notes.read_user_notes(folder)}

    @staticmethod
    def reset(project_path: Path) -> None:
        notes.reset_session(Path(project_path).parent)


def main(argv: list[str]) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="lyric2resolve claude")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="is the Claude Code CLI installed?")
    a = sub.add_parser("ask", help="send one message to the project's Assistant session")
    a.add_argument("project", type=Path)
    a.add_argument("prompt")
    m = sub.add_parser("mcp-config", help="write the MCP config next to project.json (for `claude --mcp-config`)")
    m.add_argument("project", type=Path)
    m.add_argument("--editor-url", default="")
    r = sub.add_parser("reset", help="forget the saved Claude session (CLAUDE.md notes are kept)")
    r.add_argument("project", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "status":
        st = Assistant().status()
        print(f"Claude Code: {'found ' + st['path'] + ' (' + st['version'] + ')' if st['installed'] else 'not found'}")
        print(st["message"])
        return 0 if st["installed"] else 1
    if args.cmd == "mcp-config":
        notes.write_notes(args.project)
        print(cli.write_mcp_config(args.project, editor_url=args.editor_url))
        return 0
    if args.cmd == "reset":
        Assistant.reset(args.project)
        print("Session forgotten; the next message starts a new conversation.")
        return 0
    asst = Assistant()
    try:
        asst.send(args.project, args.prompt)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    seen = 0
    while True:
        done = asst.wait(0.2)
        res = asst.poll(seen)
        seen = res["next"]
        for ev in res["events"]:
            if ev["kind"] == "text":
                print(ev["text"])
            elif ev["kind"] == "tool_use":
                print(f"  [tool] {ev['text']} {json.dumps(ev['data'].get('input'))[:200]}")
            elif ev["kind"] in ("limit", "login", "error"):
                print(f"!! {ev['text']}")
        if done and not asst.busy():
            break
    return 0
