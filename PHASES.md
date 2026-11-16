# PHASES.md — lyric2resolve build plan

Each phase = its own branch `phase-NN-<slug>` cut from latest `main`, a draft PR at first push, CHANGELOG.md entry, PR marked ready when CI is green.
Budget per phase: ≤ ~6-8 files changed, ~one module, one test file. If a phase grows bigger, split it (e.g. 7a/7b) and update this file.

Conventions used below:
- **Code folder** = the git clone (`lyric2resolve/`). **Data folder** = user data outside the code folder
  (Windows: `%LOCALAPPDATA%\lyric2resolve`, Linux/macOS: `~/.local/share/lyric2resolve`, override with env `LYRIC2RESOLVE_DATA`).
  Holds `settings/`, `projects/`, `assets/{fonts,textures}` (+ `custom/`), `cache/`, `models/`, `logs/`, `renders/`.
- "local" = pytest marker for tests that need the real PC (GPU, Whisper, Blender, Resolve). Skipped in CI.
- Every phase updates VERIFY_LOCAL.md with what can only be checked on the PC.

---

## Phase 1 — Skeleton + launcher/auto-updater (section 15)
**Goal:** the first thing the user installs. After this, every merged PR arrives via the launcher's Update button.
**Files:** `pyproject.toml`, `src/lyric2resolve/__init__.py`, `src/lyric2resolve/paths.py` (data-folder convention), `src/lyric2resolve/updater/{__init__,core,gitops,changelog,steps,config}.py` (logic, stdlib only), `src/lyric2resolve/updater/ui.py` (Tkinter window, thin), `launcher.pyw`, `install.ps1`, `install.bat`, `INSTALL.md`, `CHANGELOG.md`, `.gitignore`, `.github/workflows/ci.yml`, `requirements/launcher.txt`, `tests/test_updater.py`, `VERIFY_LOCAL.md`.
(Exception to the file budget: this is the skeleton phase; the updater module itself is one module.)
**Acceptance tests (CI):** with a temp bare repo as fake remote: up-to-date / behind / ahead / diverged detection; changelog extraction of only new entries; requirements-hash change detection; dirty-tree refusal; successful ff update; failed step → automatic rollback to the tag; rollback command; self-copy to temp dir; config load/save defaults; offline fetch fails silently with timeout.
**TEST CHECKLIST FOR ME:**
1. Follow INSTALL.md: install Git for Windows + Python 3.11/3.12 (with Tcl/Tk), `git clone`, run `install.bat`. Expected: venv created, "lyric2resolve" shortcut on Desktop + Start menu.
2. Double-click the shortcut. Expected: no console window; small window "No app interface yet – version <hash> (<date>), up to date" with Check now / Roll back / Open data folder.
3. Click "Open data folder". Expected: Explorer opens `%LOCALAPPDATA%\lyric2resolve`.
4. After the next PR is merged: open the shortcut. Expected: "Update available" with plain-language changelog + commits; "Later" closes without changing anything; "Update now" shows progress steps, then "What changed".
5. Click "Roll back". Expected: confirms, returns to previous version, window shows the older hash.
6. Make a local edit in a code file, then try Update. Expected: refuses and explains (local modifications), nothing changed. Revert the edit afterwards.
**Needs user input:** none (private-repo auth uses your existing Git credentials).

## Phase 2 — Setup script + verify_local scaffold + settings module
**Goal:** full dependency install (venv, torch+CUDA, ffmpeg check), requirements split, settings/config module, `scripts/verify_local.py` producing REPORT_LOCAL.md/JSON. Updater calls the setup "update" step when requirements change.
**Files:** `setup_windows.ps1` (+ `.bat` wrapper), `src/lyric2resolve/setup_tools.py` (logic: which requirement groups, CUDA wheel index choice, ffmpeg detection), `src/lyric2resolve/settings.py`, `requirements/{core,gpu,dev}.txt`, `scripts/verify_local.py`, `tests/test_setup_settings.py`, hook in `updater/steps.py`.
**Acceptance tests:** settings defaults/merge/migration; requirements group selection; ffmpeg/Blender/GPU probing via injected fakes; verify_local report generation with all checks mocked.
**TEST CHECKLIST:** Update via launcher → it runs the dependency step (shows it can take a while). Run `setup_windows.bat` once fully. Run `.venv\Scripts\python scripts\verify_local.py` → REPORT_LOCAL.md appears with Python/venv, git, ffmpeg, GPU/CUDA/torch lines (Whisper/Blender sections "not yet implemented"). Paste the report into the session.
**Needs user input:** paste REPORT_LOCAL.md; install ffmpeg if reported missing.

