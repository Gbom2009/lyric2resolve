# Changelog

Newest first. Each entry says in plain language what is new, what changed and what to test.
The launcher shows the new entries when an update is available and after updating.

## Phase 1 — Launcher + auto-updater (first install)
**New**
- The lyric2resolve launcher: a small window you start from the Desktop/Start-menu shortcut (no console window).
- Automatic update check at every start. When there is a new version you see this changelog and the list of changes, and choose "Update now" or "Later". Nothing updates without your click.
- "Update now" shows a progress bar with steps (fetch, save rollback point, replace files, install dependencies if needed, self-check). If anything fails, the app restores the previous version by itself.
- "Roll back" returns to the previous version; "Open data folder" opens where your projects/settings will live (`%LOCALAPPDATA%\lyric2resolve`, never touched by updates).
- `install.bat` for the first-time install (see INSTALL.md).

**What to test**
- First-time install via INSTALL.md, then the Phase 1 TEST CHECKLIST in PHASES.md.
- There is no editor yet: the launcher says "No app interface yet - version …, up to date".
