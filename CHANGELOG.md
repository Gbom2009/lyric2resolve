# Changelog

Newest first. Each entry says in plain language what is new, what changed and what to test.
The launcher shows the new entries when an update is available and after updating.

## Fixes from testing (6) — Blender: "key Emission Color not found"
**Fixed**
- Building a Blender scene failed with `KeyError: 'Emission Color'` on older Blender versions: Blender 3.x calls that setting "Emission". The scenes now work with both names, so Blender 3.6 works too.
- The render log now shows which Blender version is used. If it's very old, there's a warning, and a failed scene build tells you to update Blender (4.2 LTS or newer is recommended).

**What to test**
- Visuals page → render **Particle field** (and the other templates) again. Also check the Blender version in the log; updating to the current Blender is still recommended.

## Mac fixes from testing (3) — "CERTIFICATE_VERIFY_FAILED" when transcribing
**Fixed (Mac)**
- Transcribing failed with "SSL: CERTIFICATE_VERIFY_FAILED". Python from python.org doesn't use the Mac's trusted certificates, so the first download of Whisper's small voice-detection model was refused. The app now uses the certificate bundle from the `certifi` package automatically (also for font/texture downloads and the self-test). Nothing changes on Windows.

**What to test (Mac)**
- Update now (it installs one small package), then New project with the same song again. The vocals are already separated (cached), so it goes straight to transcribing.

## Mac fixes from testing (2) — update failed: "torch 2.2.2", numpy C-extensions
**Fixed (Mac)**
- The update's "Install changed dependencies" step ran in Intel mode (Rosetta), because the old launcher was still running that way. pip then installed Intel packages (torch 2.2.2, the last version built for Intel Macs), which clash with the Apple Silicon ones. The setup/update script and the app now always restart themselves natively first, so this can't happen again.

**What to do once (Mac)**: reinstall the Python packages cleanly, see INSTALL_MAC.md → Troubleshooting → "torch 2.2.2". Your projects and settings are not touched.

## Mac fixes from testing (1) — "incompatible architecture (have 'arm64', need 'x86_64')"
**Fixed (Mac)**
- The launcher said "the full setup has not been run yet", even though it had. The app had been started in Intel mode (Rosetta), so it could not load the Apple Silicon libraries that setup installed. The launcher now notices this and restarts itself natively. The app (lyric2resolve.app) also tells macOS to always start natively.
- If it still happens, the launcher explains what to do instead of asking you to run setup again.

**What to test (Mac)**
- Launcher → **Check for updates** → **Update now**, then quit lyric2resolve and open it again → **Start editor** opens the browser. You don't need to run setup again.
- Optional, to also get the new app: double-click `install.command` again.

## Mac (Apple Silicon) — phase 6: Mac test pass + README
**New**
- README has a Mac chapter with what is different on a Mac (MLX, Metal, VideoToolbox, Draft preset, fonts, data folder, `mac-release`).
- VERIFY_LOCAL.md starts with a **MAC FULL TEST PASS**: the order to test everything on your MacBook in about 1-2 hours.

**What to test (Mac)**
- Follow the MAC FULL TEST PASS and paste REPORT_LOCAL.md + your notes into a Claude session.

## Mac (Apple Silicon) — phase 5: Mac integration
**New**
- **Install fonts for Resolve** button on the Library page (Fonts tab): it copies the app's fonts to your user's fonts folder, so Resolve can use them. On Windows it uses the same per-user install as before; on a Mac the fonts go to `~/Library/Fonts`. Restart Resolve afterwards.
- `verify_local` checks for the Mac: PyTorch on the Mac GPU (MPS), MLX Whisper, the video encoder (VideoToolbox/NVENC with a 1-second test encode) and the Resolve scripts folder. The Whisper check says when Whisper had to fall back to the CPU.
- Help texts tell Mac users how to install ffmpeg (Homebrew), Claude Code and Blender.

**Fixed (Mac/Linux)**
- **Stop** in the Assistant now also ends the helper process that Claude Code started, as it already did on Windows.

**What to test**
- Library → Fonts → **Install fonts for Resolve**, restart Resolve: the lyric fonts are in the Text+ font list (Windows and Mac).
- Mac: run `scripts/verify_local.py` and send REPORT_LOCAL.md.

