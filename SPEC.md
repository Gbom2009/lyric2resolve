# SPEC.md — lyric2resolve (verbatim specification as given by the user)

You are starting a large project that is built in phases by Claude Code sessions in the cloud, working directly on a GitHub repository (there is no local working folder). In THIS session: save this entire specification verbatim into SPEC.md as your very first action, do "Phase 0: planning" (section 14), continue directly into Phase 1, then follow the working mode and rules in section 14 for all further phases.

PROJECT: "lyric2resolve" - Windows app (Python, NVIDIA GPU/CUDA). Turns a song plus its acapella into a DaVinci Resolve timeline with lyrics as text clips synced to the song. Includes a full browser-based editor, a karaoke mode, audio-reactive Blender visuals (headless rendering), texture/font libraries, a Claude Code link, and an auto-updater with its own launcher window. Keep modules separate: updater/launcher, audio, analysis, transcription, editor (backend + frontend), export, karaoke, visuals/render, assets, claude_link.

=== 0. DEVELOPMENT ENVIRONMENT CONSTRAINTS (read first) ===
- Development happens in cloud Claude Code sessions on a Linux sandbox: CPU only, no Windows, no NVIDIA GPU, no DaVinci Resolve, no Rekordbox/Serato, limited network (usually package registries and GitHub only). The app TARGETS Windows with an NVIDIA GPU on the user's PC.
- Therefore: write cross-platform code (pathlib, no hardcoded paths, no shell-specific assumptions), isolate hardware/OS-specific code behind small interfaces so the rest is unit-testable on Linux/CPU, and mock heavy models in tests (Whisper, separation, Blender, ffmpeg when absent). Real-model tests are marked (e.g. pytest marker "local") and skipped in the cloud. GUI code (Tkinter) must keep its logic separate from the window so the logic is unit-testable without a display.
- Everything that cannot be verified in the cloud must be listed in VERIFY_LOCAL.md and covered by scripts/verify_local.py (a script I run on my Windows PC): it checks Python/venv, ffmpeg, git, GPU/CUDA/torch, Whisper model load, a short transcription of a bundled tiny test clip, vocal separation smoke test, Blender detection and a 3-frame headless render, asset sync API reachability, FCPXML validity, and writes a short report (REPORT_LOCAL.md / JSON) I can paste back into the session. Sessions read my pasted report and fix issues.
- Add GitHub Actions CI (Linux): run the unit tests on every push/PR. Never claim something works on Windows/GPU unless it was verified by my local report.

=== 1. INPUTS ===
- Track A: full song (mp3/wav/flac/m4a); goes on the Resolve timeline as the audio.
- Track B: acapella; the ONLY file Whisper analyzes.
- Default two-track mode, no separation. Convert both to 44.1kHz wav with ffmpeg.
- Check A/B alignment via cross-correlation: estimate offset in ms, warn, optionally auto-compensate.
- Optional fallback: if only the full song is given, separate vocals with python-audio-separator (best free vocal model, e.g. BS-Roformer/MDX23C; Demucs htdemucs_ft as backup); cache stems.
- Instrumental: create it from the full song minus the acapella (or via separation if only one track) and cache it (used by karaoke mode).
- Optional lyrics field/file: if provided, use stable-ts forced alignment (model.align) on the acapella and keep my line breaks; if empty, transcribe.

=== 2. TRANSCRIPTION ===
- OpenAI open-source Whisper via faster-whisper or stable-ts, default large-v3 (selectable), CUDA float16, word_timestamps=True, VAD on, language auto-detect with manual override, condition_on_previous_text=False.
- Editable project JSON: words (text, start, end, confidence), blocks, sections, instrumental gaps, settings. Autosave.

=== 3. MUSIC ANALYSIS ===
- librosa/madmom: BPM, beat and downbeat grid, section boundaries (verse/chorus/drop via novelty + energy), key, energy curve. Beat grid + sections become markers in exports.

