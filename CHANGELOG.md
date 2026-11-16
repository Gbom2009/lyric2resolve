# Changelog

Newest first. Each entry says in plain language what is new, what changed and what to test.
The launcher shows the new entries when an update is available and after updating.

## Phase 9 — Text styles and the font library
**New**
- Styling level (how much the app sets up in Resolve): BASIC (plain text, default font/colour), STYLED (your style preset), FULL (styled + simple animations: fade, pop, slide up, word reveal).
- Style presets with a live 16:9 and 9:16 preview in the editor: font, weight, size, fill colour, outline, shadow, glow, alignment, height on screen per layout, animation. Built-in looks (Clean, Bold Yellow, Neon, Minimal, Karaoke Big) + your own ("Save as…").
- One style per section (e.g. all choruses Neon) and per block; a default style for the rest.
- Font library: `lyric2resolve assets sync --fonts` downloads 30 hand-picked free Google Fonts for lyric videos (Montserrat, Bebas Neue, Anton, Orbitron, Monoton, …). Each family's license is checked first: only SIL Open Font License or Apache 2.0 fonts are downloaded. A `CREDITS.md` with authors and licenses is written next to them.
- `lyric2resolve assets install-fonts` installs them (plus your own fonts in `…\assets\fonts\custom`) for your Windows user so Resolve can use them (restart Resolve afterwards). The editor's font picker shows library, custom and standard Windows fonts.

**What to test**
- Run `assets sync --fonts`, then `assets install-fonts`, restart Resolve → the fonts appear in Resolve's font list.
- In the editor: change the styling level, edit a style, Save as…, give the chorus its own style; watch the preview.

## Phase 8 — The editor in your browser (part 2: editing)
**New**
- Toolbar + shortcuts to shape the lyric blocks: Merge (M), Split at a word (S), split into single Words (W), move a word to the previous/next block (Alt+←/→), Edit text (E), Remove a block from the timeline (Delete), nudge timing ([ ] = 20 ms, with Shift 100 ms).
- Selection panel: change a word's text and exact start/end time, or override the whole block text as it should appear in the video (and reset it).
- Instrumental gaps on the waveform: drag/resize them, double-click to remove, add one from the selected words (G) or at the cursor.
- Review panel: every flagged word (sanity check) and every "probably too long for the screen" block (16:9 and 9:16) in one list; click to jump there. Long blocks get a ⚠ in the lyrics list. Nothing is changed automatically.
- Sections & presets: rename sections, choose a preset per section (WORD / LINE / PHRASE / AUTO), rebuild one section or everything.
- Text & timing options: case, strip punctuation, max characters, minimum clip length (+ merge shorter blocks), hold-until-next, fade, global sync offset, pre/post-roll, font size and max lines.

**What to test**
- On a real project: merge, split, move words, edit, nudge, undo/redo; check that `project.json` keeps your changes after restarting the editor.
- Add/resize/remove gaps on the waveform; click items in the Review list.
- Set chorus = WORD and click Apply for that section.

## Phase 7 — The editor in your browser (part 1)
**New**
- The launcher now starts the app: after the update check it starts the editor and opens it in your browser. The small launcher window stays open with "Open editor in browser", "Check for updates", "Roll back" and "Open data folder"; closing it stops the editor.
- If the full setup has not been run yet, the launcher says so and offers "Run setup".
- Editor screen: waveform of the song (switch to acapella or instrumental), zoom, your lyric blocks with every word as a chip, instrumental gaps shown between the lines, low-confidence and flagged words marked.
- Select words by click, click-and-drag, or Shift+click; arrow keys move the selection (Shift extends). The selection is highlighted on the waveform.
- Play / pause from the cursor (Space), play just the selection (Shift+Space), undo/redo (Ctrl+Z / Ctrl+Y). "Projects" opens another song.

**What to test**
- Start the shortcut → editor opens in the browser with your project list (make a project first with `transcribe`).
- Select words with the mouse and keyboard, play the selection, switch audio sources, zoom.

## Phase 6 — Editor engine (backend)
**New**
- The engine behind the browser editor: merge selected words into one lyric block, split a block at any word (word timings stay exactly as they were), move a word to the neighbouring block, edit text, nudge timing, remove blocks, add/resize/remove instrumental gaps, unlimited undo/redo. Every edit is saved to `project.json` right away.
- Presets to build blocks as a starting point: WORD (one word per block), LINE (your lyric lines), PHRASE (N words, restarting at each line), AUTO (new block after a pause longer than X s); per section (e.g. verse = LINE, chorus = WORD) or from a `sections.yaml` file. Blocks never run through a gap or past "max characters".
- Text options for the export: UPPERCASE / lowercase / Title Case, strip punctuation, merge blocks shorter than N frames.
- Command: `lyric2resolve editor --project <project.json>` starts it; until the next phase the page only links to the API docs.