## Mac (Apple Silicon) — phase 4: rendering on the Mac
**New (Mac)**
- Videos are encoded with Apple's hardware encoder (**VideoToolbox**): much faster than before, same Rekordbox/Serato-ready format. If it can't be used, the app falls back to the normal encoder.
- Blender renders on the Mac's GPU through **Metal** (Eevee and Cycles). If Cycles finds no Metal GPU, the warning now says what to do on a Mac.
- The Visuals page picks a render preset that suits your computer: **Draft** on an 8 GB Mac (with a short tip), Standard elsewhere. You can still pick any preset.
- Render instructions and the DJ video guide have Mac notes.

**Changed (all)**
- Windows: nothing changes (NVENC is still used on NVIDIA cards).

**What to test (Mac)**
- Visuals page → Preview render of a song: does it finish, and how long did Draft take for the whole song?

## Mac (Apple Silicon) — phase 3: Whisper on the M chip
**New (Mac only)**
- Whisper runs on your Mac's M chip with Apple's **MLX**: large-v3-turbo by default, which is fast and fits in 8 GB. Forced alignment of your pasted lyrics works too.
- If MLX can't be used, Whisper falls back to the CPU instead of failing, and the log says why.
- Whisper's memory is freed right after transcribing, so the 8 GB is free again for the analysis and Blender.
- Vocal separation uses the Mac's GPU (Metal) through the Mac version of the separation package.

**What to test (Mac)**
- Run setup (installs mlx-whisper), then New project with a song + acapella → "Loading Whisper…" downloads the turbo model the first time, then transcribes. How long for one song?

## Mac (Apple Silicon) — phases 1 + 2: foundation, installer and app
**New (Mac only; nothing changes on Windows)**
- lyric2resolve runs on Macs with an M chip. The app recognises the chip (GPU = "Apple M… (Metal)"), uses PyTorch with the Mac's GPU, finds Homebrew's ffmpeg, Blender in Applications and Claude Code, and picks Mac-friendly defaults (Whisper large-v3-turbo).
- **install.command**: double-click it in Finder to make **lyric2resolve.app** in Applications (with an icon), optionally in the Dock. Then the usual **Run setup** / **Start editor** / **Update now**. See INSTALL_MAC.md.
- Macs update from their own release channel `mac-release`, which only gets changes after the Mac tests passed.
- The test robot now also runs every test on an Apple Silicon Mac.

**What to test (on the Mac)**
- INSTALL_MAC.md from start to finish: lyric2resolve.app opens the launcher, Run setup finishes, Start editor opens the browser.

## Clips, custom 3D scenes with Claude, lyrics as the star (feature update B)
**New**
- **Clips track**: videos on the song's timeline. They are shown as purple regions on the waveform (drag or resize to move them) and in the new **Clips** card, with a preview, start/end and "Go to"/"Snap to bars".
  - **+ Add video/image**: your own file at the playhead or over the selected words. Images become a short video; a video can't be longer than its file.
  - **The clip replaces the lyrics here**: the words sung during that clip are not shown as text. Your words stay in the project, so switch it off to bring the text back.
  - Clips go to **Resolve**: in the FCPXML they are on the video track under the lyrics, and the Resolve script puts clips on V1 and the Text+ lyrics on V2. SRT/CSV/EDL leave out the replaced lyrics too.
- **✨ Make a clip with Claude**: select a moment (e.g. the one-bar break before "Acid"), describe what you want ("3D ACID text, glowing green liquid dripping down, hits on the beat"), and optionally add reference images. Claude gets the exact times, BPM, bars and the music's energy. It writes a Blender scene, the app renders exactly that moment (video only), and the clip lands on the timeline. Not right? Ask Claude in the Assistant card to change it; it re-renders in place.
  - Custom scenes live in your project's `scenes/` folder. Claude starts from a built-in example of exactly that idea (3D "ACID" with dripping glowing liquid), and builds on the audio-reactive helpers (bass/mids/highs/beat, bars, lyrics, glow).
