# VERIFY_LOCAL.md — things only your Windows PC can verify

The cloud sessions run on Linux without GPU/Windows/Resolve/Blender. Everything below must be checked on your PC.
From Phase 2 on, `scripts/verify_local.py` automates most of it and writes REPORT_LOCAL.md — paste that into the session.

## FULL TEST PASS (start here — about 1-2 hours, in this order)
The per-phase lists below hold the details; this is the route through them. Tick what works, note what doesn't,
and paste REPORT_LOCAL.md + your notes into a Claude session.

1. **Install + update** (Phase 1, 2): merge PR #2 → open the launcher → *Update now* → it runs the dependency step
   (first time: *Run setup*, can take 10-30 min for PyTorch/CUDA). Launcher shows "up to date" and opens the editor.
2. **Self-test**: `.venv\Scripts\python scripts\verify_local.py` → REPORT_LOCAL.md. Expected all ✅ except optional
   items: python, tkinter, git, ffmpeg, gpu, torch_cuda, blender, asset_apis, audio_offset, vocal_separation,
   whisper_model_load, whisper_tiny_clip, fcpxml_validity, claude_cli, mcp_server, blender_3_frame_render.
3. **Assets**: `.venv\Scripts\python -m lyric2resolve assets sync` then `assets install-fonts` (Phase 9, 13).
4. **One real song end to end** (Phase 3-5, 19):
   `.venv\Scripts\python -m lyric2resolve --song "<song>" --acapella "<acapella>" --lyrics lyrics.txt --render-preset preview`
   → offset printed, project + exports + preview MP4 created. Without `--lyrics` once too (pure Whisper).
5. **Editor** (Phase 7, 8, 9, 17, 18): open the song in the editor; merge/split/move/edit/nudge/undo; add a gap; click
   review flags; change a section preset; style + styling level; Assistant: ask it to change something; Settings page;
   branding on/off.
6. **Resolve** (Phase 10, 11): import both FCPXMLs; run the build script with STYLED and FULL; nothing in gaps;
   titles on the right words at 25 and 29.97 fps.
7. **Karaoke** (Phase 12) on a second screen with the vocal slider and a 2-song queue.
8. **Visuals + DJ** (Phase 14, 15): STANDARD render of one template; the MP4 plays in sync on Rekordbox and Serato;
   the Resolve Deliver settings from docs/DJ_VIDEO_GUIDE.md give a deck-playable file.
9. **Batch** (Phase 18): 2-3 songs in a folder → `lyric2resolve batch <folder>`.
10. **Update banner + roll back** (Phase 1, 18): after the next merge use the banner's *Update now*; then *Roll back*
    in the launcher and update again.

## Phase 1 — install + launcher + updater
CI already runs `install.ps1 -NoShortcuts` and all updater tests on a Windows runner; still check by hand:
- [ ] `install.bat` creates `.venv` and the Desktop + Start-menu shortcuts.
- [ ] Shortcut opens the launcher **without** a console window.
- [ ] Status text shows the version (hash + date) and "up to date"; from Phase 7 on the editor starts and opens in the browser.
- [ ] "Open data folder" opens `%LOCALAPPDATA%\lyric2resolve`.
- [ ] Offline (Wi-Fi off): launcher still opens, says offline, no error popup.
- [ ] After a PR is merged: "Update available" window with changelog + commits; "Later" changes nothing.
- [ ] "Update now": launcher closes, a separate progress window runs the steps (self-update from a temp copy), then "Update complete" with what changed; "Close" reopens the launcher showing the new hash.
- [ ] "Roll back": goes to the previous hash; next start offers the update again.
- [ ] Local edit in a code file → update refused with a clear message; files untouched.
- [ ] Private repo auth: if Git asks to sign in, Git Credential Manager handles it; no token stored in the app folder.
- [ ] (optional) `launcher.pyw login-check on` → after Windows login, nothing visible unless an update exists.

