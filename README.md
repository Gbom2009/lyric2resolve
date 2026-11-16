# lyric2resolve

Turn a song + its acapella into a **DaVinci Resolve timeline with the lyrics as text clips**, synced word-accurately,
in **16:9 and 9:16** at once. Around that: a full browser **editor**, a **karaoke** mode, **audio-reactive Blender
visuals** rendered headless into DJ-ready MP4s, free **font and CC0 texture** libraries, an optional **Claude Code
Assistant**, and a launcher that **updates itself** from GitHub.

Windows + NVIDIA GPU is the target (Whisper on CUDA). Everything works offline after the first setup, except
updates, asset downloads and the optional Assistant.

---

## 1. Setup (once)
Full steps: **[INSTALL.md](INSTALL.md)**. In short:
1. Install **Git for Windows** and **Python 3.12** (with "tcl/tk"), then `git clone https://github.com/Gbom2009/lyric2resolve.git`.
2. Double-click **`install.bat`**: creates `.venv` and a **lyric2resolve** shortcut (Desktop + Start menu).
3. Open the shortcut. The launcher offers **Run setup** the first time (`setup_windows.bat`): it installs PyTorch with
   the CUDA build that matches your NVIDIA driver, Whisper (faster-whisper + stable-ts), librosa, FastAPI, and checks
   for **ffmpeg** (`winget install Gyan.FFmpeg`) and **Blender** (`winget install BlenderFoundation.Blender`).
4. Run the self-test: `.venv\Scripts\python scripts\verify_local.py` → writes **REPORT_LOCAL.md** (see
   [VERIFY_LOCAL.md](VERIFY_LOCAL.md)).
5. Optional: `.venv\Scripts\python -m lyric2resolve assets sync` downloads the font library (Google Fonts, OFL/Apache
   only) and a CC0 texture/HDRI starter pack (Poly Haven + ambientCG). `assets install-fonts` makes the fonts
   visible to Resolve.

Your data (projects, settings, assets, caches, Whisper models, renders, logs) lives in
**`%LOCALAPPDATA%\lyric2resolve`**, never in the app folder. Updates never touch it.

## 2. Usage
### In the browser (normal way)
Open the shortcut → the editor opens in your browser.
- **Projects**: pick a song. New songs: see the command line below (or batch mode).
- **Lyrics**: words are atomic, **blocks** become the title clips. Click/drag/Shift+click to select words, **M** merge
  into one block, **S** split, **W** one word per block, **Alt+←/→** move a word to the neighbouring block, **E** edit
  text, **[ ]** nudge timing, **G** add an instrumental gap, **Ctrl+Z/Y** undo/redo, **Space** play.
- **Review** card: words Whisper probably got wrong (very short, overlapping, low confidence, repeats, outside the
  vocals); click to jump. **Safe-area warnings** when a block is too long for the font size in 16:9 or 9:16.
- **Sections & presets**: WORD / LINE / PHRASE (N words) / AUTO (split on pauses) per section, e.g. verse = LINE,
  chorus = WORD. **Text & timing options**: case, punctuation, max characters, minimum duration, pre/post-roll, global
  sync offset, hold until next or fade.
- **Text style**: style presets (font, size, colour, outline, shadow, glow, position, animation) with live 16:9 + 9:16
  preview, one per section; **styling level** BASIC / STYLED / FULL for the Resolve script.
- **Export…**: FCPXML (both layouts), the Resolve build script, SRT (lines + words), CSV, EDL with markers.
- **Karaoke**: fullscreen (second screen), word highlight, countdown in gaps, vocal-volume slider, playlists.
- **Ideas**: a style brief from lyrics/BPM/key/energy, 2-3 visual concepts per section, ready-to-paste Claude Code
  prompts (Blender + three.js), project templates.
- **Library**: your textures and fonts. **Settings**: tool paths, GPU, defaults, theme / Team Funqtion branding,
  Assistant, updates.
- **Assistant (Claude)** card: optional, see [docs/ASSISTANT.md](docs/ASSISTANT.md).

### Command line (`.venv\Scripts\python -m lyric2resolve …`)
```
lyric2resolve --song full.wav --acapella vocals.wav [--lyrics lyrics.txt] [--sections sections.yaml] \
              --granularity line --fps 25 --model large-v3 [--render-preset standard --template tunnel] --out ./out
lyric2resolve editor [--project path\to\project.json]
lyric2resolve batch <folder | queue.yaml> [--dry-run]       # many songs; Song.mp3 + "Song (Acapella).wav" (+ Song.txt)
lyric2resolve audio-check --song A --acapella B            # A/B offset in ms
lyric2resolve transcribe | analyze | export | render | visuals | ideas | assets | claude …   (each has --help)
lyric2resolve check-update | update | rollback | version
```
`sections.yaml` example: `default: line` + `sections: {chorus: word, verse: line}`. Without `--acapella` the vocals are
separated from the song (BS-Roformer via audio-separator, Demucs htdemucs_ft as backup) and cached.

