"""Folder conventions.

Code folder = the git clone (replaced by updates).
Data folder = everything that belongs to the user (projects, assets, settings,
caches, models, logs, renders). It lives OUTSIDE the code folder so the updater
can never touch it.

Windows: %LOCALAPPDATA%\\lyric2resolve
         (Python from the Microsoft Store: %USERPROFILE%\\lyric2resolve-data, see store_python())
Other:   $XDG_DATA_HOME/lyric2resolve or ~/.local/share/lyric2resolve
Override: environment variable LYRIC2RESOLVE_DATA
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "lyric2resolve"
DATA_ENV = "LYRIC2RESOLVE_DATA"

SUBDIRS = (
    "settings",
    "projects",
    "assets/fonts/custom",
    "assets/textures/custom",
    "cache",
    "models",
    "logs",
    "renders",
)


def code_dir() -> Path:
    """Root of the git clone (folder containing pyproject.toml)."""
    return Path(__file__).resolve().parents[2]


STORE_DATA_NAME = "lyric2resolve-data"


def store_python(prefix: str | None = None) -> bool:
    """True for Python from the Microsoft Store. Its files written under AppData (and TEMP) are silently
    redirected to a private package folder: Python still sees them, but ffmpeg, Blender, Resolve and Explorer
    do not ('Error opening input: No such file or directory'). See docs.python.org, 'Known issues' of the
    Microsoft Store package."""
    p = (prefix if prefix is not None else getattr(sys, "base_prefix", sys.prefix)).replace("/", "\\").lower()
    return "\\windowsapps\\" in p or "pythonsoftwarefoundation.python" in p


def legacy_store_dir(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def data_dir(env: dict[str, str] | None = None, platform: str | None = None, prefix: str | None = None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    override = env.get(DATA_ENV)
    if override:
        return Path(override).expanduser()
    if platform.startswith("win"):
        if store_python(prefix):  # outside AppData, so other programs see the same files
            home = env.get("USERPROFILE") or str(Path.home())
            return Path(home) / STORE_DATA_NAME
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def ensure_data_dir(root: Path | None = None) -> Path:
    default = root is None
    root = data_dir() if root is None else root
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    if default and sys.platform.startswith("win") and store_python() and not os.environ.get(DATA_ENV):
        migrate_store_data(legacy_store_dir(), root)
        use_real_temp(root)
    return root


MIGRATED_MARKER = ".migrated-from-appdata"


def migrate_store_data(old: Path, new: Path, parts: tuple[str, ...] = ("settings", "projects")) -> list[str]:
    """Once: copy settings + projects that Store Python wrote into the (redirected) AppData folder.
    Caches and models are not copied (big; they are re-created/downloaded when needed)."""
    import shutil

    marker = new / MIGRATED_MARKER
    if marker.exists() or not old.exists() or old.resolve() == new.resolve():
        return []
    copied = []
    for part in parts:
        src = old / part
        if src.is_dir():
            shutil.copytree(src, new / part, dirs_exist_ok=True)
            copied.append(part)
    marker.write_text("copied: " + ", ".join(copied) + "\n", encoding="utf-8")
    return copied


def use_real_temp(root: Path) -> Path:
    """TEMP is redirected for Store Python too: use a temp folder that every program can see."""
    import tempfile

    tmp = root / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(tmp)
    os.environ["TMP"] = os.environ["TEMP"] = str(tmp)
    return tmp


def settings_dir() -> Path:
    return data_dir() / "settings"


def logs_dir() -> Path:
    return data_dir() / "logs"


def atomic_write_text(path: Path, text: str) -> Path:
    """Write via a unique temp file + rename, so a crash never leaves half a file and two saves at the same
    time (e.g. quick changes on the Settings page) never fight over one temp file."""
    import uuid

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        for attempt in range(5):  # Windows: the target can be briefly locked by a reader (antivirus, editor)
            try:
                tmp.replace(path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                import time

                time.sleep(0.05 * (attempt + 1))
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return path


NATIVE_ENV = "L2R_NATIVE_ARM64"  # set after the launcher restarted itself natively (never loops)


def rosetta_translated() -> bool:
    """macOS: True when this process runs as Intel code under Rosetta on an Apple Silicon Mac."""
    if sys.platform != "darwin":
        return False
    try:
        import ctypes

        libc = ctypes.CDLL(None)
        val, size = ctypes.c_int(0), ctypes.c_size_t(ctypes.sizeof(ctypes.c_int))
        if libc.sysctlbyname(b"sysctl.proc_translated", ctypes.byref(val), ctypes.byref(size), None, 0) != 0:
            return False
        return val.value == 1
    except (OSError, AttributeError):
        return False


def native_relaunch_argv(argv: list[str], env: dict | None = None, translated: bool | None = None,
                         executable: str | None = None) -> list[str] | None:
    """Apple Silicon: a Finder/Dock start can run the app (and the universal python.org Python) under Rosetta as
    Intel code, while setup installed the arm64 packages -> 'incompatible architecture'. Returns the command to
    restart natively (`arch -arm64 python ...`), or None when nothing needs to happen."""
    env = os.environ if env is None else env
    if env.get(NATIVE_ENV) == "1" or not Path("/usr/bin/arch").exists():
        return None
    if not (rosetta_translated() if translated is None else translated):
        return None
    return ["/usr/bin/arch", "-arm64", executable or sys.executable, *argv]


def fix_mac_path(env: dict | None = None, platform: str | None = None) -> list[str]:
    """macOS apps started from Finder/the Dock get a minimal PATH (no Homebrew): add the usual tool folders so
    ffmpeg, git, blender and claude are found by every subprocess. Returns the folders added."""
    env = os.environ if env is None else env
    if (platform or sys.platform) != "darwin":
        return []
    have = env.get("PATH", "").split(os.pathsep)
    home = env.get("HOME") or str(Path.home())
    want = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", f"{home}/.local/bin"]
    add = [d for d in want if d not in have and Path(d).is_dir()]
    if add:
        env["PATH"] = os.pathsep.join(add + [x for x in have if x])
    return add