## Phase 2 — setup + verify script
- [ ] `setup_windows.bat` completes; torch installed from the CUDA index matching the driver (shown at the start).
- [ ] faster-whisper/ctranslate2 needs CUDA 12 + cuDNN 9 DLLs; they normally come with the CUDA torch wheels. If transcription later complains about `cudnn*.dll`, report it.
- [ ] Optional `audio-separator[gpu]` may fail to install (warning only); report the message.
- [ ] `scripts/verify_local.py` writes REPORT_LOCAL.md: expect ok for python/tkinter/git/ffmpeg/gpu/torch_cuda/asset_apis; blender ok or warning.
- [ ] Updating through the launcher after this change runs the dependency step (progress shows step 4 for a long time) and then succeeds.

## Phase 3 — audio
- [ ] `audio-check` on a real song + acapella: offset ≈ 0 ms, confidence shown, instrumental wav sounds like the song without vocals.
- [ ] Shift the acapella in an editor by ~100 ms → `audio-check` reports ≈100 ms "later"; `--compensate` fixes it.
- [ ] Without acapella: separation works on GPU (verify_local `vocal_separation` ok). Confirm the default model name `model_bs_roformer_ep_317_sdr_12.9755.ckpt` exists in your audio-separator version (`audio-separator --list_models`).

## Phase 4 — transcription
- [ ] verify_local: `whisper_model_load` ok (large-v3 on cuda/float16; first run downloads ~3 GB into the data folder `models\whisper`).
- [ ] verify_local: `whisper_tiny_clip` hears ≥4 of the key words and forced alignment returns ~9 words.
- [ ] `transcribe` on a real song: word timings look right when played (spot-check 3 words); `--lyrics` keeps line breaks.
- [ ] `pytest -m local` runs the real-Whisper test.

## Phase 5 — analysis
- [ ] `analyze` on 2-3 real songs: BPM correct (or exactly half/double), downbeats on the "1", sections plausible, key plausible.
- [ ] Gaps: intro/break/outro detected; flagged words make sense (report false alarms).

## Phase 7 — editor part 1 (manual browser checklist)
- [ ] Launcher shortcut → after the update check the browser opens the editor; launcher shows "Editor running at http://127.0.0.1:8765/". Closing the launcher stops it (page stops responding).
- [ ] Before setup_windows.bat: launcher shows "full setup has not been run" + "Run setup".
- [ ] Waveform loads for song / acapella / instrumental; zoom slider and +/− work.
- [ ] Drag-select, Shift+click, arrows, Esc; Space plays from the clicked word; Shift+Space plays only the selection.
- [ ] The playing word gets an outline and scrolls into view.
- [ ] Windows Firewall should not prompt (server listens on 127.0.0.1 only); report if it does.

## Phase 8 — editor part 2 (manual browser checklist; core flows are automated in CI)
- [ ] Merge / Split / Words / Move / Edit / Remove / nudge on a real song feel right; undo/redo across many steps.
- [ ] Gap regions: drag and resize with the mouse on the waveform; double-click removes (asks first).
- [ ] Review list jumps to the right word/block; ⚠ long marks plausible for your font size.
- [ ] Section preset Apply + "Rebuild all blocks" (asks first) work; Undo restores manual edits.
- [ ] Keyboard shortcuts don't fire while typing in input fields.

## Phase 9 — styles + fonts
- [ ] `assets sync --fonts` downloads ~30 families (≈60-80 TTF files) into `%LOCALAPPDATA%\lyric2resolve\assets\fonts`; CREDITS.md lists them. (Verified in the cloud for 3 families on 2026-11-16.)
- [ ] `assets install-fonts` → files in `%LOCALAPPDATA%\Microsoft\Windows\Fonts` and visible in Windows Settings > Fonts; after restarting Resolve they appear in Text+ / Fusion font list (check one static font, e.g. "Montserrat Bold").
- [ ] Editor: the library fonts render in the style preview (font picker suggestions).

