"""Build lyric2resolve.app (macOS) around the git clone. Stdlib only (runs from install.command).

The app is a small bundle: Info.plist + a start script that runs the launcher with the clone's .venv. The code keeps
living in the git clone, so the launcher's Update now (git) keeps working; the .app never needs rebuilding unless the
clone moves (run install.command again then).

    python -m lyric2resolve.macapp --repo <clone> [--dest /Applications] [--icon assets/app_icon.png]
"""

from __future__ import annotations

import argparse
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "lyric2resolve"
BUNDLE_ID = "app.lyric2resolve.launcher"


def info_plist(version: str = "1.0") -> dict:
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "CFBundleIconFile": "AppIcon",
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.video",
        "NSHighResolutionCapable": True,
        # the executable is a shell script: tell macOS to run it natively on M chips, never under Rosetta
        "LSArchitecturePriority": ["arm64", "x86_64"],
        "LSRequiresNativeExecution": True,
        "NSMicrophoneUsageDescription": "Not used; lyric2resolve only reads your audio files.",
    }


def start_script(repo: Path) -> str:
    """Contents/MacOS/lyric2resolve: runs the launcher with the clone's .venv (logs next to the data folder)."""
    py = shlex.quote(str(repo / ".venv" / "bin" / "python3"))
    launcher = shlex.quote(str(repo / "launcher.pyw"))
    return f"""#!/bin/bash
# lyric2resolve.app start script (made by install.command). The app code lives in the git clone below.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd {shlex.quote(str(repo))} || exit 1
if [ ! -x {py} ]; then
  osascript -e 'display alert "lyric2resolve" message "The app folder moved or its .venv is missing. Run install.command in the lyric2resolve folder again."'
  exit 1
fi
# Apple Silicon: always start the (universal) Python as arm64 - the packages from setup are arm64
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && [ -x /usr/bin/arch ]; then
  export L2R_NATIVE_ARM64=1
  exec /usr/bin/arch -arm64 {py} {launcher} "$@"
fi
exec {py} {launcher} "$@"
"""


def build_icns(png: Path, out: Path, run=subprocess.run) -> bool:
    """PNG -> .icns with macOS's own sips + iconutil (only available on a Mac)."""
    if not png.is_file() or not shutil.which("iconutil") or not shutil.which("sips"):
        return False
    iconset = out.with_suffix(".iconset")
    iconset.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 64, 128, 256, 512):
        for scale in (1, 2):
            px = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            run(["sips", "-z", str(px), str(px), str(png), "--out", str(iconset / name)], capture_output=True)
    res = run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], capture_output=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return getattr(res, "returncode", 1) == 0 and out.exists()


def build_app(repo: Path, dest: Path, icon_png: Path | None = None, version: str = "1.0") -> Path:
    repo, dest = Path(repo).resolve(), Path(dest)
    app = dest / f"{APP_NAME}.app"
    if app.exists():
        shutil.rmtree(app)
    macos, res = app / "Contents" / "MacOS", app / "Contents" / "Resources"
    macos.mkdir(parents=True)
    res.mkdir(parents=True)
    with open(app / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump(info_plist(version), f)
    exe = macos / APP_NAME
    exe.write_text(start_script(repo), encoding="utf-8")
    exe.chmod(0o755)
    (app / "Contents" / "PkgInfo").write_text("APPL????", encoding="ascii")
    if icon_png:
        build_icns(Path(icon_png), res / "AppIcon.icns")
    return app


def default_dest() -> Path:
    """/Applications when writable (admin users), else ~/Applications."""
    apps = Path("/Applications")
    if apps.is_dir() and os.access(apps, os.W_OK):
        return apps
    home_apps = Path.home() / "Applications"
    home_apps.mkdir(exist_ok=True)
    return home_apps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lyric2resolve.macapp")
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--dest", type=Path)
    ap.add_argument("--icon", type=Path)
    a = ap.parse_args(argv)
    app = build_app(a.repo, a.dest or default_dest(), a.icon or (a.repo / "assets" / "app_icon.png"))
    print(app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
