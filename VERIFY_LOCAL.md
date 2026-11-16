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