## 3. Getting it into Resolve
- **FCPXML** (Resolve free + Studio): *File → Import → Timeline…* → pick `<song>_16x9.fcpxml` (and/or `_9x16`). Song on
  an audio track, one title per block, section + bar markers, nothing inside instrumental gaps, start 01:00:00:00.
  Details and "titles came in as plain/generic titles" fixes: [docs/RESOLVE_IMPORT.md](docs/RESOLVE_IMPORT.md).
- **Real Text+ with styling** (script route): Export with "Resolve script", then in Resolve *Workspace → Scripts →
  lyric2resolve_build_timeline*. One-time Text+ template setup: [docs/RESOLVE_SCRIPT.md](docs/RESOLVE_SCRIPT.md).
- **Why no `.drp` project file?** A Resolve project is stored in Resolve's own database (`.drp` is a proprietary,
  undocumented binary export of it). There is no supported way to write one; FCPXML import and the official scripting
  API are the supported routes, so the app uses those.

## 4. Visuals, rendering and DJ use
1. `lyric2resolve render <project.json> --template tunnel --render-preset preview` (or from the Assistant / Ideas).
   Templates: spectrum bars, pulsing blob, tunnel, particle field, neon floor grid. Bass/mids/highs drive glow, scale,
   sparkles and light (configurable in `mapping.yaml`). Presets PREVIEW → DRAFT → STANDARD → HIGH → ULTRA/4K → CUSTOM.
2. It estimates time and disk space first, shows progress, can be cancelled and **resumed**, uses OptiX/CUDA for
   Cycles (CPU fallback with a warning), and encodes an **MP4 with your full song inside** (H.264 CFR + AAC 320k).
3. Each render folder has a beginner-friendly `RENDER_INSTRUCTIONS.md`. Put the visuals on V1 under the text in Resolve.
4. **DJ decks** (Rekordbox / Serato video): exact Resolve Deliver settings and a sync check in
   **[docs/DJ_VIDEO_GUIDE.md](docs/DJ_VIDEO_GUIDE.md)**.

## 5. Updates
The launcher checks GitHub at start (and the editor shows a banner): **Update available** → read what's new →
**Update now**. It saves a rollback point, replaces the code, installs changed dependencies, runs a self-check, and
**rolls back automatically** if anything fails. **Roll back** in the launcher returns to the previous version. Local
edits in the app folder block updates (by design); your data folder is never touched. Settings:
`%LOCALAPPDATA%\lyric2resolve\settings\updater.json` or the Settings page.

## 6. Licenses
- Third-party code: wavesurfer.js (BSD-3, vendored), FastAPI/uvicorn (MIT/BSD), librosa (ISC), numpy/scipy (BSD),
  faster-whisper / stable-ts / audio-separator / Demucs (MIT), Whisper models (MIT), PyTorch (BSD).
  Blender (GPL) and ffmpeg (LGPL/GPL) are separate programs you install; the app only runs them.
- **Fonts**: only Google Fonts families whose `METADATA.pb` says OFL or Apache 2.0 are downloaded, to your PC (not
  into this repo); credits in `assets\fonts\CREDITS.md` in your data folder.
- **Textures/HDRIs**: only CC0 assets from Poly Haven and ambientCG (license confirmed at every sync);
  `assets\textures\CREDITS.md` + `manifest.json` in your data folder.
- Team Funqtion branding (logo, colours) belongs to Team Funqtion and is only shown when the toggle is on.
- This repository has no license file of its own yet.

## 7. Limitations (honest list)
- Built and tested in the cloud on Linux without GPU, Windows, Resolve, Blender GUI or DJ software; those parts are
  verified on your PC with `scripts/verify_local.py` and the checklists in [VERIFY_LOCAL.md](VERIFY_LOCAL.md).
- Some Fusion Text+ input names used by the Resolve script (outline/shadow/glow, FULL animations) are unverified until
  tested in your Resolve; the FCPXML route does not depend on them.
- Whisper can mishear sung lyrics; providing a lyrics file (forced alignment) is much more accurate. The Review card
  flags suspicious words but never changes them for you.
- Text width checks estimate character widths (no font measurement), so warnings are approximate.
- The Assistant needs your own Claude Code login and counts against your Claude Pro limits.

## 8. For developers
Read [CLAUDE.md](CLAUDE.md), [SPEC.md](SPEC.md), [PHASES.md](PHASES.md), [PROGRESS.md](PROGRESS.md),
[HANDOFF_PROMPT.md](HANDOFF_PROMPT.md). Tests: `python -m pytest -q` (browser tests need Playwright + Chromium;
`L2R_CHROMIUM=<path>` uses a preinstalled one). CI runs Linux 3.11/3.12, Windows, and a real `bpy` scene build.
