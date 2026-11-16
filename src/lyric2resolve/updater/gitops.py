"""Thin, testable wrapper around the git command line (stdlib only)."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROLLBACK_PREFIX = "l2r-rollback/"

AUTH_HINTS = (
    "authentication failed",
    "could not read username",
    "could not read password",
    "repository not found",
    "permission denied",
    "terminal prompts disabled",
    "403",
)

OFFLINE_HINTS = (
    "could not resolve host",
    "failed to connect",
    "network is unreachable",
    "connection timed out",
    "operation timed out",
    "unable to access",
)

AUTH_HELP = (
    "Git could not log in to GitHub.\n"
    "- Easiest: open a terminal in the app folder and run 'git fetch' once; "
    "Git Credential Manager (part of Git for Windows) will ask you to sign in and remember it.\n"
    "- Or create a fine-grained, read-only GitHub token for this repo and use it when Git asks for a password.\n"
    "The app never stores or logs tokens."
)


class GitError(RuntimeError):
    def __init__(self, message: str, stderr: str = "", kind: str = "error"):
        super().__init__(message)
        self.stderr = stderr
        self.kind = kind  # "error" | "auth" | "offline" | "timeout" | "missing"


def classify_error(stderr: str) -> str:
    low = stderr.lower()
    if any(h in low for h in AUTH_HINTS):
        return "auth"
    if any(h in low for h in OFFLINE_HINTS):
        return "offline"
    return "error"


def _no_window_flags() -> int:
    if sys.platform.startswith("win"):
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


@dataclass
class Git:
    repo: Path
    git_exe: str = "git"

    def run(self, *args: str, timeout: float | None = 60, check: bool = True) -> str:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"  # never hang waiting for a password prompt
        env.setdefault("LC_ALL", "C")
        try:
            proc = subprocess.run(
                [self.git_exe, *args],
                cwd=str(self.repo),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
                creationflags=_no_window_flags(),
            )
        except FileNotFoundError as exc:
            raise GitError("Git is not installed or not on PATH.", kind="missing") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"git {args[0]} timed out after {timeout}s", kind="timeout") from exc
        if check and proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            raise GitError(f"git {' '.join(args[:2])} failed: {stderr}", stderr, classify_error(stderr))
        return (proc.stdout or "").strip()

    # --- queries -------------------------------------------------------
    def head(self) -> str:
        return self.run("rev-parse", "HEAD")

    def rev(self, ref: str) -> str:
        return self.run("rev-parse", "--verify", f"{ref}^{{commit}}")

    def has_ref(self, ref: str) -> bool:
        try:
            self.rev(ref)
            return True
        except GitError:
            return False

    def remote_url(self, remote: str) -> str:
        return self.run("remote", "get-url", remote)

    def short_info(self, ref: str = "HEAD") -> tuple[str, str]:
        """(short hash, commit date YYYY-MM-DD)."""
        out = self.run("log", "-1", "--format=%h|%cs", ref)
        short, _, date = out.partition("|")
        return short, date

    def ahead_behind(self, local: str, remote: str) -> tuple[int, int]:
        out = self.run("rev-list", "--left-right", "--count", f"{local}...{remote}")
        ahead, behind = out.split()
        return int(ahead), int(behind)

    def is_dirty(self) -> bool:
        """Modified/staged tracked files. Untracked + ignored files (venv, logs) are fine."""
        return bool(self.run("status", "--porcelain", "--untracked-files=no"))

    def dirty_files(self) -> list[str]:
        out = self.run("status", "--porcelain", "--untracked-files=no")
        return [line[3:] for line in out.splitlines() if line.strip()]

    def commits_between(self, old: str, new: str, limit: int = 50) -> list[str]:
        out = self.run("log", f"--max-count={limit}", "--format=%h %s", f"{old}..{new}")
        return [line for line in out.splitlines() if line.strip()]

    def changed_files(self, old: str, new: str) -> list[str]:
        out = self.run("diff", "--name-status", old, new)
        return [line for line in out.splitlines() if line.strip()]

    def show_file(self, ref: str, path: str) -> str | None:
        try:
            return self.run("show", f"{ref}:{path}")
        except GitError:
            return None

    # --- mutations ----------------------------------------------------
    def fetch(self, remote: str, branch: str, timeout: float) -> None:
        self.run("fetch", "--quiet", "--no-tags", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}", timeout=timeout)

    def merge_ff_only(self, ref: str) -> None:
        self.run("merge", "--ff-only", "--quiet", ref)

    def reset_hard(self, ref: str) -> None:
        self.run("reset", "--hard", "--quiet", ref)

    def tag(self, name: str, ref: str = "HEAD") -> None:
        self.run("tag", "-f", name, ref)

    def delete_tag(self, name: str) -> None:
        self.run("tag", "-d", name, check=False)

    def rollback_tags(self) -> list[str]:
        """Rollback tags, newest first (names embed a sortable timestamp)."""
        out = self.run("tag", "--list", f"{ROLLBACK_PREFIX}*")
        return sorted((t for t in out.splitlines() if t.strip()), reverse=True)