**What to test**
- `lyric2resolve editor --project <project.json>` → the browser opens a placeholder page; `/docs` lists the API. (The real editor screen comes in the next phase.)

## Phase 5 — Music analysis, instrumental gaps, sanity check
**New**
- Analyses the song: BPM, beat grid and bar starts (downbeats), key, an energy curve and section boundaries (labelled intro / verse / chorus / outro as a first guess you can rename later). Beats and sections become markers in the exports.
- Instrumental gaps: long stretches without vocals (intro, breaks, outro) are detected automatically; gaps you add yourself are kept when re-analysing. Nothing will be placed on the timeline inside a gap.
- Sanity check: flags (never changes) words Whisper probably got wrong: zero/very short durations, overlaps, low confidence, words far away from any singing, suspicious repeats ("la la la la" loops) and typical Whisper phantom phrases ("thanks for watching").
- Command: `lyric2resolve analyze <project.json>`.

**What to test**
- Run `analyze` on the project from Phase 4 → check the BPM against what you know, see if the sections roughly match the song, and look at the flagged words.

## Phase 4 — Whisper transcription and the project file
**New**
- Transcribes the acapella with Whisper (large-v3 by default, on your NVIDIA GPU) with a timestamp for every word. Voice-activity detection is on; the language is detected automatically or you can set it.
- Got the lyrics? Give a text file and the app aligns YOUR lyrics to the acapella instead (forced alignment). Your line breaks become the first lyric blocks; `[Chorus]`-style tags are ignored.
- Everything is stored in an editable project file (`project.json`): words, blocks, sections, instrumental gaps and settings. The editor (later phase) autosaves into it.
- Command: `lyric2resolve transcribe --song song.mp3 --acapella vocals.wav [--lyrics lyrics.txt] [--language nl]`.
- `verify_local.py` now loads Whisper on your GPU and transcribes a 4-second test clip.

**What to test**
- Run the transcribe command on a real song → it prints the number of words/blocks and where `project.json` is saved (in `%LOCALAPPDATA%\lyric2resolve\projects\<song>`). Open it and check a few word times.
- Same with `--lyrics` → blocks match your lines.
- Run `scripts\verify_local.py` → `whisper_model_load` and `whisper_tiny_clip` ok.

## Phase 3 — Audio inputs, A/B sync check, instrumental
**New**
- Your song (Track A) and acapella (Track B) are converted to 44.1 kHz wav with ffmpeg (mp3, wav, flac, m4a, ...). Converted files are cached, so the same song is only converted once.
- Sync check: the app measures whether the acapella starts earlier or later than the vocals in the song (in milliseconds) and warns you. Optional auto-compensation shifts the acapella to match.
- Instrumental: made by subtracting the acapella from the song (used later by karaoke mode), cached.
- No acapella? The app can separate the vocals itself (BS-Roformer via audio-separator, Demucs as backup), cached per song.
- Command: `lyric2resolve audio-check --song song.mp3 --acapella vocals.wav [--compensate]`.

**What to test**
- `.venv\Scripts\python.exe -m lyric2resolve audio-check --song <song> --acapella <acapella>` → prints the offset (≈0 ms for matching stems) and where the instrumental was saved; listen to the instrumental wav.
- Same without `--acapella` → separates the vocals (takes a minute on GPU, first run downloads the model).

## Phase 2 — Full setup, settings and the local check script
**New**
- `setup_windows.bat`: installs everything the app needs into its own environment: PyTorch with the CUDA version that matches your NVIDIA driver, Whisper (faster-whisper + stable-ts), audio libraries, and optional vocal separation. Safe to run again.
- The updater now runs this dependency step automatically when an update changes the requirements (the first update after this one downloads PyTorch, ~2-3 GB, so it takes a while).
- `scripts/verify_local.py`: checks Python, Git, ffmpeg, GPU/CUDA, torch, Blender and the asset download sites, and writes `REPORT_LOCAL.md` for you to paste into the Claude session.
- App settings file `%LOCALAPPDATA%\lyric2resolve\settings\app.json` (paths, Whisper model, fps, resolution, styling level, theme). A settings page comes later.

**What to test**
- Run `setup_windows.bat` once (or let the launcher update do it); it ends with "Setup complete".
- Run `.venv\Scripts\python.exe scripts\verify_local.py` and paste `REPORT_LOCAL.md` into the session. If ffmpeg is missing: `winget install Gyan.FFmpeg`.

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
