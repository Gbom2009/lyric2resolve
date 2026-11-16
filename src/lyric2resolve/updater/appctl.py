"""Start/stop the app (editor server) from the launcher. Stdlib only.

The launcher runs the editor as a child process (no console window), waits until
its port answers, opens the browser, and stops it when the launcher closes.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .core import venv_python

DEPS_CHECK = "import fastapi, uvicorn, numpy, lyric2resolve.editor.app"


def _flags(console: bool = False) -> int:
    if not sys.platform.startswith("win"):
        return 0
    if console:
        return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


UPDATE_REQUEST = "update_request.json"
LAUNCHER_ENV = "L2R_LAUNCHER"  # set for the editor when the launcher started it


def app_env(repo: Path) -> dict:
    env = dict(os.environ)
    env[LAUNCHER_ENV] = "1"
    src = str(repo / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def deps_ready(repo: Path, python: Path | None = None, timeout: float = 60) -> tuple[bool, str]:
    """True when the full setup (Phase 2) has been run, i.e. the editor can start."""
    python = python or venv_python(repo)
    try:
        proc = subprocess.run([str(python), "-c", DEPS_CHECK], cwd=str(repo), env=app_env(repo),
                              capture_output=True, text=True, timeout=timeout, creationflags=_flags())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    last = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
    return False, last[0]


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(preferred: int, host: str = "127.0.0.1", tries: int = 20) -> int:
    for p in range(preferred, preferred + tries):
        if port_free(p, host):
            return p
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 30.0,
                  alive=lambda: True) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not alive():
            return False
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def editor_command(repo: Path, port: int, host: str = "127.0.0.1", python: Path | None = None) -> list[str]:
    python = python or venv_python(repo)
    return [str(python), "-m", "lyric2resolve", "editor", "--no-browser", "--host", host, "--port", str(port)]


def start_editor(repo: Path, port: int, log_file: Path, host: str = "127.0.0.1") -> subprocess.Popen:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_file, "a", encoding="utf-8")  # noqa: SIM115 - handed to the child process
    log.write(f"\n--- editor start {time.strftime('%Y-%m-%d %H:%M:%S')} port {port} ---\n")
    log.flush()
    return subprocess.Popen(editor_command(repo, port, host), cwd=str(repo), env=app_env(repo),
                            stdout=log, stderr=subprocess.STDOUT, creationflags=_flags())


def stop(proc: subprocess.Popen | None, timeout: float = 5.0) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


def setup_command(repo: Path) -> list[str]:
    """Run the full setup in a visible console window (it prints progress)."""
    if sys.platform.startswith("win"):
        return ["cmd", "/c", str(repo / "setup_windows.bat")]
    if sys.platform == "darwin":  # visible progress in a Terminal window
        return ["open", "-a", "Terminal", str(repo / "setup_mac.command")]
    return [str(venv_python(repo)), str(repo / "scripts" / "setup_update.py"), "--full"]


def run_setup(repo: Path) -> subprocess.Popen:
    return subprocess.Popen(setup_command(repo), cwd=str(repo), creationflags=_flags(console=True))


# ------------------------------------------------------------------ update request from the browser banner
def request_update(settings_dir: Path) -> Path:
    """The editor writes this when you click 'Update now' in the browser; the launcher picks it up."""
    import json

    path = Path(settings_dir) / UPDATE_REQUEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"time": time.time()}), encoding="utf-8")
    return path


def take_update_request(settings_dir: Path, max_age_s: float = 600) -> bool:
    """True once per fresh request (the file is removed). Stale requests are ignored and removed."""
    path = Path(settings_dir) / UPDATE_REQUEST
    try:
        age = time.time() - path.stat().st_mtime
        path.unlink()
    except OSError:
        return False
    return age <= max_age_s

