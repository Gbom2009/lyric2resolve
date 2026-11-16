"""Update check + update/rollback logic. No UI here (see ui.py)."""

from __future__ import annotations

import datetime as _dt
import hashlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import changelog
from .config import UpdaterConfig, UpdaterState, load_state, save_state
from .gitops import AUTH_HELP, ROLLBACK_PREFIX, Git, GitError

# Files whose change means "re-run dependency installation".
REQUIREMENT_GLOBS = ("requirements/*.txt", "pyproject.toml")
# Phase 2 adds this script; when present the dependency step runs it instead of plain pip.
SETUP_UPDATE_SCRIPT = Path("scripts") / "setup_update.py"
# Optional frontend build hook (none yet: the editor frontend has no build step).
FRONTEND_BUILD_SCRIPT = Path("scripts") / "build_frontend.py"

UP_TO_DATE, BEHIND, AHEAD, DIVERGED, OFFLINE, ERROR, NOT_CHECKED = (
    "up_to_date", "behind", "ahead", "diverged", "offline", "error", "not_checked")


# ---------------------------------------------------------------- check
@dataclass
class UpdateStatus:
    state: str
    local: str = ""
    remote: str = ""
    ahead: int = 0
    behind: int = 0
    commits: list[str] = field(default_factory=list)
    changelog_entries: list[changelog.Entry] = field(default_factory=list)
    dirty: bool = False
    message: str = ""

    @property
    def update_available(self) -> bool:
        return self.state in (BEHIND, DIVERGED)


def classify(ahead: int, behind: int) -> str:
    if ahead == 0 and behind == 0:
        return UP_TO_DATE
    if ahead == 0:
        return BEHIND
    if behind == 0:
        return AHEAD
    return DIVERGED


def remote_ref(cfg: UpdaterConfig) -> str:
    return f"{cfg.remote}/{cfg.branch}"


def check_remote_allowed(git: Git, cfg: UpdaterConfig) -> None:
    if not cfg.repo_url:
        return
    actual = git.remote_url(cfg.remote).rstrip("/").removesuffix(".git").lower()
    wanted = cfg.repo_url.rstrip("/").removesuffix(".git").lower()
    if actual != wanted:
        raise GitError(f"Remote '{cfg.remote}' points to {actual}, expected {wanted}. Refusing to fetch.")


def check_for_update(git: Git, cfg: UpdaterConfig, fetch: bool = True) -> UpdateStatus:
    """Never raises: offline/auth problems come back as a status."""
    try:
        local = git.head()
        if fetch:
            check_remote_allowed(git, cfg)
            git.fetch(cfg.remote, cfg.branch, timeout=cfg.fetch_timeout_s)
        remote = git.rev(remote_ref(cfg))
        ahead, behind = git.ahead_behind(local, remote)
    except GitError as exc:
        if exc.kind in ("offline", "timeout"):
            return UpdateStatus(OFFLINE, message="Offline - could not check for updates.")
        msg = AUTH_HELP if exc.kind == "auth" else str(exc)
        return UpdateStatus(ERROR, message=msg)
    status = UpdateStatus(classify(ahead, behind), local, remote, ahead, behind)
    status.dirty = git.is_dirty()
    if status.update_available:
        status.commits = git.commits_between(local, remote)
        status.changelog_entries = changelog.new_entries(
            git.show_file(local, "CHANGELOG.md"), git.show_file(remote, "CHANGELOG.md"))
    if status.state == AHEAD:
        status.message = "This copy has local commits that are not on the server; nothing to update."
    elif status.state == DIVERGED:
        status.message = ("This copy and the server have both changed. Updating will replace this copy "
                          "with the server version (your current version stays available via Roll back).")
    return status


def version_label(git: Git) -> str:
    try:
        short, date = git.short_info()
        return f"{short} ({date})"
    except GitError:
        return "unknown version"


# ------------------------------------------------------- requirements hash
def requirements_hash(repo: Path) -> str:
    h = hashlib.sha256()
    files: list[Path] = []
    for pattern in REQUIREMENT_GLOBS:
        files.extend(repo.glob(pattern))
    for path in sorted(set(files)):
        h.update(path.relative_to(repo).as_posix().encode())
        h.update(b"\0")
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))
        h.update(b"\0")
    return h.hexdigest()