=== 4. FULL BROWSER EDITOR (not a simplified version; build the full thing) ===
Local web app: FastAPI backend + vanilla JS or React frontend, wavesurfer.js, opened with one command.
- Data model: WORDS are atomic (text, start, end, confidence). BLOCKS are ordered groups of consecutive words. Export reads only from blocks.
- Click-drag/shift-click to select consecutive words; MERGE selected words into one block (start = first word start, end = last word end); SPLIT a block at any word boundary into multiple blocks keeping each word's original timing; move words between neighbouring blocks; inline text edit; timing nudge; undo/redo; play selection/from cursor; keyboard shortcuts.
- Presets as a starting point, then manual edits: WORD, LINE, PHRASE (N words), AUTO (split on pauses > X s), applicable per section (e.g. verse = LINE, chorus = WORD) via a section table and YAML config.
- Text options: UPPERCASE/lowercase/Title Case, strip punctuation, max chars per block, merge blocks shorter than N frames, hold until next or fade after N ms, pre/post-roll ms, global sync offset, min clip duration.
- INSTRUMENTAL GAPS: auto-detect long vocal gaps and show them as regions in the editor. I can also add, resize and remove gap regions manually. No icon/text is generated for gaps: in the Resolve export the timeline must contain NO elements (no clips, no titles) during gaps.
- ROUGH-CUT SANITY CHECK: flag (do not auto-fix) words likely wrong from Whisper: very short/overlapping/zero-length timings, low confidence, suspicious repeats, words far outside the vocal activity. Show a review list that jumps to each flagged word.
- SAFE-AREA / LINE-LENGTH WARNING: warn (do not change anything) when a block is probably too long for the chosen font size, resolution and aspect ratio (16:9 and 9:16).
- Frontend tests: where practical, add headless browser tests (e.g. Playwright) for select/merge/split in CI; keep a manual test checklist in VERIFY_LOCAL.md for what cannot be automated.

=== 5. EXPORT (only after I press Export, generated from the edited blocks) ===
- Both layouts from the same project: 16:9 (default 1920x1080) AND vertical 9:16 (1080x1920) for Reels/TikTok, selectable at export or both at once, with text repositioned/wrapped for each. Vertical is supported from the first working export, not added later.
- Primary: FCPXML (use the version Resolve imports best): FULL SONG (Track A) on an audio lane, one title clip per block (Basic Title with the text) on a video track, frame-accurate at configurable fps (23.976/24/25/29.97/30/50/60), configurable start timecode (default 01:00:00:00), beat/section markers, and no clips during instrumental gaps. Document what to do if titles import as generic titles instead of Text+. Since Resolve cannot run in the cloud, validate against the FCPXML DTD/schema and add the actual import test to VERIFY_LOCAL.md.
- resolve_build_timeline.py to run via Workspace > Scripts in Resolve (works in free): creates the timeline, adds Track A, inserts real Fusion Text+ clips at the right frames, applies styling per the chosen STYLING LEVEL (section 6). Verify the Resolve scripting API calls against the official docs; unit-test the generator against a mocked Resolve API; real run goes in VERIFY_LOCAL.md.
- Also: SRT (line and word versions), CSV (start/end/text), EDL with markers.
- DJ-VIDEO EXPORT GUIDE: The visuals are played directly on DJ decks (Rekordbox and Serato video mode: an MP4 with high-quality audio embedded, output via HDMI). Therefore: (a) every video the app renders itself (Blender backgrounds, karaoke previews) gets the full-quality song muxed in via ffmpeg (H.264 MP4 + high-bitrate audio, e.g. AAC 320 kbps; verify the video/audio formats and limits that Rekordbox and Serato currently accept before coding, and keep the video constant-frame-rate); (b) generate a short guide with the exact Resolve Deliver settings for the final render (codec, bitrate, audio codec/bitrate/sample rate, resolution, fps) for DJ use, 16:9 and 9:16 variants, and how to verify the audio is in sync on the decks.
- README note: .drp project files cannot be generated and why.

