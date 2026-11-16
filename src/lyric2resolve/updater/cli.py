"""Command line for the launcher/updater.

    launch [--skip-check] [--login-check]   open the launcher window (default)
    apply-update --repo PATH                run the update UI (used from the temp copy)
    check-update                            print update status
    update [--yes]                          update from the console
    rollback                                go back to the previous version
    login-check on|off                      check for updates at Windows login
    version                                 print the installed version
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lyric2resolve import paths

from . import changelog, core, messages
from .config import load_config, save_config
from .gitops import Git


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lyric2resolve")
    p.add_argument("--repo", type=Path, default=None, help="app folder (git clone); default: this code's folder")
    sub = p.add_subparsers(dest="cmd")
    launch = sub.add_parser("launch")
    launch.add_argument("--skip-check", action="store_true")
    launch.add_argument("--login-check", action="store_true")
    apply = sub.add_parser("apply-update")
    apply.add_argument("--repo", dest="apply_repo", type=Path, required=True)
    sub.add_parser("check-update")
    upd = sub.add_parser("update")
    upd.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    sub.add_parser("rollback")
    lc = sub.add_parser("login-check")
    lc.add_argument("value", choices=["on", "off"])
    sub.add_parser("version")
    return p


def _print_progress(i: int, name: str, detail: str) -> None:
    print(f"[{i + 1}/{len(core.STEP_NAMES)}] {name}" + (f" - {detail}" if detail else ""))


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    repo = (args.repo or paths.code_dir()).resolve()
    cmd = args.cmd or "launch"
    git = Git(repo)
    cfg = load_config()

    if cmd == "launch":
        from .ui import run_launcher

        return run_launcher(repo, getattr(args, "skip_check", False), getattr(args, "login_check", False))
    if cmd == "apply-update":
        from .ui import run_apply

        return run_apply(args.apply_repo.resolve())
    if cmd == "version":
        print(core.version_label(git))
        return 0
    if cmd == "check-update":
        status = core.check_for_update(git, cfg)
        print(messages.status_line(status, core.version_label(git)))
        if status.update_available:
            print(messages.update_available_text(status))
        return 0 if status.state != core.ERROR else 1
    if cmd == "update":
        status = core.check_for_update(git, cfg)
        if not status.update_available:
            print(messages.status_line(status, core.version_label(git)))
            return 0
        print(messages.update_available_text(status))
        if not args.yes and input("Update now? [y/N] ").strip().lower() not in ("y", "yes", "j", "ja"):
            print("Later.")
            return 0
        result = core.run_update(git, cfg, progress=_print_progress)
        print(messages.whats_changed_text(result) if result.ok else messages.failure_text(result))
        return 0 if result.ok else 1
    if cmd == "rollback":
        result = core.rollback(git)
        print(messages.rollback_text(result))
        return 0 if result.ok else 1
    if cmd == "login-check":
        from .selfcopy import set_login_check

        cfg.check_at_login = args.value == "on"
        save_config(cfg)
        target = set_login_check(cfg.check_at_login, repo)
        print(f"Check at login: {args.value} ({target})")
        return 0
    return 2


__all__ = ["main", "build_parser", "changelog"]
