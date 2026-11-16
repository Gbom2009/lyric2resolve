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
| 6 | Editor backend API | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 7 | Editor frontend 1 | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 8 | Editor frontend 2 | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 9 | Styling + fonts | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 10 | FCPXML export | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 11 | Resolve script + SRT/CSV/EDL | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 12 | Karaoke | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 13 | Texture sync + browser | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 14 | Blender generator | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 15 | Headless render + DJ mux | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 16 | Prompt generator + templates | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 17 | Claude link | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 18 | Settings UI / branding / batch / update banner | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |
| 19 | Full test pass + docs | done (in PR #2, not merged) | continuous-2026-11-16 / PR #2 |

Statuses: planned / in progress / PR open / merged / tested-OK / needs fixes / waiting for user

## CURRENT STEP LOG
Continuous mode, branch `continuous-2026-11-16` (one PR into main, phase-labelled commits).
Phase 2: done (setup_tools.py, settings.py, verify.py, scripts/setup_update.py, scripts/verify_local.py, setup_windows.ps1/.bat, tests/test_setup_settings.py).
Phase 3: done (audio/{convert,wavio,align,stems,__init__}.py, `audio-check` CLI, verify checks audio_offset + vocal_separation, tests/test_audio.py).
Phase 4: done (project.py, transcription/{engine,__init__}.py, `transcribe` CLI, verify whisper checks, tests/data/tiny_vocal.wav).
Phase 5: done (analysis/{music,gaps,sanity,__init__}.py, `analyze` CLI, tests/test_analysis.py).
Phase 6: done (editor/{ops,presets,history,app}.py, `editor` CLI, tests/test_editor_api.py).
Phase 7: done (static/{index.html,style.css,app.js}, vendored wavesurfer 7.12.12, project picker API, launcher starts editor via updater/appctl.py, tests/e2e/*).
Phase 8: done (static/{blocks,gaps,review}.js, layout.py (shared text layout/safe area), layout warnings in state, tests/e2e/test_merge_split.py).
Phase 9: done (styling.py, assets/{__init__,fonts}.py, assets/fonts/curation.json, static/styles.js, tests/test_styling_fonts.py + e2e/test_styles.py).
Phase 10: done (export/{timecode,timeline,fcpxml,__init__}.py, editor Export dialog (static/export.js), docs/RESOLVE_IMPORT.md, verify check fcpxml_validity, tests/test_fcpxml.py).
Phase 11: done (export/{textformats,resolve_job}.py, export/resolve_template/lyric2resolve_build_timeline.py, docs/RESOLVE_SCRIPT.md, tests/test_exports_resolve.py).
Phase 12: done (karaoke.py, karaoke endpoints in editor/app.py, static/karaoke.{html,css,js}, tests/test_karaoke.py + e2e/test_karaoke.py, tests/conftest.py isolates the data folder for every test).
Phase 13: done (assets/textures.py, assets/textures/curation.json, /library page (static/library.{html,js}), tests/test_assets_textures.py).
Phase 14: done (visuals/{bands,mapping,procedural,blender_gen}.py, visuals/blender_template/l2r_scene.py (5 templates), `visuals` CLI, tests/test_visuals.py; CI job 'blender' installs bpy 5.3 and builds all templates).
Phase 15: done (render/{presets,blender,runner,mux,instructions,__init__}.py, `render` CLI, tests/data/fake_blender.py, tests/test_render.py, docs/DJ_VIDEO_GUIDE.md).
Phase 16: done (visuals/{brief,prompts}.py, templates.py, /ideas page (static/ideas.{html,js}), `ideas` CLI, apply_template op, tests/test_prompts_templates.py).
Phase 17: done (claude_link/{__init__,cli,notes,mcp_server}.py, render/jobs.py, editor endpoints /api/assistant/* + /api/render*, static/assistant.js (side-panel card), docs/ASSISTANT.md, verify checks claude_cli + mcp_server, tests/test_claude_link.py + tests/data/fake_claude.py + tests/e2e/test_assistant.py).
Phase 18: done (branding.py + config/brand_funqtion.json + static/brand/funqtion-logo.svg, editor/settings_api.py (/api/settings, /api/settings/updater, /api/update/*, /theme.css, /api/brand, /settings), static/{settings.html,settings.js,update_banner.js}, appctl update-request hand-off + launcher watcher, batch.py (`batch` CLI, run_song = single-song pipeline), tests/test_settings_batch.py + e2e/test_settings.py).
Phase 19: done (cli.py end-to-end `lyric2resolve --song ...` via batch.run_song, README.md, VERIFY_LOCAL FULL TEST PASS section, verify check blender_3_frame_render (real render path, 3 preview frames; fake-Blender test), tests/test_end_to_end.py).
ALL PHASES BUILT. PR #2 = phases 2-19, ready for the user to merge + run the FULL TEST PASS (VERIFY_LOCAL.md). Next session: record the user's REPORT_LOCAL.md + feedback here, fix on a new branch from main ("Fixes from testing").
Session 3 (2026-11-16): user confirmed: continue on PR #2, Claude CLI installed on PC, try funqtion-site for branding, test everything later.
Phase 1 user test: not done yet (user chose continuous); fold its checklist into the combined test later.

## Decisions
- Branding: tokens from the public funqtion-site repo (css/tokens.css, commit 8bccd0f) in `config/brand_funqtion.json`; user edits go in `<data>/settings/brand_funqtion.json` (editing the repo copy would make the code folder dirty and block updates). Served as `/theme.css` (CSS variable overrides) on every page; brand fonts only from the local font library (offline, no Google requests). Toggle = `funqtion_branding` (or theme "funqtion").
- Browser update banner: the editor runs `core.check_for_update` in a background thread (cached 30 min); "Update now" writes `<data>/settings/update_request.json` and the launcher (polling every 2 s while the editor runs) does the normal self-copying update. Only when the editor was started by the launcher (env L2R_LAUNCHER=1). Tests set L2R_NO_UPDATE_CHECK=1 so no git fetch runs.
- Batch: folder pairing by name tokens (acapella/vocals/vox/voice, "_" counts as separator) or queue.yaml; never stops on one failure; report rewritten after every song. `batch.run_song` is the single-song pipeline reused by the Phase 19 CLI.
- Claude link: real CLI only (`claude -p --output-format stream-json --verbose`, prompt via stdin to avoid claude.cmd quoting; `--session-id` first, `--resume` after; `--mcp-config <project>/.l2r_mcp.json --allowedTools mcp__lyric2resolve`). Flags + event shapes verified on CLI 2.1.325 in the cloud (one real run). ANTHROPIC_API_KEY is removed from the child env so the user's subscription is used. Lost session (resume fails) -> automatic retry with a new id.
- MCP server is stdlib JSON-RPC (no `mcp` package): initialize/ping/tools/list/tools/call, newline-delimited. With `--editor-url` it edits through the running editor's API (one owner of the project + shared undo; the browser card reloads state after each tool result); without it, it edits project.json directly via EditorSession.
- Assistant UI = card in the editor side panel (not a separate page) so edits are visible live; polling `/api/assistant/events?after=n` (no websockets).
- One background render at a time (`render/jobs.RenderJobs`), shared by `/api/render*` and the MCP tools.
- On Windows, Stop kills the process tree (`taskkill /T`): claude.cmd -> node -> MCP server.
- Render: scene rebuilt per preset (curves must match the render fps); Blender args order: file, -P setup, -s/-e/-a, then `--` job (Blender ignores args after `--`). Resume = use_overwrite off + only missing frame ranges requested. Estimate = 3 middle frames into `_estimate/` (deleted). DJ encode: H.264 High yuv420p CFR, GOP ≤25, AAC 320k 48k, faststart; `_dj.mp4` copy fits 1920x1080 (Rekordbox limit). NVENC tried first, falls back to libx264.
- Blender scenes: curves keyframed as custom props on an empty `L2R_Controller` (fast keyframe_points.foreach_set; slotted-action compatible for 4.4/5.x), all reactive values are simple-expression drivers on it (no Python auto-run needed). Bloom via compositor Glare (5.x: node group + `inputs['Type']='Bloom'`). Textures packed into the .blend. Verified with the bpy 5.3 wheel (Python 3.13) incl. Cycles CPU renders.
- Textures: Poly Haven + ambientCG have no per-asset license field; both are site-wide CC0, so the sync requires 'CC0' on each site's license page (checked every sync) and records CC0 per asset. Poly Haven files verified by md5, ambientCG zips by size + testzip; zips extracted flat (images only). Default 1k.
- Karaoke audio: both stems decoded to AudioBuffers and started on the same AudioContext time (sample-accurate sync); gain nodes with setTargetAtTime for click-free fades. Playlists in `<data>/settings/karaoke_playlists.json`.
- Resolve script: the API (README 2026) has no way to set a timeline item's duration and InsertFusionTitleIntoTimeline ripple-inserts, so Text+ clips are AppendToTimeline copies of a user-made Media Pool Fusion Composition named `l2r_textplus` with exact startFrame/endFrame/recordFrame; fallback = ImportTimelineFromFile(FCPXML). Script is self-contained (stdlib), reads `<data>/exports/last_resolve_job.json`, installed to %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility.
- FCPXML 1.9, one file per layout: spine = one gap covering the song from the start TC; song = connected asset-clip lane -1; titles = Basic Title lane 1; markers on the gap. NTSC rates use 1000/1001 with NDF timecode. Apple's DTD is NOT committed (Apple copyright); tests/verify download it from the CommandPost mirror and skip when offline.
- All exporters share `export/timeline.build_plan` (frame-snapped clips) and `check_plan` (no overlaps, nothing in gaps); export refuses to write if check_plan fails.
- Styles live in `project.styles` (StyleBook: user presets + default + by_section label→name); built-ins are code. Resolution: block > section own > section by id > by label > default. BASIC ignores presets; STYLED drops animations; FULL keeps them.
- Fonts: license from google/fonts METADATA.pb (OFL/APACHE2 only; UFL rejected); static TTFs via the Google Fonts CSS2 API with an old User-Agent (variable fonts are unreliable in Resolve). Per-user install: copy to %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts + HKCU Fonts registry value. No fonts are committed to the repo.
- Text width is estimated from character counts (0.55 em mixed / 0.68 em uppercase) in `lyric2resolve/layout.py`; used for warnings now and for wrapping/positions in exports. Font size 0 = auto (7.5% of height in 16:9, 4.4% in 9:16).
- Frontend: vanilla JS, global `window.L2R` with hooks (render/selection/keydown/ready) so later files plug in; wavesurfer 7.12.12 UMD vendored in static/vendor. E2E tests: Python Playwright (CI installs chromium; locally the preinstalled one).
- Launcher = app control window: runs the editor as a child process (no console, log in data/logs/editor.log), picks a free port from settings.editor_port, opens the browser, stops it on close/update/rollback.
- Editor ops are pure functions on Project, called via a whitelist (`editor.app.OPS`) from `POST /api/op/{name}`; undo/redo = full project snapshots (simple, projects are small); failed ops restore the snapshot; every successful op saves immediately.
- PHRASE preset restarts at lyric line breaks; presets never cross gaps/sections; max_chars splits at the biggest pause near the middle.
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
- Unverified on real hardware/software (by design, see VERIFY_LOCAL.md): Whisper on CUDA, separation model name, Resolve FCPXML import + Text+ input names, Eevee headless render, Rekordbox/Serato playback, Windows launcher/update flow, Claude CLI on Windows (claude.cmd vs claude.exe).
- Google Fonts CSS2 static-TTF trick and Poly Haven/ambientCG endpoints are verified only from the cloud; asset sync must be run on the PC.

## User test feedback per phase
- (none yet)

## Pending VERIFY_LOCAL items
- Phase 1: install, shortcut, update flow, self-update, rollback on Windows (see VERIFY_LOCAL.md).
- Phase 2: setup_windows.bat, verify_local report (waiting for user: paste REPORT_LOCAL.md).
- Phase 3: audio-check with a real song + acapella; separation model name (waiting for user: test song + acapella).

## Local verification reports (paste below)
- (none yet)