=== 6. TEXT STYLING + FONTS (how far the app generates in Resolve is a setting) ===
STYLING LEVEL setting: (1) BASIC: plain Text+ with a default font/size/color; (2) STYLED: apply a style preset (font, size, fill color, outline, shadow/glow, position, per-section variants); (3) FULL: styled + simple animations (fade/pop/slide/per-word reveal) via the Resolve script where the API allows.
- Style presets editor (font, color, outline, shadow, glow, alignment) with live preview in the editor; one style per section.
- Font library: fetch open-source fonts (Google Fonts, only OFL/Apache-licensed families verified from their license metadata) via `assets sync` on my PC into assets/fonts, with a manifest + license credits, and an installer that copies them to the user's Windows fonts folder so Resolve can see them. Include a preview picker. Optional: user's own fonts in assets/fonts/custom. (Downloads happen on my PC, not in the cloud; keep a tiny bundled fallback font list in the repo only if its license allows redistribution.)
- Project templates: save/load a template (text style, section styling, band-to-visual mapping, render preset, layout settings, styling level) and apply it to a new song.

=== 7. KARAOKE MODE (inside the app; NOT an export option) ===
- Separate "Karaoke" page: play a saved project fullscreen (or on a second screen) with word-by-word highlighting driven by word timings, current + upcoming line shown, instrumental gap countdown/indicator, large readable text.
- Audio: plays the instrumental by default with a VOCAL VOLUME slider that fades the original vocals in/out (mix instrumental + acapella in the browser via Web Audio).
- Karaoke night: a saved playlist/queue of projects with next/previous, reorder, and quick search. Keyboard shortcuts (space, next, vocal volume). Works fully offline from saved projects.

=== 8. VISUALS + PROMPT GENERATOR ===
- "Visual ideas" tab builds a style brief from lyrics (themes, mood), BPM, key, energy curve, sections. Per section: 2-3 visual concepts (particles, tunnel, liquid, neon grid, low-poly, etc.) and text-animation suggestions.
- Generates ready-to-paste Claude Code prompts (a) for a Blender (bpy) project/script (beat-synced, my fps/resolution/aspect ratio) and (b) optionally a three.js/WebGL scene. Each prompt includes BPM, section timings, mood, palette, duration, available textures (section 10) and render requirements (section 9). Template-based by default.
- The in-app Claude link (section 11) can also generate richer briefs, but must be optional; the app works without it.

=== 9. RENDERING ===
- Blender HEADLESS route first: the app runs `blender -b ... -a`, shows progress (parse frame output), has cancel, a low-res preview mode first, resume (skip existing frames), GPU (OptiX/CUDA) auto-detection with CPU fallback + warning, and automatic ffmpeg encoding of PNG sequences to MP4 with the full song muxed in (section 5 DJ guide). Detect Blender install path; give install instructions if missing. In the cloud, test the scene-generation scripts with the `bpy` pip module or a mocked bpy if installation is not possible; real renders are verified locally.
- Every generated visual (Blender file/script, three.js scene) also gets its own RENDER_INSTRUCTIONS.md for beginners: prerequisites (Blender version, GPU setup, ffmpeg), recommended settings and why (Eevee vs Cycles, samples, resolution, fps matching the Resolve timeline, frame range, color management, output format), exact CLI and GUI steps, render time estimates, quick preview first, resuming, how to import into Resolve (place on V1 under the text, match fps/resolution, loop/stretch, sync to markers), and a troubleshooting list.
- Audio-reactive: compute band energies with librosa (default bass 20-150 Hz, mids 150-2000 Hz, highs 2000-12000 Hz, plus RMS and onset/beat strength), smooth with attack/release, per-band gain and normalization, sampled at project fps. Write them into the .blend via bpy as keyframes/drivers (document manual "Bake Sound to F-Curves" as alternative). Store curves as JSON/CSV next to the .blend so they can be re-tuned without re-analysing.
- Mappable targets per band in YAML and UI: emission color/strength, scale, displacement, position/rotation, particle rate, camera shake, light intensity. Default: bass = glowing orange + scale pulse, mids = glowing blue, highs = glowing green + sparkles; all configurable. Scene templates: spectrum bars, pulsing blob, tunnel, particle field, reactive floor grid; section-aware intensity/palette.
- Render presets (UI + CLI --render-preset): PREVIEW (480p/540p, Eevee, minimal samples, 12-15 fps, first 20-30 s), DRAFT, STANDARD (1080p Eevee, medium, bloom, denoise), HIGH, ULTRA/4K, Custom (resolution, fps, aspect ratio, engine, samples, denoise, frame range, color management, output). Before rendering: render a few test frames, extrapolate estimated time, frames, disk usage; warn if long. Time savers: render selected sections only, render at 30 fps, render 1080p and upscale in Resolve. Both 16:9 and 9:16 camera setups.

