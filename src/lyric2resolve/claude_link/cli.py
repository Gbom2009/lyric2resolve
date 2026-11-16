"""Run the real `claude` CLI headless as a background subprocess and parse its stream-json output.

Verified against Claude Code 2.1.x (`claude --help` + a real run):
  claude -p --output-format stream-json --verbose [--session-id UUID | --resume UUID]
         --mcp-config FILE --allowedTools mcp__lyric2resolve [--model M] [--permission-mode M]
The prompt is sent on stdin (no quoting problems with claude.cmd on Windows).
Events (one JSON object per line): system/init (session_id, mcp_servers), assistant (message.content
blocks: text / tool_use), user (tool_result blocks), rate_limit_event (rate_limit_info.status,
utilization), result (is_error, result, permission_denials). Unknown lines are ignored.

We never read, copy or store login tokens and never use an API key: the CLI uses the user's own login.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SERVER_NAME = "lyric2resolve"
# Read/search anywhere it is pointed at; write + edit ONLY inside the project folder (the working directory).
# Verified with Claude Code 2.1.325: writes in ./ are allowed, a write to ../ is denied.
FILE_TOOLS = ("Read", "Glob", "Grep", "Edit(./**)", "Write(./**)")
MCP_CONFIG_FILE = ".l2r_mcp.json"

INSTALL_HELP = (
    "The Claude Code CLI was not found. The app works fine without it; the Assistant is optional.\n"
    "To use it: install Claude Code (https://code.claude.com/docs - Windows: run "
    "`irm https://claude.ai/install.ps1 | iex` in PowerShell; Mac: run "
    "`curl -fsSL https://claude.ai/install.sh | bash` in Terminal; or `npm install -g @anthropic-ai/claude-code`), "
    "open a new terminal, run `claude` once and log in with your Claude account. "
    "If it is installed somewhere unusual, set its path in Settings (claude_cli_path).")
LOGIN_HELP = (
    "Claude Code is installed but not logged in (or the login expired). Open a terminal, run `claude`, "
    "type /login and sign in with your Claude account, then try again. The app never sees your login.")
LIMIT_HELP = (
    "Claude usage limit reached. Claude Pro has usage limits per few hours; the Assistant can continue "
    "after the reset time. Everything else in the app keeps working without it.")

_LOGIN_RE = re.compile(r"not logged in|please run /login|/login|invalid api key|authenticat|oauth token", re.I)
_LIMIT_RE = re.compile(r"usage limit|limit reached|rate limit|out of (extra )?usage|hit your limit", re.I)
_NO_SESSION_RE = re.compile(r"no conversation found|session .* not found|could not find session", re.I)


# ------------------------------------------------------------------ finding the CLI
def claude_candidates(env: dict[str, str]) -> list[Path]:
    home = env.get("USERPROFILE") or env.get("HOME") or ""
    appdata, local = env.get("APPDATA", ""), env.get("LOCALAPPDATA", "")
    out = []
    if home:
        out += [Path(home) / ".local" / "bin" / "claude.exe", Path(home) / ".local" / "bin" / "claude",
                Path(home) / ".claude" / "local" / "claude.exe", Path(home) / ".claude" / "local" / "claude"]
    if appdata:
        out += [Path(appdata) / "npm" / "claude.cmd", Path(appdata) / "npm" / "claude.exe"]
    if local:
        out += [Path(local) / "Programs" / "claude" / "claude.exe"]
    out += [Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude")]   # macOS (Homebrew / npm)
    if home:
        out += [Path(home) / ".npm-global" / "bin" / "claude"]
    return out


def find_claude(configured: str = "", env: dict[str, str] | None = None,
                which: Callable[[str], str | None] | None = None) -> Path | None:
    """Configured path > PATH > common install folders."""
    env = os.environ if env is None else env
    which = which or shutil.which
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return p
    hit = which("claude")
    if hit:
        return Path(hit)
    for cand in claude_candidates(env):
        if cand.is_file():
            return cand
    return None


def _popen_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0


def cli_version(exe: Path, timeout: float = 20) -> str:
    try:
        out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=timeout,
                             encoding="utf-8", errors="replace", creationflags=_popen_flags())
    except (OSError, subprocess.SubprocessError):
        return ""
    return (out.stdout or out.stderr or "").strip().splitlines()[0] if (out.stdout or out.stderr) else ""


def _killpg(pid: int) -> None:
    """Mac/Linux: SIGTERM the whole process group (claude + its MCP server)."""
    import signal

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, AttributeError):
        pass


@dataclass
class CliStatus:
    installed: bool
    path: str = ""
    version: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        return {"installed": self.installed, "path": self.path, "version": self.version, "message": self.message}


def status(configured: str = "", env: dict[str, str] | None = None,
           which: Callable[[str], str | None] | None = None) -> CliStatus:
    exe = find_claude(configured, env, which)
    if not exe:
        return CliStatus(False, message=INSTALL_HELP)
    ver = cli_version(exe)
    if not ver:
        return CliStatus(False, str(exe), message=f"Found {exe} but `claude --version` did not answer.\n{INSTALL_HELP}")
    return CliStatus(True, str(exe), ver, "Claude Code found. Login is checked when you send the first message.")


# ------------------------------------------------------------------ MCP config
def mcp_config(project_path: Path, editor_url: str = "", python: str | None = None,
               src_dir: Path | None = None, blender_mcp: dict | None = None) -> dict:
    """The MCP config for the background session: the app's own server (+ optional Blender MCP)."""
    src_dir = src_dir or Path(__file__).resolve().parents[2]
    args = ["-m", "lyric2resolve.claude_link.mcp_server", "--project", str(Path(project_path).resolve())]
    if editor_url:
        args += ["--editor-url", editor_url]
    servers = {SERVER_NAME: {"type": "stdio", "command": python or sys.executable, "args": args,
                             "env": {"PYTHONPATH": str(src_dir), "PYTHONIOENCODING": "utf-8"}}}
    if blender_mcp:
        servers["blender"] = blender_mcp
    return {"mcpServers": servers}


