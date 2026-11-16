# Changelog

Newest first. Each entry says in plain language what is new, what changed and what to test.
The launcher shows the new entries when an update is available and after updating.

## Phase 14 — Audio-reactive Blender scenes
**New**
- `lyric2resolve visuals <project.json> --template <name>` prepares an audio-reactive Blender scene for your song, in 16:9 and 9:16, at your project's frame rate.
- Five scene templates: **spectrum bars**, **pulsing blob**, **tunnel**, **particle field** (sparkles), **neon floor grid**.
- The song is analysed into curves: bass (20-150 Hz), mids (150-2000 Hz), highs (2-12 kHz), loudness, onsets and beats, smoothed with attack/release and normalised. The curves are saved as `curves.json`/`curves.csv` next to the scene, so you can tweak them without analysing again.
- Default look: bass = glowing orange + scale pulse, mids = glowing blue (+ rotation), highs = glowing green + sparkles, loudness drives the light, beats give a small camera shake. Choruses/drops glow brighter than verses. Everything is configurable in `mapping.yaml` (colours per band and per section, amounts).
- Materials use a texture from your CC0 library (or procedural patterns: noise, grid, hex, cracks, stripes) with the audio-reactive glow layered on top; textures are packed into the .blend.
- Build the .blend files with `blender -b -P l2r_scene.py -- scene_data.json` (the next phase does this and the rendering for you).

**What to test**
- Generate a scene for your song, build it with Blender, open the .blend and scrub the timeline: shapes should pulse with the music.

## Phase 13 — Free texture library (CC0) + Library page
**New**
- `lyric2resolve assets sync --textures [--resolution 1k|2k|4k]` downloads a hand-picked starter pack of free CC0 textures and HDRIs for glowing visuals from Poly Haven and ambientCG: brushed/dark metal, sci-fi panels, carbon fiber, concrete, lava/cracked rock, rock, rubber, leather, fabric, tiles/grids, ice, foil, plus dark night and studio HDRIs. Full PBR sets (colour, normal, roughness, height, AO, metalness, emission where available).
- Safe and polite: the CC0 license is confirmed from each site before downloading, one download at a time with pauses, every file verified (checksum/size), and an interrupted sync continues where it stopped. A `manifest.json` and `CREDITS.md` are written; textures are never stored in the app folder or git.
- Your own textures: put them in `…\assets\textures\custom` (one folder per material, or single images; `.hdr`/`.exr` count as HDRIs).
- New **Library** page (button in the editor): browse textures with thumbnails, filter by category, and preview all fonts with your own sample text.

**What to test**
- Run `assets sync --textures` (≈150 MB at 1k) → open Library → textures with thumbnails; run it again → it finishes quickly without downloading again.

## Phase 12 — Karaoke mode
**New**
- **Karaoke** button in the editor (or http://127.0.0.1:8765/karaoke): plays a saved song full-screen with big readable text. The current line lights up word by word as it is sung, the next line is shown below, and before the first line and during instrumental gaps a countdown appears.
- Audio: plays the instrumental by default; the **Vocals** slider fades the original vocals (the acapella) in and out smoothly. Both are mixed in the browser and stay perfectly in sync. Songs without an instrumental play the full song.
- Karaoke night: saved playlists/queues — add songs with the quick search, reorder (↑/↓), remove, next/previous. Saved automatically.
- Keys: Space play/pause, N/P next/previous song, ↑/↓ vocal volume, ←/→ skip 5 s, F fullscreen, Q queue. Opens in its own window, so you can drag it to a second screen/TV.
- Works fully offline from your saved projects.

**What to test**
- Click Karaoke on a project, press Space, move the vocal slider, go fullscreen on a second screen.
- Build a queue of 3 songs, reorder, use N/P; restart the app → the queue is still there.

## Phase 11 — Resolve script with real Text+, plus SRT / CSV / EDL
**New**
- Export option **Resolve script**: a script you run inside Resolve (Workspace → Scripts → Utility → lyric2resolve_build_timeline). It builds the 16:9 and 9:16 timelines in your open project with the song on the audio track and a real **Fusion Text+** clip per lyric line at the exact frames, styled according to your styling level (BASIC / STYLED with outline, shadow, glow / FULL with fade, pop, slide-up or word-by-word reveal), plus section and bar markers. The export copies the script into Resolve's scripts folder for you.
- One-time setup in Resolve: a Media Pool item called `l2r_textplus` (see `docs/RESOLVE_SCRIPT.md`). Without it the script imports the FCPXML instead.
- Export option **SRT / CSV / EDL**: subtitles per line and per word (SRT), a CSV with start/end/text, and an EDL with markers (sections, bars, lyric lines) for Resolve's "Import Timeline Markers from EDL".

**What to test**
- Create the `l2r_textplus` template once, export with "Resolve script", run the script in Resolve → check timing, Text+ size/position, and the styling level effects. Report what looks off (with your Resolve version).
- Open the SRT in a video player next to the song; import the EDL markers.

## Phase 10 — Export to DaVinci Resolve (FCPXML), 16:9 and 9:16
**New**
- **Export…** button in the editor (and `lyric2resolve export <project.json>`): writes an FCPXML timeline for Resolve for 16:9 (1920×1080) and/or vertical 9:16 (1080×1920), made from your edited blocks.
- The timeline has the full song on an audio track, one title per lyric block (text wrapped and positioned for each layout, in your style when the styling level is STYLED/FULL), markers for the sections and bars, and starts at 01:00:00:00 (configurable).
- Frame-accurate at 23.976, 24, 25, 29.97, 30, 50 and 60 fps.
- Instrumental gaps are respected strictly: no titles (and no bar markers) inside a gap. Lines that fall completely inside a gap are left out and you get a note.
- Step-by-step import guide: `docs/RESOLVE_IMPORT.md` (incl. what to do if titles arrive as simple Text titles instead of Text+, and why a `.drp` file cannot be generated).

**What to test**
- Export both layouts and import them in Resolve via File → Import → Timeline (see the guide). Check: the song plays, titles appear on the right words, nothing inside the gaps, markers on sections.
- Tell me your Resolve version and whether the titles came in as Text or Text+.

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