=== 10. TEXTURE LIBRARY (free, CC0) ===
- assets/textures with `lyric2resolve assets sync` (run on my PC): downloads a curated starter pack of CC0 PBR textures and HDRIs from Poly Haven (public API, api.polyhaven.com) and ambientCG (public API). Verify current API endpoints/docs before coding. No keys, polite rate limits, resumable, verified downloads. Textures are NOT committed to git (gitignored data folder); only the manifest/curation list is.
- Categories suited to glowing audio-reactive scenes: dark/brushed metal, carbon fiber, concrete, cracked rock/lava-like, rubber/leather, sci-fi panels, grids/tiles, glass, fabric, ice, plus a few dark neutral HDRIs. Default 1K-2K (selectable up to 4K), full PBR sets.
- manifest.json (name, source, URL, author, license, resolution, path) + auto-generated CREDITS.md. Only include assets whose CC0 license is confirmed from the API/asset page.
- User textures in assets/textures/custom; texture browser tab. Blender material builder uses textures with audio-reactive emission layered on top (emission mask from height/noise/crack pattern); .blend files pack textures or use relative paths. Additional procedural/tileable textures generated on demand (bpy nodes, numpy/PIL).

=== 11. CLAUDE CODE LINK (runs on my PC; uses my Claude Pro login, no API key) ===
- In-app "Assistant" panel that runs the REAL `claude` CLI (already installed and logged in by me on my PC) as a background subprocess, e.g. `claude -p` with streaming JSON output, using a saved session id per project and resuming it each time (`--resume`), so the conversation and memory continue across app restarts. Verify the current CLI flags and headless/session behavior from the docs before coding. Do NOT read, copy or store my login tokens; do not use any API key; if the CLI is missing or not logged in, show clear instructions.
- Also keep a per-project CLAUDE.md / notes file with the project state, decisions and style choices so a fresh session can pick up context even if the session is lost.
- The app exposes its own MCP server (stdio) with tools: get_project, list/edit blocks and words, add/remove gap regions, get sanity flags, apply section presets, set styles, trigger exports, run a preview render, read render progress, list textures/fonts. Register it for the background session via a generated MCP config file so Claude can iterate inside the app.
- Also write the foundation for a Blender MCP connection (optional): config + docs for the community Blender MCP server, clearly marked as optional and to be verified against its repo; headless rendering never depends on it.
- Show usage honestly in the UI: Claude Pro has usage limits, so show a notice when the CLI reports a limit; the app works fully without the Assistant. Unit-test with a fake `claude` executable; real use goes in VERIFY_LOCAL.md.

=== 12. UI / BRANDING / BATCH / SETTINGS ===
- Default theme: your own clean, high-contrast, usable design for the app (readable, not too dark).
- Settings toggle "Team Funqtion branding": ON applies Team Funqtion colors/fonts/logo from github.com/gbom2009/funqtion-site (look in the repo for the brand colors, fonts, logo, and a VIDEO-BRAND.md style guide if present; if the cloud session cannot access it, add a TODO and the brand tokens as a config file I can fill in); OFF uses the default usable theme. Meant for presenting to others, not daily use.
- Batch mode: simple queue of songs run through the pipeline (transcribe -> blocks -> export). Keep it minimal; it only needs to be smoke-tested to confirm it works.
- Settings page: paths (Blender, ffmpeg), GPU info, default fps/resolution, styling level, theme/branding toggle, Claude link status, updater settings.

