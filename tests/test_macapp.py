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