- **Lyrics inside the scene**: on the Visuals page, "Lyrics inside the scene (3D)" (on by default) puts the lyrics as big glowing 3D text into the rendered video, appearing exactly when they're sung, so the render is a finished lyric video.
- **Lyrics as the main focus**: new **Lyric Video**, **Lyric Video Neon** and **Lyric Video Punch** styles (big, centred, heavy type, glow, pop or word-by-word reveal). New projects get a **Look** choice: *Lyric video* (default: Lyric Video style and the FULL styling level with animations) or *Clean captions*. For an existing project, pick a Lyric Video style in the Text style card.
- **Assistant**:
  - **📎 Attach** images, videos or documents (mood boards, logos, example frames, a description). They're saved in the project's `context` folder and ticked files go with your next message; Claude can look at images.
  - Claude may now **read, write and edit files inside the project folder**, including its own notes file, which failed before. Writing outside the project folder stays blocked.

**Fixed**
- Quick changes on the Settings page could get lost (two saves at the same moment overwrote each other). Settings, projects, playlists and the Assistant session are now saved safely, even when several saves happen at once.

**What to test**
- Visuals → Preview render with "Lyrics inside the scene": the words appear in 3D at the right moments.
- Select the break before a drop → ✨ Make a clip with Claude → describe it → the clip appears on the timeline. Export to Resolve: the clip is on V1, the lyrics on V2, and no title during the clip when "replaces the lyrics" is on.
- Add one of your own videos and an image with + Add video/image.
- New project with Look = Lyric video → the export looks like a lyric video, not subtitles.

## Visuals page, your own text, steadier editor (feature update A)
**New**
- **Visuals** button in the editor: render the audio-reactive Blender visuals without the terminal. Pick a scene (spectrum bars, pulsing blob, tunnel, particle field, neon floor grid; each has a short description), the quality (Preview → Ultra), 16:9 and/or 9:16, and the whole song or one section. **Estimate time** first, then **Render**: it runs in the background with a progress bar and time left, **Stop** and continue later. Finished videos play right on the page, and **Open folder** shows them in Explorer. The Ideas page's scene suggestions now link straight to it.
- **+ Text** (or the **T** key): add words, lines or whole sentences Whisper missed. Type the text, set the start and end time (pre-filled from the playhead, and it shows the free time there), and choose one block per line, one block, or one per word. The words are spread over the time range. Instrumental gaps make room automatically. Undo works.
- **Block start / end** can be typed in the Selection card (the words inside move and stretch along).
- **Clearer times**: the waveform ruler shows minutes:seconds, and the play time is bigger.
- **"Missed lyrics" warnings** in the Review card: stretches where the acapella has singing but there are no words (e.g. a missed first sentence), with an **Add text here** button.

**Changed**
- Whisper's voice filter is gentler for singing (0.35 instead of 0.5). The old setting was made for speech and could drop soft or reverb-heavy sung lines, such as a whole first sentence. Adjustable in Settings ("Voice filter sensitivity"; 0 = off).

