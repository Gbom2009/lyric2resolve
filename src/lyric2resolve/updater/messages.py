"""User-facing texts for the launcher/updater windows (pure functions, unit-tested)."""

from __future__ import annotations

from . import changelog
from .core import AHEAD, DIVERGED, ERROR, NOT_CHECKED, OFFLINE, UP_TO_DATE, RollbackResult, UpdateResult, UpdateStatus, changed_files_summary

NO_APP_YET = "lyric2resolve"


def status_line(status: UpdateStatus | None, version: str) -> str:
    if status is None:
        return f"{NO_APP_YET} - version {version}. Checking for updates..."
    if status.state == NOT_CHECKED:
        return f"{NO_APP_YET} - version {version}. (Update check at launch is off - click Check now.)"
    if status.state == UP_TO_DATE:
        return f"{NO_APP_YET} - version {version}, up to date"
    if status.state == OFFLINE:
        return f"{NO_APP_YET} - version {version}. {status.message}"
    if status.state == AHEAD:
        return f"{NO_APP_YET} - version {version}. {status.message}"
    if status.state == ERROR:
        return f"{NO_APP_YET} - version {version}. Update check failed:\n{status.message}"
    return f"{NO_APP_YET} - version {version}. An update is available."


def update_available_text(status: UpdateStatus) -> str:
    parts = ["WHAT'S NEW (changelog)", "", changelog.render_entries(status.changelog_entries), "",
             f"COMMITS ({status.behind} new)", ""]
    parts += [f"  {c}" for c in status.commits] or ["  (none)"]
    if status.state == DIVERGED:
        parts += ["", "NOTE: " + status.message]
    if status.dirty:
        parts += ["", "WARNING: files in the app folder were modified locally. The update will refuse "
                  "until those edits are undone."]
    return "\n".join(parts)


def whats_changed_text(result: UpdateResult) -> str:
    parts = ["WHAT CHANGED", "", changelog.render_entries(result.changelog_entries), "",
             "COMMITS", ""]
    parts += [f"  {c}" for c in result.commits] or ["  (none)"]
    parts += ["", "FILES", changed_files_summary(result.changed_files)]
    if result.deps_installed:
        parts += ["", "Dependencies were updated."]
    parts += ["", f"Previous version saved as rollback point {result.rollback_tag}."]
    return "\n".join(parts)


def failure_text(result: UpdateResult) -> str:
    parts = [f"The update failed at step: {result.failed_step}", "", result.error]
    if result.rolled_back:
        parts += ["", "The app was automatically restored to the previous version. Nothing is lost."]
    elif result.old and result.failed_step not in ("Check for local changes",):
        parts += ["", "Automatic restore did not complete. Use 'Roll back' in the launcher, or run "
                  f"'git reset --hard {result.old[:10]}' in the app folder."]
    return "\n".join(parts)


def rollback_text(result: RollbackResult) -> str:
    if result.ok:
        return (f"Rolled back from {result.old[:7]} to {result.new[:7]} ({result.tag}).\n"
                "The newer version will be offered again as an update.")
    return f"Roll back not possible:\n{result.error}"


APP_LINES = {
    "idle": "Editor: not running.",
    "checking": "Editor: checking the installation...",
    "starting": "Editor: starting...",
    "running": "Editor running at {url} (opened in your browser).",
    "needs_setup": ("Editor: the full setup has not been run yet ({detail}).\n"
                    "Click 'Run setup' (installs PyTorch/Whisper/audio libraries, takes a while), "
                    "then 'Start editor'."),
    "failed": "Editor could not start. {detail}",
}


def app_line(state: str, url: str = "", detail: str = "") -> str:
    return APP_LINES.get(state, state).format(url=url, detail=detail or "unknown error")