## Phase 10 — FCPXML import (needs Resolve)
- [ ] verify_local `fcpxml_validity` ok (DTD validation; already passes in CI).
- [ ] Import `_16x9.fcpxml` in Resolve (File → Import → Timeline): timeline 1920×1080 at the project fps, starts 01:00:00:00, song on A1, titles on V1 aligned with the words (spot-check 5 lines), no titles inside gaps, section/bar markers present.
- [ ] Same for `_9x16.fcpxml` (1080×1920 timeline).
- [ ] Test one NTSC rate (29.97 or 23.976): the last title is still in sync at the end of the song.
- [ ] Note your Resolve version + whether titles arrive as "Text" or "Text+" (expected: Text) and which style attributes survived.

## Phase 11 — Resolve script (needs Resolve; unit-tested only against a mocked API)
- [ ] Export with "Resolve script" → script appears under Workspace → Scripts → Utility.
- [ ] Without `l2r_textplus`: script imports both FCPXMLs and says so in the Console.
- [ ] With `l2r_textplus` (New Fusion Composition, renamed): timelines "… 16x9 (l2r)" / "… 9x16 (l2r)" with the right resolution and start TC 01:00:00:00.
- [ ] Song on A1 for the whole length (check the AppendToTimeline `endFrame` is not one frame short/long).
- [ ] Text+ clips start/end on the right frames (spot-check 5), none inside gaps.
- [ ] Unverified Text+ mappings to check: `Size = font_px / width`, `Center` (x/y), `HorizontalJustificationNew`, outline `Thickness2`, shadow `Offset3/Softness3`, SoftGlow `Gain/XGlowSize`, FULL keyframes on `Alpha1` / `Size` / `Center` / Write-On `End`.
- [ ] Does each Text+ clip get its OWN composition (editing one does not change the others)?
- [ ] SRT plays in sync in VLC with the song; EDL markers import via Timeline → Import → Timeline Markers from EDL.

## Phase 12 — karaoke (manual)
- [ ] Word highlight follows the singing on a real song (check one fast and one slow part); countdown before the first line and in gaps.
- [ ] Vocal slider fades without clicks; music slider works; no drift between instrumental and vocals over a whole song.
- [ ] Fullscreen on a second monitor/TV (open with the Karaoke button, drag the window, press F); text readable from a distance.
- [ ] Queue: add/reorder/remove/next/previous; survives an app restart.
- [ ] Memory: a 5-minute song loads in a few seconds (both stems are decoded in the browser).

## Phase 13 — textures
- [ ] `assets sync --textures` completes (~27 assets at 1k); CREDITS.md + manifest.json in `%LOCALAPPDATA%\lyric2resolve\assets\textures`. (3 assets verified from the cloud on 2026-11-16.)
- [ ] Interrupt it (Ctrl+C) halfway and run again → continues, no duplicate downloads.
- [ ] Library page shows thumbnails; custom folder textures appear.

## Phase 14 — Blender scenes (built + rendered with Blender 5.3 `bpy` in the cloud/CI, Cycles CPU)
- [ ] With your installed Blender: `blender -b -P l2r_scene.py -- scene_data.json` builds both .blend files (report your Blender version; tested with 5.3).
- [ ] Open in Blender, play the timeline: motion and glow follow bass/mids/highs; sections change intensity.
- [ ] Eevee viewport/render looks right (Eevee could not be tested in the cloud; Cycles was).
- [ ] Packed textures: move the .blend to another folder → still textured.

## Phase 15 — headless render (cloud-tested only with a fake Blender + real ffmpeg)
- [ ] Blender is found automatically (or set `blender_path`); `render --render-preset preview` finishes and prints an estimate first.
- [ ] Eevee render works headless on your GPU (Eevee could not run in the cloud).
- [ ] `--engine CYCLES --render-preset custom`: "GPU rendering with OPTIX/CUDA" message; speed plausible.
- [ ] Ctrl+C then the same command again resumes; the final frame count is complete.
- [ ] The MP4 plays in **Rekordbox** and **Serato** with sound, in sync at start and end (docs/DJ_VIDEO_GUIDE.md section C).
- [ ] NVENC is used when available (fast encode); otherwise libx264 (slower, same result).
- [ ] Resolve Deliver settings from the DJ guide produce a file that plays on the decks.