**Fixed** (several of these were found in a code review)
- The Resolve script couldn't find your export with Microsoft Store Python, and may not have been installed where Resolve looks for it. It now checks both data folders and installs the script so Resolve can see it.
- Applying a preset to one section made the other half of a lyric line that crosses into that section disappear from the export.
- Nudging or retiming a word past its neighbour silently dropped a block from the export. Words can no longer pass each other; you get a clear message instead.
- "Set block time" could refuse a valid change because of rounding.
- New project from the browser now corrects a detected time offset between song and acapella (before, every title could be a little late or early).
- Batch mode no longer overwrites a project you already edited (`--overwrite` if you really want that). Songs with "Voice"/"Vox" in the title are no longer mistaken for acapellas.
- The Assistant can no longer switch the open project behind your back, and a double click can't start it twice.
- After **Stop**, a half-written frame is removed, so continuing the render doesn't produce a broken video.
- Updates no longer fail when the app folder's path contains an apostrophe (e.g. `C:\Users\O'Brien`).
- The editor jumped and resized non-stop after loading a long song at the normal zoom level. The zoomed waveform was pushing the page wider, the waveform redrew for the new width, the page shrank again, and so on.

**What to test**
- Open You're Not Alone at the normal zoom: the screen stays still.
- Visuals → Preview render of one scene → the video plays on the page.
- Add the missed first sentence with **+ Text**, check it in Karaoke and in the export.
- Make a new project of the same song: is the first sentence there now?

## Fixes from testing (5) — "Library cublas64_12.dll is not found or cannot be loaded"
**Fixed**
- New project got through the vocal separation, then failed when Whisper started on the GPU: `cublas64_12.dll is not found`. Whisper's engine (CTranslate2) needs NVIDIA's cuBLAS 12 DLL, which it doesn't include itself.
  - Whisper now looks in PyTorch's own folder. The CUDA 12 PyTorch builds already contain cuBLAS 12 and cuDNN 9, so nothing extra is downloaded.
  - With the CUDA 13 PyTorch build, which only has cuBLAS 13, setup now installs the small `nvidia-cublas-cu12` package (~550 MB). This happens automatically on the next **Update now**.
  - Safety net: if the GPU libraries still can't load, Whisper runs on the **CPU** instead of failing. That is much slower, and the log says why and how to fix it.

**What to test**
- Update now → New project with the same song → the log should NOT show "WARNING: GPU libraries could not be loaded". If it does, the project still completes (slowly); send me the warning.

## Fixes from testing (4) — vocal separation ("No module named 'audioread'")
**Fixed**
- New project with only a song (no acapella) failed in the vocal-separation step: `audio-separator: No module named 'audioread'`. The separation package needs `audioread` but doesn't install it itself; it used to come with librosa, and librosa 1.0 dropped it. It is now in the requirements, and the next **Update now** installs it.
- The backup separator (Demucs) can't be installed next to current PyTorch, and failed with a confusing error. It is now skipped cleanly, and when separation fails the message suggests uploading the acapella.
- Checked in the cloud: a real BS-Roformer separation, and a full song-only New project (separation, Whisper, analysis), both on CPU.

**What to test**
- Update now → New project with only the song → "vocals separated with audio-separator". The first time it downloads the separation model (~600 MB). With your GPU it should take well under a few minutes per song.

## Fixes from testing (3) — "ffmpeg could not convert … No such file or directory"
**Fixed**
- New project failed with `ffmpeg … Error opening input: No such file or directory` although the file was there. Cause: when Python comes from the **Microsoft Store**, everything it writes in `AppData` (and in TEMP) is quietly hidden in a private folder. Python itself still sees those files; ffmpeg, Blender, Resolve and Explorer don't.
  - With Store Python the app now keeps its data in **`C:\Users\<you>\lyric2resolve-data`**, where all programs see the same files. Your settings and projects are copied there automatically the first time. The Whisper model is downloaded once more.
  - Temporary files go there too (`tmp`) for the same reason.
  - `install.bat` warns when it picks Store Python. Python from python.org is still the recommended choice.
  - If ffmpeg still can't open a file that Python can see, the error message now says why and what to do.
- A failed New project no longer leaves a half-made folder behind, which made names turn into "(2)", "(3)".

**What to test**
- Close the launcher completely, open it again (Update now first), then New project with the same song → conversion works.
- Launcher → **Open data folder** now shows your projects.

## Fixes from testing (2) — "Could not load this library: libtorchaudio.pyd"
**Fixed**
- New project failed while loading Whisper with `Could not load this library: …\torchaudio\lib\libtorchaudio.pyd`. Cause: setup installed the CUDA version of PyTorch, but a later step (the vocal-separation package needs `torchvision`) silently replaced it with the newest PyPI PyTorch, which is CPU-only on Windows. The CUDA torchaudio left behind could no longer load.
  - Setup now installs **torch, torchaudio and torchvision together** from the CUDA index and **locks those versions** for all later steps, so nothing can swap them again.
  - Setup now **checks PyTorch** and **repairs it automatically**: a broken or mixed CPU/CUDA set is uninstalled and a matching set is installed again. This runs on your next **Update now**, so your current install gets fixed without doing anything by hand. Expect a ~2-3 GB download.
  - Newer NVIDIA drivers (CUDA 13) now get the newer CUDA 13 PyTorch builds.
- Pinned PyAV below 19: PyAV 19 broke audio decoding in faster-whisper (the next error you would have hit).
- A broken PyTorch now gives a clear message explaining how to repair it, in New project and in `verify_local.py`.

**What to test**
- Launcher → **Update now**: the dependency step reinstalls PyTorch (takes a while) and ends with "PyTorch OK: torch … +cu…, CUDA available".
- Then New project with a real song → it gets past "Loading Whisper" and the project opens.

## Fixes from testing (1) — make a new project in the editor, buttons without a project
**New**
- **+ New project…** (in the Projects window, which opens automatically when nothing is open): choose the full song, optionally the acapella, and paste the lyrics if you have them. Set the name, language and block type, then click **Create project**. It converts the audio, checks the alignment, transcribes (or aligns your lyrics), analyses BPM/sections/gaps and builds the blocks in the background with a progress log, then opens the project. The first time it downloads the Whisper model, which takes a while. Your files are copied into the project folder (`input`).

**Fixed**
- With no project open, the right-hand panel was empty and the buttons did nothing. Now the panel says "No project open — click Projects…", and Play / Play selection / Undo / Redo / Export tell you what to do and open the Projects window.
- After opening a project the status line kept saying "Open a project to start".
- If Whisper isn't installed yet, New project says to run **Run setup** in the launcher instead of failing silently.

**What to test**
- Open the editor → Projects window → **+ New project…** → pick a song (+ acapella) → Create project → after the progress log, the lyrics appear and the right-hand panel works.
- Without a project: click Play or Export → you get a message and the Projects window.

## Phase 19 — One-command pipeline, README, full test pass
**New**
- **One command for a whole song**: `lyric2resolve --song full.wav --acapella vocals.wav [--lyrics lyrics.txt] [--sections sections.yaml] --granularity line --fps 25 --model large-v3 [--render-preset standard] --out ./out`. It converts, checks A/B alignment, transcribes (or aligns your lyrics), analyses BPM/sections/gaps, builds the blocks, exports FCPXML (16:9 + 9:16), the Resolve script and SRT/CSV/EDL, installs the Resolve script, and optionally renders visuals. `--open-editor` opens the result.
- **README.md**: setup, daily use, Resolve import, rendering and DJ use, updates, licenses, limitations, and why there is no `.drp` file.
- **VERIFY_LOCAL.md** now starts with one **full test pass** in the right order.
- verify_local: the **Blender 3-frame render** check now really renders (scene build + 3 headless Eevee frames) instead of saying "not implemented".

**What to test**
- The FULL TEST PASS at the top of VERIFY_LOCAL.md, and paste REPORT_LOCAL.md back into a Claude session.

## Phase 18 — Settings page, Team Funqtion branding, batch mode, update banner
**New**
- **Settings** page (button in the editor): Programs & GPU (ffmpeg, Blender and Claude Code are found automatically, or set a path; shows your NVIDIA GPU), defaults for new projects (frame rate, resolution, layouts, start timecode, styling level, Whisper model, device, language), Assistant options, and update options. Every change is saved immediately.
- **Team Funqtion branding** toggle: the dark Team Funqtion look (near-black, orange `#f68712`, mono type, logo), taken from the funqtion-site repo. It applies to the editor, Library, Ideas, Settings and Karaoke. Off = the normal light theme. It works offline; the brand fonts are used when they are in your font library (JetBrains Mono is now in the font sync list).
- A button that adds the **Team Funqtion text style** (Archivo Black, orange glow) to the open project.
- **Update banner** in the browser: when a new version is on GitHub you see "Update available" with what's new. **Update now** hands over to the launcher, which stops the editor, updates safely (rollback point, automatic rollback on problems) and shows what changed. **Later** hides the banner for this session.
- **Batch mode**: `lyric2resolve batch <folder>` runs every song in a folder through the whole pipeline (convert, transcribe, analyse, blocks, export). Songs and acapellas are paired by name (`Song.mp3` + `Song (Acapella).wav`), and `Song.txt` gives the lyrics. Or use a `queue.yaml`. One failing song does not stop the rest; `batch_report.md` shows the result per song. `--dry-run` only lists what it found.