=== 13. QUALITY ===
- CLI: `lyric2resolve --song full.wav --acapella vocals.wav [--lyrics lyrics.txt] [--sections sections.yaml] --granularity line --fps 25 --model large-v3 --render-preset standard --out ./out`, plus commands to open the editor, sync assets, run batch, check for updates.
- One-click Windows setup script (venv, torch+CUDA, ffmpeg check, asset sync), requirements files, clear logs/errors. Written and unit-tested for logic in the cloud, executed for real on my PC.
- Tests for timecode/frame math, A/B offset detection, block merge/split, gap handling (no clips in gaps), FCPXML generator (validate XML), 16:9 and 9:16 layout, band-energy analysis, asset license filter, sanity-check flags, karaoke timing data, updater logic (section 15). GitHub Actions CI runs them.
- README: setup, usage, Resolve import steps, DJ video guide, rendering workflow, licenses, update workflow, limitations.

=== 14. PHASED BUILD, TEST GATE, AND ROLLING HANDOFF BETWEEN TWO CLAUDE CODE ACCOUNTS ===
HOW THIS PROJECT IS BUILT: I alternate between two Claude Code Pro accounts (a personal one and a school one). A session works until it hits its usage limit; I then paste the latest handoff prompt into a session on the OTHER account, which continues, and so on back and forth until the app is finished. Both accounts have access to the same GitHub repo. A session cannot know when its limit will hit, so the project must ALWAYS be in a resumable state. THE REPO IS THE SOURCE OF TRUTH: if a pasted handoff text and the repo disagree, trust the repo (main branch, open PRs, PROGRESS.md, git log).

GIT WORKFLOW (I never test a pull request; I merge it first, then test main):
- main only contains merged, CI-passing work. Never push directly to main, except the very first initial commit (Phase 0 planning docs) if the repo is empty, because a PR needs a base branch.
- Every phase gets its OWN branch cut from the latest main (e.g. phase-05-editor-api). Open a DRAFT pull request into main at the first push of that branch (so the next account can see unfinished work), commit small and often, push after every commit, and mark the PR ready when the phase is done and CI is green.
- Every phase PR adds a plain-language entry to CHANGELOG.md (what is new, what changed, what to test) and puts the same summary in the PR description. The updater shows this to me after each update.
- Fixes and changes I request after testing go into the NEXT phase's branch/PR (as clearly labelled commits at the start: "Fixes from testing phase N"), together with the next phase's work. Always start a new branch from the freshly updated main after I have merged the previous PR. If my feedback is urgent or blocks testing, you may make a separate small "fix" PR instead.

PHASE 0 = PLANNING ONLY (no features, nothing for me to test; no test gate; continue straight into Phase 1):
1. Save this whole spec verbatim into SPEC.md.
2. Write PHASES.md: split the build into about 14-20 SMALL, self-contained phases. Each phase must be completable well within one session (budget: at most ~6-8 files changed, ~one module, one test file; if bigger, split it). Each phase lists goal, files, acceptance tests, a TEST CHECKLIST FOR ME (concrete steps on my PC with expected results) and "needs user input" flags. Required order and content:
   (1) Skeleton + UPDATER/LAUNCHER (section 15): minimal package layout, data-folder convention, CHANGELOG.md, .gitignore, CI, the launcher/updater window, install script + desktop shortcut, tests. This is the first thing I install.
   (2) Setup script (venv, torch+CUDA, ffmpeg check, requirements split) + scripts/verify_local.py scaffold + settings/config module (the updater re-runs the setup update step when requirements change).
   (3) Audio inputs, alignment check, ffmpeg conversion, instrumental stem.
   (4) Whisper transcription + forced alignment + project JSON.
   (5) Music analysis + gap detection + sanity checks.
   (6) Editor backend API (blocks/words, merge/split, undo/redo).
   (7) Editor frontend part 1 (waveform + word selection). Launcher now opens the editor in the browser.
   (8) Editor frontend part 2 (merge/split UI, gaps, flags, warnings).
   (9) Styling model + presets + fonts library.
   (10) FCPXML export (16:9 and 9:16, no clips in gaps).
   (11) Resolve script export + SRT/CSV/EDL + styling levels.
   (12) Karaoke mode.
   (13) Asset sync (textures) + texture browser.
   (14) Audio-reactive Blender generator + scene templates.
   (15) Headless render + presets + ffmpeg mux for DJ video + RENDER_INSTRUCTIONS.
   (16) Visuals/prompt generator + project templates.
   (17) Claude link (CLI subprocess + MCP server + Blender MCP foundation).
   (18) UI settings, branding toggle, batch mode, in-app update banner/settings (hooks into the updater from Phase 1).
   (19) Full test pass, README, DJ guide, consolidated VERIFY_LOCAL.md.