def write_mcp_config(project_path: Path, **kw) -> Path:
    path = Path(project_path).parent / MCP_CONFIG_FILE
    path.write_text(json.dumps(mcp_config(project_path, **kw), indent=2), encoding="utf-8")
    return path


def build_args(exe: Path, mcp_config_path: Path | None, session_id: str, resume: bool,
               model: str = "", permission_mode: str = "", extra_allowed: list[str] | None = None) -> list[str]:
    args = [str(exe), "-p", "--output-format", "stream-json", "--verbose"]
    args += ["--resume", session_id] if resume else ["--session-id", session_id]
    if mcp_config_path:
        args += ["--mcp-config", str(mcp_config_path)]
    allowed = [f"mcp__{SERVER_NAME}"] + list(FILE_TOOLS) + list(extra_allowed or [])
    args += ["--allowedTools", ",".join(allowed)]
    if model:
        args += ["--model", model]
    if permission_mode:
        args += ["--permission-mode", permission_mode]
    return args


# ------------------------------------------------------------------ stream parsing
@dataclass
class Event:
    kind: str   # session | text | tool_use | tool_result | usage | limit | login | result | error | info
    text: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "data": self.data}


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def parse_line(line: str) -> list[Event]:
    """One stdout line -> zero or more app events (robust against unknown/extra fields)."""
    line = line.strip()
    if not line:
        return []
    try:
        d = json.loads(line)
    except ValueError:
        return [Event("info", line[:500])]
    if not isinstance(d, dict):
        return []
    t = d.get("type")
    if t == "system" and d.get("subtype") == "init":
        servers = d.get("mcp_servers") or []
        ours = next((s for s in servers if isinstance(s, dict) and s.get("name") == SERVER_NAME), None)
        return [Event("session", d.get("session_id", ""),
                      {"model": d.get("model", ""), "mcp": (ours or {}).get("status", "missing"),
                       "version": d.get("claude_code_version", "")})]
    if t == "assistant":
        out = []
        for c in (d.get("message") or {}).get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and c.get("text"):
                out.append(Event("text", c["text"]))
            elif c.get("type") == "tool_use":
                out.append(Event("tool_use", str(c.get("name", "")), {"input": c.get("input", {}), "id": c.get("id")}))
        return out
    if t == "user":
        out = []
        for c in (d.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                out.append(Event("tool_result", _content_text(c.get("content"))[:2000],
                                 {"id": c.get("tool_use_id"), "is_error": bool(c.get("is_error"))}))
        return out
    if t == "rate_limit_event":
        info = d.get("rate_limit_info") or {}
        st = str(info.get("status", ""))
        windows = info.get("unifiedWindows") or {}
        util = max([w.get("utilization", 0) for w in windows.values() if isinstance(w, dict)] or [0])
        data = {"status": st, "resets_at": info.get("resetsAt"), "window": info.get("rateLimitType", ""),
                "utilization": util}
        if st == "rejected":
            return [Event("limit", LIMIT_HELP, data)]
        return [Event("usage", st, data)]
    if t == "result":
        text = str(d.get("result", "") or "")
        data = {"is_error": bool(d.get("is_error")), "subtype": d.get("subtype", ""),
                "num_turns": d.get("num_turns"), "duration_ms": d.get("duration_ms"),
                "permission_denials": [str((x or {}).get("tool_name", x)) for x in d.get("permission_denials") or []],
                "session_id": d.get("session_id", "")}
        out = []
        if data["is_error"]:
            if _LIMIT_RE.search(text):
                out.append(Event("limit", LIMIT_HELP, {"detail": text}))
            elif _LOGIN_RE.search(text):
                out.append(Event("login", LOGIN_HELP, {"detail": text}))
        out.append(Event("result", text, data))
        return out
    return []


# ------------------------------------------------------------------ one run
class ClaudeRun:
    """One prompt -> one `claude -p` process. Events are collected for polling by the browser."""

    def __init__(self, args: list[str], prompt: str, cwd: Path, env: dict | None = None,
                 on_event: Callable[[Event], None] | None = None):
        self.args, self.prompt, self.cwd = args, prompt, Path(cwd)
        self.env = env
        self.events: list[Event] = []
        self.stderr_tail: list[str] = []
        self.done = threading.Event()
        self.cancelled = False
        self.returncode: int | None = None
        self.proc: subprocess.Popen | None = None
        self.started = time.time()
        self._on_event = on_event or (lambda e: None)
        self._lock = threading.Lock()

    def _emit(self, ev: Event) -> None:
        with self._lock:
            self.events.append(ev)
        self._on_event(ev)

    def start(self) -> "ClaudeRun":
        try:
            self.proc = subprocess.Popen(self.args, cwd=str(self.cwd), env=self.env, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                         encoding="utf-8", errors="replace", creationflags=_popen_flags(),
                                         # Mac/Linux: own process group, so Stop also ends the MCP server child
                                         start_new_session=not sys.platform.startswith("win"))
        except OSError as exc:
            self._emit(Event("error", f"could not start Claude Code: {exc}\n{INSTALL_HELP}"))
            self.returncode = -1
            self.done.set()
            return self
        threading.Thread(target=self._pump, daemon=True).start()
        return self

    def _pump(self) -> None:
        proc = self.proc
        assert proc is not None
        err_thread = threading.Thread(target=self._read_stderr, daemon=True)
        err_thread.start()
        try:
            proc.stdin.write(self.prompt)
            proc.stdin.close()
        except OSError:
            pass
        for line in proc.stdout:
            for ev in parse_line(line):
                self._emit(ev)
        self.returncode = proc.wait()
        err_thread.join(timeout=2)
        if not any(e.kind == "result" for e in self.events) and not self.cancelled:
            tail = "\n".join(self.stderr_tail[-8:])
            if _NO_SESSION_RE.search(tail):
                self._emit(Event("error", "The saved Claude session no longer exists.", {"no_session": True}))
            elif _LOGIN_RE.search(tail):
                self._emit(Event("login", LOGIN_HELP, {"detail": tail}))
            elif _LIMIT_RE.search(tail):
                self._emit(Event("limit", LIMIT_HELP, {"detail": tail}))
            else:
                self._emit(Event("error", f"Claude Code stopped (exit code {self.returncode}).\n{tail}".strip()))
        self.done.set()

    def _read_stderr(self) -> None:
        for line in self.proc.stderr:
            self.stderr_tail.append(line.rstrip())
            del self.stderr_tail[:-50]

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            if sys.platform.startswith("win"):
                # claude.cmd -> node -> MCP server: end the whole tree, not only cmd.exe
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True,
                               creationflags=_popen_flags())
            else:
                _killpg(self.proc.pid)
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._emit(Event("info", "Cancelled."))

    def wait(self, timeout: float | None = None) -> bool:
        return self.done.wait(timeout)

    def events_after(self, n: int) -> list[dict]:
        with self._lock:
            return [e.to_dict() for e in self.events[n:]]

    def final_text(self) -> str:
        res = [e for e in self.events if e.kind == "result" and not e.data.get("is_error")]
        if res and res[-1].text:
            return res[-1].text
        return "\n\n".join(e.text for e in self.events if e.kind == "text")


def new_session_id() -> str:
    return str(uuid.uuid4())