**What to test**
- Settings: check the tool paths and the GPU line are right; change the frame rate, then start a new project → it uses the new default.
- Switch Team Funqtion branding on: every page turns dark/orange with the logo; off again → light.
- Put 2 songs (+ acapellas) in a folder, run `lyric2resolve batch <folder> --dry-run`, then without `--dry-run`.
- After the next merge: the editor shows the update banner; **Update now** → the launcher updates and reopens.

## Phase 17 — Assistant: Claude Code inside the app (optional)
**New**
- **Assistant (Claude)** card at the top of the editor's side panel: type what you want ("make every chorus one word per block with a glowing style", "check the flagged words", "export both layouts") and Claude does it inside the app. Changes show up live in the lyrics and can be undone with Undo.
- Uses the **real Claude Code CLI with your own login** (Claude Pro), no API key. The app never touches your login.
- One conversation per project that continues after restarting the app. **New conversation** starts fresh. Each project folder gets a `CLAUDE.md` with the project's state plus a Notes part for decisions and style choices, so even a new session knows where things stand.
- The app's own **MCP server** gives Claude tools for: project overview, blocks/words, merge/split/move, fix text/timing, gaps, sanity flags, section presets, styles and styling level, undo/redo, export, preview render + progress + cancel, textures and fonts.
- Honest usage display: shows your Claude usage when the CLI reports it, and a clear notice when you hit the Pro limit. Clear instructions if Claude Code is not installed or not logged in.
- Optional (off by default): register the community **Blender MCP** server so Claude can work in an open Blender. Rendering never depends on it.
- New commands: `lyric2resolve claude status | ask <project.json> "…" | mcp-config <project.json> | reset <project.json>`.
- verify_local: new checks `claude_cli` and `mcp_server`.
- See `docs/ASSISTANT.md`.