## Phase 17 — Assistant / Claude link (cloud-tested with a fake `claude` + the real CLI's event format, 2.1.325)
- [ ] `python -m lyric2resolve claude status` finds your Claude Code (report the version and whether it is `claude.exe` or `claude.cmd`).
- [ ] Editor Assistant card: first message gets an answer (= login OK). If not logged in: the card shows the login instructions.
- [ ] A request that edits (e.g. merge two words) changes the lyrics live; Undo reverts it; no console window pops up.
- [ ] Restart the launcher, ask about the previous message → the conversation continued (`claude_session.json` in the project folder).
- [ ] Stop during an answer ends it within a few seconds (no leftover `claude`/`node` processes in Task Manager).
- [ ] When the Pro limit is reached the card shows the limit notice (only if it happens naturally).
- [ ] verify_local: `claude_cli` ok, `mcp_server` ok.
- [ ] (optional) Blender MCP per docs/ASSISTANT.md.

## Phase 18 — settings, branding, batch, update banner
- [ ] Settings page: ffmpeg/Blender/Claude found (or "not found" + help); GPU line shows your NVIDIA card; setting a wrong path shows "not found".
- [ ] Branding on/off changes every page (editor, Library, Ideas, Settings, Karaoke); readable in both themes. After `assets sync --fonts`, the branded pages use JetBrains Mono / Archivo Black.
- [ ] Update banner: after a merge, the editor (started from the launcher) shows "Update available"; **Update now** → the editor stops, the launcher's progress window runs, "What changed" appears, then the editor starts again on the new version.
- [ ] Editor started by hand (`python -m lyric2resolve editor`): Update now explains to use the launcher instead.
- [ ] `lyric2resolve batch <folder>` on 2-3 real songs on the GPU: all projects + exports created, `batch_report.md` correct; a song without an acapella is separated.

## Fixes from testing (1) — new project in the editor
- [ ] Projects window → **+ New project…** with a real song + acapella (+ lyrics) on the GPU: progress log runs, the project opens, words look right.
- [ ] Same without an acapella (separation; slow the first time).
- [ ] With no project open: the right-hand panel shows the hint; Play/Export open the Projects window.
- [ ] If the right-hand buttons still do nothing WITH a project open: press F12 → Console, and send a screenshot of the red errors.

## Fixes from testing (2) — PyTorch repair
- [ ] Update now → the dependency step prints "problem: … mixed CPU/CUDA builds …", reinstalls torch/torchaudio/torchvision, and ends with "PyTorch OK: … +cu128 (or +cu130), CUDA available". If it says "still not OK", copy the whole window text into the session.
- [ ] `verify_local.py`: torch_cuda ✅ with your GPU name.
- [ ] New project with a real song gets past "Loading Whisper" (first time: model download, ~3 GB for large-v3).

## Fixes from testing (3) — Microsoft Store Python
- [ ] `.venv\Scripts\python -c "import sys; print(sys.base_prefix)"` → contains `WindowsApps`? (= Store Python; report it either way).
- [ ] After Update + launcher restart: **Open data folder** opens `C:\Users\<you>\lyric2resolve-data` (Store Python) and shows `settings` + `projects`.
- [ ] New project with the same song converts and transcribes.

## Fixes from testing (4) — vocal separation
- [ ] New project with only a song: separation works on the GPU (time per song?); the editor's audio switch "Acapella" plays the separated vocals.

## Fixes from testing (5) — cuBLAS 12 for Whisper on the GPU
- [ ] Update log / `setup_windows.bat`: "cuBLAS 12 for Whisper: already available (from torch)" or "Installing cuBLAS 12…".
- [ ] New project transcribes on the GPU (no "GPU libraries could not be loaded" warning); how long for one song with large-v3?

## Feature update A — Visuals page, + Text, layout fix
- [ ] Long song at the normal zoom: no jumping/resizing.
- [ ] Visuals: Estimate shows a time; a Preview render finishes with a playable video; Stop + Render continues; Open folder opens Explorer.
- [ ] + Text adds a line where Whisper missed it; it appears in the FCPXML/Resolve export and in Karaoke.
- [ ] New project of You're Not Alone: first sentence recognised now (voice filter 0.35)? If not, does the Review card show "missed lyrics" there?

