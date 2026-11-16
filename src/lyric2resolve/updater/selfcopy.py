"""Self-update support + optional 'check at Windows login' entry.

Windows cannot overwrite files that are in use, so the launcher copies the
updater code to a temporary folder and starts the update from that copy as a
separate process, then exits. The copy only contains stdlib code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE_FILES = ("__init__.py", "paths.py")


def copy_updater(src_pkg: Path, dest_root: Path | None = None) -> Path:
    """Copy lyric2resolve/{__init__,paths}.py + lyric2resolve/updater/ to a temp root.

    Returns the root to put on PYTHONPATH.
    """
    dest_root = Path(dest_root or tempfile.mkdtemp(prefix="l2r-updater-"))
    pkg = dest_root / "lyric2resolve"
    (pkg / "updater").mkdir(parents=True, exist_ok=True)
    for name in PACKAGE_FILES:
        shutil.copy2(src_pkg / name, pkg / name)
    for py in (src_pkg / "updater").glob("*.py"):
        shutil.copy2(py, pkg / "updater" / py.name)
    return dest_root


def gui_python(python: Path | None = None) -> Path:
    """pythonw.exe next to python.exe on Windows (no console window)."""
    python = Path(python or sys.executable)
    if sys.platform.startswith("win"):
        candidate = python.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
    return python


def apply_command(temp_root: Path, repo: Path, python: Path | None = None) -> tuple[list[str], dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(temp_root)
    cmd = [str(gui_python(python)), "-m", "lyric2resolve.updater", "apply-update", "--repo", str(repo)]
    return cmd, env


def start_apply_process(src_pkg: Path, repo: Path) -> subprocess.Popen:
    temp_root = copy_updater(src_pkg)
    cmd, env = apply_command(temp_root, repo)
    flags = 0
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # cwd = temp root, so nothing in the code folder is held open by this process.
    return subprocess.Popen(cmd, cwd=str(temp_root), env=env, creationflags=flags, close_fds=True)


def launch_command(repo: Path, python: Path | None = None, *extra: str) -> list[str]:
    return [str(gui_python(python)), str(repo / "launcher.pyw"), *extra]


def start_launcher(repo: Path, *extra: str) -> subprocess.Popen:
    from .core import venv_python

    return subprocess.Popen(launch_command(repo, venv_python(repo), *extra), cwd=str(repo), close_fds=True)


# ------------------------------------------------------------- login entry
STARTUP_FILE = "lyric2resolve-update-check.vbs"


def startup_folder(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    appdata = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_script(pythonw: Path, launcher: Path) -> str:
    # The launcher with --login-check stays invisible unless an update is available.
    return (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.Run """{pythonw}"" ""{launcher}"" --login-check", 0, False\r\n'
    )


def set_login_check(enabled: bool, repo: Path, folder: Path | None = None) -> Path:
    from .core import venv_python

    folder = folder or startup_folder()
    target = folder / STARTUP_FILE
    if enabled:
        folder.mkdir(parents=True, exist_ok=True)
        target.write_text(startup_script(gui_python(venv_python(repo)), repo / "launcher.pyw"), encoding="utf-8")
    elif target.exists():
        target.unlink()
    return target