## Phase 3 — Audio inputs, A/B alignment, conversion, instrumental
**Goal:** `audio` module: ffmpeg conversion to 44.1 kHz wav (ffmpeg behind an interface), cross-correlation offset estimate (ms) with warning + optional compensation, instrumental = song − acapella (aligned, gain-matched), separation fallback interface (python-audio-separator BS-Roformer/MDX23C, Demucs backup) with stem cache.
**Files:** `src/lyric2resolve/audio/{__init__,convert,align,stems}.py`, `tests/test_audio.py`, VERIFY_LOCAL additions.
**Acceptance tests:** synthetic signals with known offsets (±, sub-ms tolerance at 44.1k decimation), instrumental subtraction residual energy, cache keying by file hash, ffmpeg command construction, separation mocked.
**TEST CHECKLIST:** `lyric2resolve audio-check --song A --acapella B` on your song → prints offset in ms (expected ~0 for matching stems); `--only-song` fallback creates stems in cache (local).
**Needs user input:** a test song + its acapella (any short track).

## Phase 4 — Transcription + forced alignment + project JSON
**Goal:** `transcription` module (faster-whisper/stable-ts behind an interface, large-v3, CUDA fp16, word timestamps, VAD, language override, condition_on_previous_text=False), forced alignment when lyrics given (keep line breaks), `project` model (words, blocks, sections, gaps, settings) with JSON save/load + autosave helper.
**Files:** `src/lyric2resolve/transcription/{__init__,engine,align}.py`, `src/lyric2resolve/project.py`, `tests/test_transcription_project.py`, bundled tiny test clip `tests/data/tiny_vocal.wav` (generated/own, license-free).
**Acceptance tests:** mocked engine → project words; lyrics line breaks mapped to initial LINE blocks; JSON round-trip + schema version; autosave debounce.
**TEST CHECKLIST:** `lyric2resolve transcribe --song A --acapella B --out ./out` → `project.json` with words; verify_local transcribes the tiny clip on GPU.
**Needs user input:** run verify_local (GPU/Whisper).

## Phase 5 — Music analysis + gap detection + sanity checks
**Goal:** `analysis` module: BPM, beats, downbeats, sections (novelty+energy), key, energy curve; instrumental gap detection from vocal activity; rough-cut sanity flags (short/zero/overlap, low confidence, repeats, outside vocal activity).
**Files:** `src/lyric2resolve/analysis/{__init__,music,gaps,sanity}.py`, `tests/test_analysis.py`.
**Acceptance tests:** click-track BPM, synthetic gaps, every flag type triggered by crafted word lists.
**TEST CHECKLIST:** `lyric2resolve analyze project.json` → BPM/key/sections printed and stored; flagged-word count shown.
**Needs user input:** none.

## Phase 6 — Editor backend API
**Goal:** FastAPI app: project load/save, words/blocks CRUD, merge/split/move words between neighbours, text edit, nudge, presets (WORD/LINE/PHRASE/AUTO per section, YAML), text options, gaps CRUD, flags, undo/redo (command stack), audio file serving.
**Files:** `src/lyric2resolve/editor/{__init__,app,ops,presets,history}.py`, `tests/test_editor_api.py`.
**Acceptance tests:** merge timing = first start/last end; split keeps word timings; undo/redo round trips; preset per section; FastAPI TestClient endpoints.
**TEST CHECKLIST:** `lyric2resolve editor --project project.json` → http://127.0.0.1:PORT/docs lists the API.
**Needs user input:** none.

