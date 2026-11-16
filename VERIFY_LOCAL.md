# VERIFY_LOCAL.md — things only your Windows PC can verify

The cloud sessions run on Linux without GPU/Windows/Resolve/Blender. Everything below must be checked on your PC.
From Phase 2 on, `scripts/verify_local.py` automates most of it and writes REPORT_LOCAL.md — paste that into the session.

## Phase 1 — install + launcher + updater
CI already runs `install.ps1 -NoShortcuts` and all updater tests on a Windows runner; still check by hand:
- [ ] `install.bat` creates `.venv` and the Desktop + Start-menu shortcuts.
- [ ] Shortcut opens the launcher **without** a console window.
- [ ] Status text "No app interface yet - version <hash> (<date>), up to date".
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
