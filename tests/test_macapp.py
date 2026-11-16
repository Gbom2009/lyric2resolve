"""Mac phase 2: lyric2resolve.app bundle + install.command + setup on Mac."""

import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from lyric2resolve import macapp

REPO = Path(__file__).resolve().parents[1]


def test_build_app_bundle(tmp_path):
    repo = tmp_path / "My Apps" / "lyric2resolve"   # spaces in the path
    repo.mkdir(parents=True)
    app = macapp.build_app(repo, tmp_path / "Applications", REPO / "assets" / "app_icon.png")
    assert app.name == "lyric2resolve.app"
    with open(app / "Contents" / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    assert info["CFBundleExecutable"] == "lyric2resolve" and info["CFBundleIdentifier"] == macapp.BUNDLE_ID
    exe = app / "Contents" / "MacOS" / "lyric2resolve"
    text = exe.read_text()
    assert text.startswith("#!/bin/bash") and "'" + str(repo.resolve() / ".venv" / "bin" / "python3") + "'" in text
    assert "launcher.pyw" in text and "/opt/homebrew/bin" in text
    if os.name != "nt":
        assert exe.stat().st_mode & stat.S_IXUSR
    again = macapp.build_app(repo, tmp_path / "Applications")  # rebuilding replaces the old app
    assert again == app and (app / "Contents" / "PkgInfo").read_text() == "APPL????"


def test_icon_needs_macos_tools(tmp_path):
    out = tmp_path / "AppIcon.icns"
    if sys.platform != "darwin":
        assert macapp.build_icns(REPO / "assets" / "app_icon.png", out) is False
    assert macapp.build_icns(tmp_path / "missing.png", out) is False


def test_setup_command_opens_terminal_on_mac(monkeypatch, tmp_path):
    from lyric2resolve.updater import appctl

    monkeypatch.setattr(appctl.sys, "platform", "darwin")
    assert appctl.setup_command(tmp_path) == ["open", "-a", "Terminal", str(tmp_path / "setup_mac.command")]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="bash scripts")
def test_mac_scripts_are_valid_bash_and_executable():
    for name in ("install.command", "setup_mac.command"):
        subprocess.run(["bash", "-n", str(REPO / name)], check=True)
        mode = subprocess.run(["git", "-C", str(REPO), "ls-files", "-s", name], capture_output=True,
                              text=True).stdout.split()
        if mode:  # committed: must keep the executable bit so Finder can run it with a double-click
            assert mode[0] == "100755", name


# ------------------------------------------------------------------ fix: app started under Rosetta (user test, M1 Air)

def test_app_bundle_forces_native_arm64(tmp_path):
    from lyric2resolve import macapp

    plist = macapp.info_plist()
    assert plist["LSArchitecturePriority"][0] == "arm64" and plist["LSRequiresNativeExecution"] is True
    script = macapp.start_script(tmp_path / "repo")
    assert "hw.optional.arm64" in script and "exec /usr/bin/arch -arm64" in script
    assert script.index("arch -arm64") < script.rindex('exec ')  # native start comes before the plain fallback


def test_launcher_relaunches_natively_under_rosetta():
    from lyric2resolve import paths

    argv = paths.native_relaunch_argv(["/r/launcher.pyw", "--x"], env={}, translated=True, executable="/r/py")
    if not __import__("pathlib").Path("/usr/bin/arch").exists():
        assert argv is None  # not a Mac
        return
    assert argv == ["/usr/bin/arch", "-arm64", "/r/py", "/r/launcher.pyw", "--x"]
    assert paths.native_relaunch_argv(["l"], env={paths.NATIVE_ENV: "1"}, translated=True) is None  # never loops
    assert paths.native_relaunch_argv(["l"], env={}, translated=False) is None


def test_native_relaunch_off_mac(monkeypatch):
    from lyric2resolve import paths

    monkeypatch.setattr(paths.sys, "platform", "linux")
    assert paths.rosetta_translated() is False


def test_arch_mismatch_message():
    from lyric2resolve.updater import messages

    detail = ("ImportError: dlopen(.../_pydantic_core.cpython-312-darwin.so, 0x0002): ... (mach-o file, but is an "
              "incompatible architecture (have 'arm64', need 'x86_64'))")
    line = messages.app_line("needs_setup", detail=detail)
    assert "Rosetta" in line and "Run setup" not in line
    assert "Run setup" in messages.app_line("needs_setup", detail="No module named fastapi")


def test_ensure_native_execs_only_under_rosetta(monkeypatch):
    from lyric2resolve import paths

    calls = []
    monkeypatch.delenv(paths.NATIVE_ENV, raising=False)
    monkeypatch.setattr(paths, "native_relaunch_argv", lambda argv: None)
    paths.ensure_native(["x"], execv=lambda *a: calls.append(a))
    assert calls == []
    monkeypatch.setattr(paths, "native_relaunch_argv", lambda argv: ["/usr/bin/arch", "-arm64", "py", *argv])
    paths.ensure_native(["setup_update.py", "--update"], execv=lambda *a: calls.append(a))
    assert calls == [("/usr/bin/arch", ["/usr/bin/arch", "-arm64", "py", "setup_update.py", "--update"])]
    assert __import__("os").environ[paths.NATIVE_ENV] == "1"  # the restarted process never restarts again
    monkeypatch.delenv(paths.NATIVE_ENV)


def test_setup_update_restarts_natively_first():
    src = (__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "setup_update.py").read_text()
    body = src[src.index("def main("):]
    assert body.index("ensure_native(") < body.index("ap.parse_args") < body.index("plan_setup(")  # before any pip