def requirements_changed(repo: Path, state: UpdaterState) -> bool:
    return requirements_hash(repo) != state.requirements_hash


# --------------------------------------------------------- commands
Runner = Callable[[list[str], Path], None]


def default_runner(cmd: list[str], cwd: Path) -> None:
    """Run one allowed command; raise RuntimeError with its output on failure."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=flags)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).strip().splitlines()[-15:])
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{tail}")


def venv_python(repo: Path) -> Path:
    """The project's venv interpreter (console version, used for pip/self-check)."""
    win = repo / ".venv" / "Scripts" / "python.exe"
    nix = repo / ".venv" / "bin" / "python"
    if win.exists():
        return win
    if nix.exists():
        return nix
    return Path(sys.executable)


def dependency_commands(repo: Path, python: Path) -> list[list[str]]:
    if (repo / SETUP_UPDATE_SCRIPT).exists():
        return [[str(python), str(repo / SETUP_UPDATE_SCRIPT), "--update"]]
    return [[str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q",
             "-r", str(repo / "requirements" / "launcher.txt")]]


def self_check_command(repo: Path, python: Path) -> list[str]:
    code = ("import sys; sys.path.insert(0, r'%s'); import lyric2resolve, lyric2resolve.updater.core; "
            "print('ok', lyric2resolve.__version__)") % (repo / "src")
    return [str(python), "-c", code]


# --------------------------------------------------------- update steps
STEP_NAMES = (
    "Fetch the new version",
    "Save a rollback point",
    "Replace the app files",
    "Install changed dependencies (can take a while)",
    "Rebuild the frontend",
    "Quick self-check",
    "Ready to start",
)

Progress = Callable[[int, str, str], None]  # (step index, step name, detail)


@dataclass
class UpdateResult:
    ok: bool
    old: str = ""
    new: str = ""
    rollback_tag: str = ""
    failed_step: str = ""
    error: str = ""
    rolled_back: bool = False
    commits: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    changelog_entries: list[changelog.Entry] = field(default_factory=list)
    deps_installed: bool = False


class DirtyTreeError(RuntimeError):
    pass


