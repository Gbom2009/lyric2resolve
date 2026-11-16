# Changelog

Newest first. Each entry says in plain language what is new, what changed and what to test.
The launcher shows the new entries when an update is available and after updating.

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