3. Write PROGRESS.md: MODE (gated or continuous), phase status table (planned / in progress / PR open / merged / tested-OK / needs fixes), a "CURRENT STEP LOG" for the phase in progress (what is done, what is next, exact file/function), decisions with reasons, open issues, my test feedback per phase, pending VERIFY_LOCAL items, and a place where I paste local verification reports.
4. Write HANDOFF_PROMPT.md (requirements below). Commit and push Phase 0 docs (initial commit to main if the repo is empty, otherwise via a PR), then start Phase 1.

WORKING MODES (stored in PROGRESS.md as MODE; default GATED):
- GATED (default). After each completed phase from Phase 1 on (tests pass, CI green): update PROGRESS.md, CHANGELOG.md and HANDOFF_PROMPT.md, mark the PR ready, then print in the chat: (1) one clear line "Phase N done, PR #X is ready"; (2) the steps for me: merge the PR into main, then update my installed copy (from Phase 1 on: open the launcher/shortcut and click Update; for Phase 1 itself the first-time install steps from INSTALL.md), then run the phase's TEST CHECKLIST (concrete steps + expected results, including `scripts/verify_local.py` when relevant); (3) "Reply with what works and what doesn't, or say 'continuous'"; (4) the full current handoff prompt in one code block. Then STOP and WAIT. Do not start the next phase until I reply. When I reply: pull the updated main, record my feedback in PROGRESS.md, create the next branch from main, apply my fixes first (labelled commits), then build the next phase, and repeat.
- CONTINUOUS. If my message (including the last line of a pasted handoff prompt) contains "continuous" / "use continuous" / "go continuous", set MODE=continuous in PROGRESS.md. In this mode do NOT wait for tests: work through the phases one after another on a single branch "continuous-<date>" with one PR into main that you keep updating (phase-labelled commits and CHANGELOG entries), print a short status line after each phase plus the handoff prompt, and keep going until the session budget ends. I will merge and test everything later. If I say "gate" / "gated" / "stop continuous", switch back: finish the current step, mark the PR ready, and follow GATED from there. After I merge a continuous PR, new work starts from fresh main again.
- Both modes: if a phase needs my input or something only my PC can provide (test song + acapella, Resolve version, Blender path, GitHub details, running scripts/verify_local.py), mark it "waiting for user" in PROGRESS.md, say so in the chat and in the handoff, and if in CONTINUOUS mode skip to the next phase that does not depend on it.

WORKING RULES FOR EVERY SESSION:
- A session starts by reading SPEC.md, PROGRESS.md, PHASES.md and HANDOFF_PROMPT.md, running `git fetch`, `git log`, and checking open PRs and which branch/step is current. A session that already has older context must re-read the repo before acting, because the other account may have changed things.
- Commit small and often (WIP commits are fine on the phase branch) and push after each commit. Keep the PROGRESS.md CURRENT STEP LOG updated at each meaningful step, so that if the usage limit hits mid-phase the next session can resume exactly where this one stopped.
- If you notice you are running low on budget, checkpoint the current step, commit/push, update PROGRESS.md and print the handoff immediately.
- Keep the way you interact with me consistent in both accounts: short, specific questions (multiple choice where possible), concise progress reports about outcomes (no long recaps of steps), casual tone; I may write Dutch, so reply in the language I write in.