## Phase 7 — Editor frontend part 1 (waveform + word selection)
**Goal:** vanilla-JS frontend (no build step) with vendored wavesurfer.js: waveform, word lane, click-drag/shift-click selection, play selection / from cursor, keyboard shortcuts. Launcher now opens the editor in the browser when up to date.
**Files:** `src/lyric2resolve/editor/static/{index.html,app.js,style.css}`, vendored `wavesurfer.min.js`, launcher change, `tests/e2e/test_select.py` (Playwright, CI).
**TEST CHECKLIST:** launcher → browser opens editor; drag over words selects them; space plays selection.

## Phase 8 — Editor frontend part 2 (merge/split UI, gaps, flags, warnings)
**Goal:** merge/split/move buttons + shortcuts, inline edit, nudge, undo/redo UI, gap regions (add/resize/remove), review list of flags (jump to word), safe-area/line-length warnings (16:9 and 9:16), preset/section table, text options panel.
**Files:** `static/{blocks.js,gaps.js,review.js}`, `editor/layout_check.py`, `tests/e2e/test_merge_split.py`.
**TEST CHECKLIST:** merge 3 words → one block; split again; add a gap region; click a flag → jumps to word; long line → warning icon.

## Phase 9 — Styling model + presets + font library
**Goal:** style model (font, size, fill, outline, shadow, glow, alignment, position, per-section), styling level setting (BASIC/STYLED/FULL), style editor + live preview, font manifest + Google Fonts sync (OFL/Apache only, from license metadata), Windows font installer, preview picker.
**Files:** `src/lyric2resolve/styling.py`, `src/lyric2resolve/assets/fonts.py`, `static/styles.js`, `tests/test_styling_fonts.py`.
**TEST CHECKLIST:** `lyric2resolve assets sync --fonts` on PC → `assets/fonts` + CREDITS; `assets install-fonts` → fonts visible in Resolve.
**Needs user input:** run sync on PC.

## Phase 10 — FCPXML export (16:9 and 9:16, no clips in gaps)
**Goal:** frame-accurate FCPXML (version Resolve imports best — verify; likely 1.9/1.10) with Track A audio, one Basic Title per block, markers for beats/sections, configurable fps + start TC 01:00:00:00, both layouts; nothing inside gaps. Timecode/frame math module. DTD validation.
**Files:** `src/lyric2resolve/export/{__init__,timecode,layout,fcpxml}.py`, vendored DTD under `tests/data/`, `tests/test_fcpxml.py`.
**TEST CHECKLIST:** Export → import both .fcpxml files in Resolve (File > Import > Timeline); titles land on the right words; gaps empty.
**Needs user input:** Resolve version.

## Phase 11 — Resolve script + SRT/CSV/EDL + styling levels
**Goal:** `resolve_build_timeline.py` (Workspace > Scripts) inserting Fusion Text+ at frames with styling levels; SRT line/word, CSV, EDL with markers. Mocked Resolve API tests.
**Files:** `src/lyric2resolve/export/{resolve_script,srt,csv_export,edl}.py`, template `resolve_build_timeline.py`, `tests/test_exports_resolve.py`.
**TEST CHECKLIST:** copy script to Resolve scripts folder, run → timeline with Text+ clips styled per level.

## Phase 12 — Karaoke mode
**Goal:** Karaoke page (fullscreen, word highlight, current+next line, gap countdown), Web Audio mix instrumental + acapella with vocal slider, playlist/queue (next/prev/reorder/search), shortcuts, offline.
**Files:** `src/lyric2resolve/karaoke.py` (timing data API), `static/karaoke.{html,js,css}`, `tests/test_karaoke.py`.
**TEST CHECKLIST:** open Karaoke, play a project on second screen, slider fades vocals, queue next song.

