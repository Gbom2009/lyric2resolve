# PROGRESS.md — lyric2resolve

MODE: continuous (set 2026-11-16 by user; branch `continuous-2026-11-16`, one PR)

## Phase status
| # | Phase | Status | Branch / PR |
|---|-------|--------|-------------|
| 0 | Planning docs | merged (initial commit on main) | main |
| 1 | Skeleton + launcher/updater | merged (user test pending) | PR #1 |
| 2 | Setup script + verify_local + settings | in progress | continuous-2026-11-16 |
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
Continuous mode, branch `continuous-2026-11-16` (one PR into main, phase-labelled commits).
Phase 2:
- [ ] requirements split (core/torch/ml/separation/dev) + `setup_tools.py` (GPU/CUDA detect, torch index choice, ffmpeg/Blender detect, pip commands)
- [ ] `settings.py` (app settings JSON in data folder)
- [ ] `scripts/setup_update.py` (--full / --update, used by updater) + `setup_windows.ps1/.bat`
- [ ] `verify.py` + `scripts/verify_local.py` (REPORT_LOCAL.md/json)
- [ ] tests/test_setup_settings.py, CHANGELOG, VERIFY_LOCAL, PHASES checklist
Phase 1 user test: not done yet (user chose continuous); fold its checklist into the combined test later.

## Decisions
- Python package in `src/lyric2resolve/` (src layout). Phase 1: launcher puts `src` on sys.path (no pip install needed); later phases may install it editable.
- User data lives OUTSIDE the clone: `%LOCALAPPDATA%\lyric2resolve` (Windows) / `~/.local/share/lyric2resolve` (else), override `LYRIC2RESOLVE_DATA`. Assets (fonts/textures) therefore live in `<data>/assets/...`; the repo only holds manifests/curation lists. Reason: the updater hard-resets code and must never touch user data.
- Launcher + updater are stdlib only (Tkinter, subprocess git) so they run before heavy deps exist.
- Updater self-update: launcher copies the `updater` package to a temp dir and runs it from there as a separate process (`python -m` with PYTHONPATH=temp), then exits.
- Update strategy: fetch → tag `l2r-rollback/<timestamp>` → `git merge --ff-only origin/<branch>`; if not fast-forward but tree clean → `git reset --hard origin/<branch>`; dirty tree → refuse.
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