**What to test**
- Editor → Assistant card shows "Claude Code 2.x". Send "Give me an overview of this project" → answer appears.
- Ask "merge the first two words into one block" → the lyrics change; Undo reverts it.
- Close and reopen the app, ask "what did I ask you before?" → it remembers.
- Press Stop during a long answer → it stops.

## Phase 16 — Visual ideas, Claude Code prompts and project templates
**New**
- **Ideas** page (button in the editor; or `lyric2resolve ideas <project.json>`): a style brief for your song from the lyrics (themes and mood), BPM, key, energy and sections, with 2-3 visual concepts per section (neon grid, tunnel, liquid blob, particles, lava cracks, rain on glass, chrome, low-poly…) and text-animation suggestions. Each concept shows the render command for the matching scene template.
- Ready-to-paste **Claude Code prompts** for a Blender (bpy) project and for a three.js/WebGL scene, with BPM, section timings, mood, palette, duration, fps/resolution/aspect, your available CC0 textures and all render/DJ-delivery requirements. Works without any AI; the Claude link (next phase) can do more.
- **Project templates**: save a song's look (text styles, per-section styling, band→visual mapping, render preset, layout and text settings, styling level) and apply it to another song with one click (undoable).

**What to test**
- Open Ideas on a real song: do the moods/concepts make sense? Copy the Blender prompt into Claude Code.
- Save a template on one song, open another song, apply it → styles/settings change, lyrics stay.

## Phase 15 — Rendering the visuals (headless Blender) + DJ-ready MP4s
**New**
- `lyric2resolve render <project.json> --template <name> --render-preset <preset>`: builds the Blender scene, renders it in the background (no Blender window) and makes an MP4 with your full song inside, ready for Rekordbox/Serato.
- Presets: **PREVIEW** (540p, 15 fps, first 25 s — check the look fast), **DRAFT** (720p), **STANDARD** (1080p Eevee, bloom, denoise), **HIGH**, **ULTRA** (4K Cycles) and **CUSTOM** (`--height`, `--engine`, `--samples`, `--fps`).
- Before rendering it renders 3 test frames and tells you how long it will take and how much disk space the frames need; it warns when a render will take more than 3 hours and suggests time savers.
- Progress with frames done and time left; Ctrl+C cancels and running the same command again **resumes** (finished frames are skipped).
- Uses your NVIDIA GPU (OptiX, else CUDA) for Cycles, with a clear warning if it has to fall back to the CPU; finds Blender automatically and explains how to install it if missing.
- Time savers: render only some sections (`--sections chorus drop`), render at 30 fps (`--fps 30`), or render 1080p and upscale in Resolve.
- Every render folder gets a beginner-friendly `RENDER_INSTRUCTIONS.md` (settings and why, CLI and GUI steps, time estimates, preview first, resuming, importing into Resolve, troubleshooting).
- MP4 format checked against the Rekordbox and Serato specs: H.264 High, constant frame rate, keyframe every ≤25 frames, AAC 320 kbps. Portrait/4K renders also get a `_dj.mp4` that fits Rekordbox (max 1920×1080).
- `docs/DJ_VIDEO_GUIDE.md`: the exact Resolve Deliver settings for DJ use (16:9 and 9:16) and how to check sync on the decks.

**What to test**
- `render … --render-preset preview` on a real song → MP4 plays in Rekordbox/Serato with the song, in sync.
- Start a STANDARD render, stop it with Ctrl+C, start again → it continues.

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
