# PROGRESS.md — lyric2resolve

MODE: gated

## Phase status
| # | Phase | Status | Branch / PR |
|---|-------|--------|-------------|
| 0 | Planning docs | merged (initial commit on main) | main |
| 1 | Skeleton + launcher/updater | PR open (draft until CI green) | phase-01-launcher-updater / PR #1 |
| 2 | Setup script + verify_local + settings | planned | |
| 3 | Audio inputs / alignment / instrumental | planned | |
| 4 | Transcription + project JSON | planned | |
| 5 | Music analysis + gaps + sanity | planned | |
| 6 | Editor backend API | planned | |
| 7 | Editor frontend 1 | planned | |
| 8 | Editor frontend 2 | planned | |
| 9 | Styling + fonts | planned | |
| 10 | FCPXML export | planned | |
| 11 | Resolve script + SRT/CSV/EDL | planned | |
| 12 | Karaoke | planned | |
| 13 | Texture sync + browser | planned | |
| 14 | Blender generator | planned | |
| 15 | Headless render + DJ mux | planned | |
| 16 | Prompt generator + templates | planned | |
| 17 | Claude link | planned | |
| 18 | Settings UI / branding / batch / update banner | planned | |
| 19 | Full test pass + docs | planned | |

Statuses: planned / in progress / PR open / merged / tested-OK / needs fixes / waiting for user

## CURRENT STEP LOG
Phase 1 (branch `phase-01-launcher-updater`, PR #1):
- [x] package skeleton + paths.py (data folder)
- [x] updater logic: `updater/{gitops,changelog,config,core,messages,selfcopy,cli}.py`
- [x] tests/test_updater.py (temp bare repo as fake remote; UI smoke tests run under xvfb / Windows runner)
- [x] Tkinter UI `updater/ui.py` + `launcher.pyw`
- [x] install.ps1/install.bat + INSTALL.md + shortcuts
- [x] CI (Linux 3.11/3.12 + Windows incl. `install.ps1 -NoShortcuts` smoke test), CHANGELOG, VERIFY_LOCAL.md
- [ ] CI green → mark PR #1 ready → GATED stop, wait for user's Phase 1 test
Next: if CI fails, read job logs (GitHub MCP `get_job_logs`) and fix on this branch.

## Decisions
- Python package in `src/lyric2resolve/` (src layout), installed editable into the venv → clean imports, tests run against the package.
- User data lives OUTSIDE the clone: `%LOCALAPPDATA%\lyric2resolve` (Windows) / `~/.local/share/lyric2resolve` (else), override `LYRIC2RESOLVE_DATA`. Assets (fonts/textures) therefore live in `<data>/assets/...`; the repo only holds manifests/curation lists. Reason: the updater hard-resets code and must never touch user data.
- Launcher + updater are stdlib only (Tkinter, subprocess git) so they run before heavy deps exist.
- Updater self-update: launcher copies the `updater` package to a temp dir and runs it from there as a separate process (`python -m` with PYTHONPATH=temp), then exits.
- Update strategy: fetch → tag `l2r-rollback-<timestamp>` (+ moving `l2r-rollback-latest`) → `git merge --ff-only origin/<branch>`; if not fast-forward but tree clean → `git reset --hard origin/<branch>`; dirty tree → refuse.
- Frontend: vanilla JS, no build step (keeps the updater's "rebuild frontend" step a no-op and avoids Node on the PC).
- Branching: phase branches `phase-NN-slug` as in the spec (pushing them works). The harness-designated `claude/...` branch of session 1 is unused.
- CI runs on PRs + pushes to main only (no duplicate runs); a Windows runner also runs the tests and `install.ps1 -NoShortcuts`.
- Rollback tags `l2r-rollback/<timestamp>` are local-only (never pushed); 5 kept. Manual roll back steps back one version at a time; the newer version is then offered again as an update (= undo).
- Dependency step runs only when the hash of `requirements/*.txt` + `pyproject.toml` changes (state in `<data>/settings/updater_state.json`); from Phase 2 it calls `scripts/setup_update.py --update` if present.

## Open issues
- (none yet)

## User test feedback per phase
- (none yet)

## Pending VERIFY_LOCAL items
- Phase 1: install, shortcut, update flow, self-update, rollback on Windows (see VERIFY_LOCAL.md).

## Local verification reports (paste below)
- (none yet)
