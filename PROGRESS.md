# PROGRESS.md — lyric2resolve

MODE: continuous (set 2026-11-16 by user; branch `continuous-2026-11-16`, one PR)

## Phase status
| # | Phase | Status | Branch / PR |
|---|-------|--------|-------------|
| 0 | Planning docs | merged (initial commit on main) | main |
| 1 | Skeleton + launcher/updater | merged (user test pending) | PR #1 |
| 2 | Setup script + verify_local + settings | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 3 | Audio inputs / alignment / instrumental | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 4 | Transcription + project JSON | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 5 | Music analysis + gaps + sanity | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 6 | Editor backend API | in progress | continuous-2026-11-16 / PR #2 |
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
Phase 2: done (setup_tools.py, settings.py, verify.py, scripts/setup_update.py, scripts/verify_local.py, setup_windows.ps1/.bat, tests/test_setup_settings.py).
Phase 3: done (audio/{convert,wavio,align,stems,__init__}.py, `audio-check` CLI, verify checks audio_offset + vocal_separation, tests/test_audio.py).
Phase 4: done (project.py, transcription/{engine,__init__}.py, `transcribe` CLI, verify whisper checks, tests/data/tiny_vocal.wav).
Phase 5: done (analysis/{music,gaps,sanity,__init__}.py, `analyze` CLI, tests/test_analysis.py).
Phase 6 (editor backend): next → `editor/{ops,history,presets,app}.py`, tests/test_editor_api.py.
Phase 1 user test: not done yet (user chose continuous); fold its checklist into the combined test later.

## Decisions
- Music analysis: librosa only (no madmom: unmaintained, hard on Win/Py3.12). Beat tracking at hop 256 (hop 512 cannot represent 120 BPM), trim=False, grid extended at constant tempo over quiet parts; BPM from least-squares fit. Downbeats = beat phase with most low-band energy. Sections = checkerboard novelty on beat-synced chroma+MFCC+RMS SSM, labelled by energy.
- Gaps = word-less stretches ≥ `settings.min_gap_s` (4 s) unless the acapella is mostly active there; manual gaps survive re-analysis.
- Whisper backend: stable-ts 2.19 `load_faster_whisper` (faster-whisper 1.2). Transcribe uses faster-whisper's own `vad_filter` (no torch-hub download), `condition_on_previous_text=False`; align uses `model.align(..., original_split=True)` + language detection via `detect_language`. Verified against package source, not yet on the PC.
- Words get stable ids `w00001...`; blocks reference word ids; `Word.line` = lyric line / Whisper segment.
- Offset convention: `offset_ms > 0` = acapella starts later than the song's vocals. Cross-correlation at 11025 Hz on the first 120 s, ±10 s max lag, parabolic refinement.
- Instrumental = song − g·acapella (least-squares gain per channel); cached by content hash. CLI: `python -m lyric2resolve <app-command>` routes app commands via `__main__.APP_COMMANDS`, everything else to the updater CLI.
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
- Phase 2: setup_windows.bat, verify_local report (waiting for user: paste REPORT_LOCAL.md).
- Phase 3: audio-check with a real song + acapella; separation model name (waiting for user: test song + acapella).

## Local verification reports (paste below)
- (none yet)