def make_rollback_tag(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now()
    return ROLLBACK_PREFIX + now.strftime("%Y%m%d-%H%M%S-%f")


def prune_rollback_tags(git: Git, keep: int) -> None:
    for tag in git.rollback_tags()[keep:]:
        git.delete_tag(tag)


def dirty_message(files: list[str]) -> str:
    shown = "\n".join(f"  {f}" for f in files[:10])
    return ("Update refused: files in the app folder were modified locally:\n"
            f"{shown}\n"
            "Nothing was changed. Undo those edits (e.g. 'git checkout -- .' in the app folder) and try again.")


def run_update(git: Git, cfg: UpdaterConfig, settings_dir: Path | None = None,
               progress: Progress | None = None, runner: Runner | None = None,
               now: _dt.datetime | None = None) -> UpdateResult:
    """Steps 1-6 of the update. Step 7 (launch) is done by the caller.

    On any failure after files were replaced, the code is reset to the rollback
    tag automatically (and dependencies reinstalled if they had changed).
    """
    runner = runner or default_runner
    progress = progress or (lambda i, name, detail: None)
    repo = git.repo
    state = load_state(settings_dir)
    result = UpdateResult(ok=False)
    step = 0

    def report(i: int, detail: str = "") -> None:
        nonlocal step
        step = i
        progress(i, STEP_NAMES[i], detail)

    try:
        if git.is_dirty():
            raise DirtyTreeError(dirty_message(git.dirty_files()))
        result.old = git.head()

        report(0)
        check_remote_allowed(git, cfg)
        git.fetch(cfg.remote, cfg.branch, timeout=max(cfg.fetch_timeout_s, 60))
        target = git.rev(remote_ref(cfg))

        report(1)
        result.rollback_tag = make_rollback_tag(now)
        git.tag(result.rollback_tag, result.old)

        report(2)
        ahead, _behind = git.ahead_behind(result.old, target)
        if ahead == 0:
            git.merge_ff_only(target)
        else:  # diverged/ahead: tree is clean (checked above) -> hard reset
            git.reset_hard(target)
        result.new = git.head()

        report(3)
        python = venv_python(repo)
        if requirements_changed(repo, state):
            for cmd in dependency_commands(repo, python):
                progress(3, STEP_NAMES[3], " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd)))
                runner(cmd, repo)
            result.deps_installed = True
        else:
            progress(3, STEP_NAMES[3], "No dependency changes.")

        report(4)
        if (repo / FRONTEND_BUILD_SCRIPT).exists():
            runner([str(python), str(repo / FRONTEND_BUILD_SCRIPT)], repo)
        else:
            progress(4, STEP_NAMES[4], "No build step needed.")

        report(5)
        runner(self_check_command(repo, python), repo)

        report(6)
        result.ok = True
        result.commits = git.commits_between(result.old, result.new)
        result.changed_files = git.changed_files(result.old, result.new)
        result.changelog_entries = changelog.new_entries(
            git.show_file(result.old, "CHANGELOG.md"), git.show_file(result.new, "CHANGELOG.md"))
        state.requirements_hash = requirements_hash(repo)
        state.last_update_from, state.last_update_to = result.old, result.new
        save_state(state, settings_dir)
        try:
            prune_rollback_tags(git, cfg.keep_rollback_tags)
        except GitError:
            pass
        return result
    except DirtyTreeError as exc:
        result.failed_step, result.error = "Check for local changes", str(exc)
        return result
    except (GitError, RuntimeError, OSError) as exc:
        result.failed_step = STEP_NAMES[step]
        result.error = AUTH_HELP if isinstance(exc, GitError) and exc.kind == "auth" else str(exc)
        if result.old and step >= 2:
            result.rolled_back = _auto_rollback(git, result.old, repo, state, runner, settings_dir)
        return result


def _auto_rollback(git: Git, old: str, repo: Path, state: UpdaterState, runner: Runner,
                   settings_dir: Path | None) -> bool:
    try:
        git.reset_hard(old)
        if requirements_changed(repo, state) and state.requirements_hash:
            for cmd in dependency_commands(repo, venv_python(repo)):
                runner(cmd, repo)
        return git.head() == old
    except (GitError, RuntimeError, OSError):
        return False


# --------------------------------------------------------- manual rollback
@dataclass
class RollbackResult:
    ok: bool
    old: str = ""
    new: str = ""
    tag: str = ""
    error: str = ""


def rollback_target(git: Git) -> str | None:
    """Newest rollback tag pointing at a commit different from HEAD."""
    head = git.head()
    for tag in git.rollback_tags():
        try:
            if git.rev(tag) != head:
                return tag
        except GitError:
            continue
    return None


def rollback(git: Git, settings_dir: Path | None = None, runner: Runner | None = None) -> RollbackResult:
    runner = runner or default_runner
    try:
        if git.is_dirty():
            return RollbackResult(False, error=dirty_message(git.dirty_files()).replace("Update", "Roll back"))
        tag = rollback_target(git)
        if not tag:
            return RollbackResult(False, error="There is no previous version to roll back to yet.")
        old = git.head()
        target = git.rev(tag)
        # No new tag here: the server version is still offered as an update, which is the "undo".
        git.reset_hard(target)
        state = load_state(settings_dir)
        if requirements_changed(git.repo, state):
            for cmd in dependency_commands(git.repo, venv_python(git.repo)):
                runner(cmd, git.repo)
            state.requirements_hash = requirements_hash(git.repo)
            save_state(state, settings_dir)
        return RollbackResult(True, old=old, new=target, tag=tag)
    except (GitError, RuntimeError, OSError) as exc:
        return RollbackResult(False, error=str(exc))


def changed_files_summary(lines: list[str], limit: int = 15) -> str:
    labels = {"A": "added", "M": "changed", "D": "removed", "R": "renamed"}
    out = []
    for line in lines[:limit]:
        code, _, name = line.partition("\t")
        out.append(f"  {labels.get(code[:1], code)}: {name.replace(chr(9), ' -> ')}")
    if len(lines) > limit:
        out.append(f"  ... and {len(lines) - limit} more files")
    return "\n".join(out) or "  (no file changes)"