HANDOFF_PROMPT.md REQUIREMENTS (rewritten after every phase and at every checkpoint; self-contained so it works on an account with no memory of this project; compact, because details live in the repo files): what the project is and where everything lives (SPEC.md, PHASES.md, PROGRESS.md, CHANGELOG.md, VERIFY_LOCAL.md, CLAUDE.md, scripts/verify_local.py); the repo and branch workflow above, with the exact current state (completed/merged phases, open PR number and branch, current phase and exact step, whether we are waiting for my test result, which mode is active, what is waiting for my input); architecture and key decisions with reasons; the cloud-development constraints and the verify_local report loop; the working modes and rules above including the interaction style; how the installed copy on my PC updates itself from main via the launcher; known limitations and open issues; and the first actions for the new session (fetch, read the files, summarize understanding back to me in a few lines, then continue with the current step or wait for my test feedback). End the file with a line telling the reader that the user may append a mode line such as "use continuous" below the pasted prompt.

WHEN ALL PHASES ARE DONE: write a final HANDOFF_PROMPT.md marked "PROJECT COMPLETE" with maintenance instructions, and tell me what to verify on my PC.

=== 15. LAUNCHER + AUTO-UPDATER (built in PHASE 1; no GitHub Releases needed) ===
GOAL: after Phase 1 I install ONCE; from then on every merged PR is delivered by opening the app's launcher and clicking Update. Phase 1 is therefore the first thing I can download, even though there is no editor yet.
- First-time install: INSTALL.md + install.ps1/install.bat in the repo: prerequisites (Git for Windows, Python 3.x with Tcl/Tk), `git clone` of the repo into a folder of my choice (a plain zip download cannot update because it has no git history; say so), create a venv, install the minimal launcher requirements, create a Desktop/Start-menu shortcut to the launcher (pythonw, no console window). Private repo: use existing git credentials (Git Credential Manager) or a fine-grained read-only token; show clear instructions on auth failure; never store or log tokens in the repo.
- Launcher (the app's entry point, Tkinter window, stdlib only so it works before any heavy dependency is installed): on every start it checks for updates in the background (git fetch with a timeout; silent failure when offline) comparing local HEAD with origin/<configured branch, default main>. If up to date, it goes straight on to start the app; until the real editor exists (Phase 7) it shows a small status window ("No app interface yet - version <hash/date>, up to date") with Check now / Roll back / Open data folder.
- If an update is available: show a window "Update available" with the new CHANGELOG.md entries and commit messages (the changelog in plain language is the main thing I read), and buttons "Update now" / "Later". Never update without my confirmation.
- On "Update now": a progress bar with named steps: (1) fetch; (2) rollback tag of the current commit; (3) pull with --ff-only (or fetch + hard reset to origin/<branch> if the working tree is clean; refuse and explain if there are local modifications); (4) install changed dependencies (compare hashes of the requirements files; run the project's setup update step once it exists in Phase 2; show that this can take a while); (5) rebuild the frontend if a build step exists; (6) quick self-check (import test); (7) restart/launch the app. On any failure automatically roll back to the previous commit and show what went wrong.
- The updater must update ITSELF safely: because Windows cannot overwrite running files, the update work runs in a separate process started from a temporary copy of the updater, while the launcher window closes (or the temp copy shows the progress UI).
- After a successful update show a "What changed" screen: the new CHANGELOG.md entries (plain language: what is new, what to test), the commit list, and a short summary of changed files. Then "Start app" (or "Close" while no app UI exists yet).
- "Removes the old version" = the pull replaces the old files; the previous commit stays recoverable via the rollback tag (settings/launcher: "Roll back to previous version"). User data (projects, assets, settings, caches, models) lives outside the code folder and is never touched.
- Only fetch from the configured remote and branch, and never run anything except git, the project's pip/setup commands, and the app's own start command.
- Settings (config file now, UI later): repo URL/remote, branch, check at launch (on/off), check at Windows login (on/off; optional Startup entry/Task Scheduler with a notification, off by default), current version, "Check now", "Roll back".
- Keep logic (version comparison, behind/ahead/diverged detection, changelog extraction, requirements change detection, dirty-tree refusal, rollback, step runner) separate from the Tkinter window so it is unit-testable in the cloud; use a temporary local git repo as a fake remote in tests. The real Windows flow (install, shortcut, update with progress bar, self-update, rollback) goes in VERIFY_LOCAL.md and in the Phase 1 TEST CHECKLIST.
- Phase 18 later adds the in-app update banner/settings in the browser UI, calling the same updater logic.