## Phase 13 — Texture asset sync + texture browser
**Goal:** Poly Haven + ambientCG sync (verify APIs), CC0-only filter, curated list, resumable + checksummed downloads, rate limiting, manifest.json + CREDITS.md, custom folder, browser tab.
**Files:** `src/lyric2resolve/assets/{textures,download,curation.yaml}`, `static/textures.js`, `tests/test_assets_textures.py`.
**TEST CHECKLIST:** `lyric2resolve assets sync` on PC → textures + CREDITS.md; browser tab shows thumbnails.

## Phase 14 — Audio-reactive Blender generator + scene templates
**Goal:** band energies (bass/mids/highs/RMS/onset), attack/release smoothing, gain/normalize at fps → JSON/CSV; bpy scene generator writing keyframes/drivers; band→target mapping YAML; templates (spectrum bars, blob, tunnel, particles, floor grid); material builder with emission mask; 16:9 + 9:16 cameras.
**Files:** `src/lyric2resolve/visuals/{__init__,bands,mapping,blender_gen}.py`, `scene_templates/*.py`, `tests/test_visuals.py` (mocked bpy).

## Phase 15 — Headless render + presets + DJ mux + RENDER_INSTRUCTIONS
**Goal:** `blender -b -a` runner (progress parse, cancel, resume, GPU detect + fallback), presets PREVIEW..ULTRA/Custom, test-frame time/disk estimate, PNG→MP4 with song muxed (Rekordbox/Serato compatible, CFR, verify formats), RENDER_INSTRUCTIONS.md generator.
**Files:** `src/lyric2resolve/render/{__init__,runner,presets,mux,instructions}.py`, `tests/test_render.py`.
**TEST CHECKLIST:** preview render of a project; MP4 plays on Rekordbox/Serato in sync.
**Needs user input:** Blender path, DJ software versions.

## Phase 16 — Visual ideas / prompt generator + project templates
**Goal:** style brief from lyrics/BPM/key/energy/sections, 2-3 concepts per section, Claude Code prompts for Blender and three.js (template-based), project templates save/load/apply.
**Files:** `src/lyric2resolve/visuals/{brief,prompts}.py`, `src/lyric2resolve/templates.py`, `static/ideas.js`, `tests/test_prompts_templates.py`.

## Phase 17 — Claude link (CLI subprocess + MCP server + Blender MCP foundation)
**Goal:** Assistant panel running real `claude -p --output-format stream-json --resume <id>` (verify flags), per-project session id + CLAUDE.md notes, app MCP server (stdio) with the listed tools, generated MCP config, usage-limit notice, optional Blender MCP docs/config.
**Files:** `src/lyric2resolve/claude_link/{__init__,cli,mcp_server,notes}.py`, `static/assistant.js`, `tests/test_claude_link.py` (fake claude executable).
**Needs user input:** confirm `claude` CLI installed + logged in.

## Phase 18 — Settings UI, branding toggle, batch mode, in-app update banner
**Goal:** settings page (paths, GPU info, defaults, styling level, theme/branding, Claude status, updater), Team Funqtion brand tokens (from gbom2009/funqtion-site if accessible, else TODO config), batch queue (smoke-tested), browser update banner using Phase 1 updater logic.
**Files:** `src/lyric2resolve/{batch,branding}.py`, `editor/settings_api.py`, `static/settings.js`, `config/brand_funqtion.json`, `tests/test_settings_batch.py`.
**Needs user input:** access to funqtion-site repo or brand values.

## Phase 19 — Full test pass, README, DJ guide, consolidated VERIFY_LOCAL
**Goal:** end-to-end CLI (`lyric2resolve --song ... --out`), README (setup, usage, Resolve import, DJ guide, rendering, licenses, update workflow, limitations, why no .drp), DJ_VIDEO_GUIDE.md, consolidated VERIFY_LOCAL.md + verify_local.py covering everything; final HANDOFF "PROJECT COMPLETE".
**Files:** `README.md`, `DJ_VIDEO_GUIDE.md`, `VERIFY_LOCAL.md`, `scripts/verify_local.py`, `src/lyric2resolve/cli.py`, `tests/test_end_to_end.py`.
**TEST CHECKLIST:** full run on a real song → both FCPXMLs import, karaoke plays, preview render plays on decks; verify_local all green.
