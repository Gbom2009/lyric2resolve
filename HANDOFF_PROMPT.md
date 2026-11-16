# HANDOFF PROMPT — lyric2resolve — PROJECT COMPLETE (all 19 phases built; waiting for the user's PC test)

You are continuing **lyric2resolve**, a Windows app (Python, NVIDIA/CUDA) that turns a song + its acapella into a DaVinci Resolve timeline with synced lyric text clips (FCPXML 16:9 + 9:16, Resolve Text+ script, SRT/CSV/EDL), plus a browser editor, karaoke mode, audio-reactive Blender visuals rendered headless into DJ-ready MP4s, font/CC0-texture libraries, an optional Claude Code Assistant, batch mode, Team Funqtion branding, and a git-based auto-updater with its own launcher. Repo: `github.com/Gbom2009/lyric2resolve`. Built in phases by cloud Claude Code sessions, alternating between two user accounts. **The repo is the source of truth** — if this text and the repo disagree, trust the repo (main, open PRs, PROGRESS.md, git log).

## Where everything lives
- `README.md` user guide · `SPEC.md` full spec (verbatim) · `PHASES.md` phase plan · `PROGRESS.md` MODE, status table, CURRENT STEP LOG, decisions, open issues, user feedback, pasted local reports · `CHANGELOG.md` plain-language entries (shown by the updater) · `VERIFY_LOCAL.md` (FULL TEST PASS at the top) + `scripts/verify_local.py` (checks in `src/lyric2resolve/verify.py`) · `CLAUDE.md` coding conventions · `INSTALL.md` first-time install · `docs/` (RESOLVE_IMPORT, RESOLVE_SCRIPT, DJ_VIDEO_GUIDE, ASSISTANT).

## Current state
- Merged on main: Phase 0 (docs), Phase 1 (launcher/updater, PR #1).
- **PR #2** (Phases 2-19) is MERGED into main.
- Feature updates (2026-11-16): A = PR #8 (merged: Visuals page, + Text, layout fix, VAD 0.35 + missed-lyrics flag, 11 review fixes); B = branch `feature-clips-scenes` (clips track + export, ✨ clips with Claude via custom Blender scenes, 3D lyrics, lyric-video styles + Look, Assistant attachments + scoped write permissions). User asked: merge each PR as soon as CI is green.
- User feedback 6 (2026-11-16, PC): Blender scene KeyError 'Emission Color' (old Blender) → fixed on branch `fix-blender-sockets` (socket aliases, version in log). Ask which Blender version the PC has.
- Mac feedback 3 (2026-11-16): setup + editor work on the Mac now; transcription failed CERTIFICATE_VERIFY_FAILED (python.org Python, urllib) → fixed on branch `mac-fix-ssl` (SSL_CERT_FILE → certifi). Waiting for retry.
- Mac feedback 2 (2026-11-16): update dependency step ran under Rosetta (x86_64 torch 2.2.2 into the arm64 .venv); fixed on branch `mac-fix-arch-2` (ensure_native in setup_update.py / __main__ / launcher); user reinstalls .venv once. Waiting for retry.
- Mac feedback 1 (2026-11-16): app ran under Rosetta → arm64/x86_64 ImportError; fixed on branch `mac-fix-arch` (launcher native re-exec, plist + start script arch -arm64). Waiting for the user's retry.
- **Mac app** (Apple Silicon, docs/MAC_PLAN.md, 6 phases, one PR each): 1-2 merged, 3 (MLX Whisper) merged #12, 4 (VideoToolbox/Metal/8 GB presets) merged #13, 5 (fonts, verify checks, help texts, Stop) PR #14, 6 (README Mac chapter + MAC FULL TEST PASS) branch `mac-docs`. Next: the user's Mac REPORT_LOCAL.md → fixes. Mac installs follow branch `mac-release` (fast-forward it to main after each Mac PR). macOS CI job is cancelled by GitHub on this account → test on the user's MacBook Air M1 8 GB.
- User feedback 5 (2026-11-16): transcription failed "cublas64_12.dll not found" → fixed on branch `fixes-2026-11-16e` (PR "Fixes from testing (5)"): CUDA DLL search path, cuBLAS 12 install when missing, CPU fallback. Waiting for merge + Update + retry.
- User feedback 4 (2026-11-16): song-only New project: audio-separator missing `audioread` → fixed on branch `fixes-2026-11-16d` (PR "Fixes from testing (4)"). Store Python confirmed (data now in C:\Users\<user>\lyric2resolve-data). Waiting for merge + Update + retry.
- User feedback 3 (2026-11-16): New project: ffmpeg "No such file or directory" for an uploaded file Python could see → Microsoft Store Python AppData redirection; fixed on branch `fixes-2026-11-16c` (PR "Fixes from testing (3)"): data dir outside AppData for Store Python + migration. Waiting for the user to merge + Update + restart launcher + retry.
- User feedback 2 (2026-11-16): "libtorchaudio.pyd could not load" in New project → torch replaced by a CPU PyPI build during setup; fixed on branch `fixes-2026-11-16b` (PR "Fixes from testing (2)"): pinned torch set + auto-repair on Update, av<19. Waiting for the user to merge + Update + retry New project.
- User feedback 1 (2026-11-16): side-panel buttons "don't work" + no way to create a project in the UI → fixed on branch `fixes-2026-11-16` (PR "Fixes from testing (1)"): New project dialog, no-project guards/empty states. Waiting for the user to merge + Update + retest, then the FULL TEST PASS in VERIFY_LOCAL.md.
- User facts (session 3): Claude Code CLI is installed + logged in on the PC; brand values come from the public repo Gbom2009/funqtion-site.

## Maintenance mode (what the next sessions do)
1. Fetch, read PROGRESS.md (feedback + reports), check open PRs. If PR #2 is merged, branch from fresh main: `fixes-<date>` (or `phase-20-<slug>` for new features), draft PR at first push.
2. Record the user's REPORT_LOCAL.md / feedback in PROGRESS.md ("Local verification reports", "User test feedback"), then fix in commits labelled "Fixes from testing" (CHANGELOG entry + VERIFY_LOCAL item per fix).
3. Likely first fixes (unverifiable in the cloud): Whisper/CUDA + separation model name, Resolve FCPXML import details and Fusion Text+ input names (docs/RESOLVE_SCRIPT.md lists them), Eevee headless, NVENC, Rekordbox/Serato playback, Windows paths of `claude`.
4. New features: add a phase to PHASES.md + PROGRESS.md table, keep the module separation (updater stdlib-only; heavy deps behind interfaces; tests with fakes; `@pytest.mark.local` for real hardware), add verify_local checks for anything PC-only.
5. Dependencies: change `requirements/*.txt` → the updater's dependency step runs `scripts/setup_update.py --update` automatically on the PC.

## Git workflow
- `main` = merged, CI-green work only. Never push to main directly.
- Branch from fresh main per phase/fix batch, draft PR at first push, small commits, push after each, CHANGELOG entry + same summary in the PR description, mark ready when done + CI green.
- The user never tests PRs: they merge, then update their installed copy with the launcher's **Update** button or the editor's update banner (git fetch + ff-only/hard-reset to origin/main, rollback tag, dependency step, self-check; auto-rollback on failure; *Roll back* in the launcher).

## Architecture / key decisions (details: PROGRESS.md "Decisions")
- src layout `src/lyric2resolve/`: updater (stdlib only), audio, transcription, analysis, project, editor (FastAPI + vanilla JS, no build step), export, karaoke, visuals, render, assets, claude_link, branding, batch, cli (end-to-end), verify.
- User data outside the clone: `%LOCALAPPDATA%\lyric2resolve` (override env `LYRIC2RESOLVE_DATA`). The updater never touches it.
- Editor ops are pure functions behind `POST /api/op/{name}` with undo snapshots; all exporters share `export/timeline.build_plan` + `check_plan` (nothing in gaps).
- Claude link: real `claude -p --output-format stream-json --verbose` with `--session-id`/`--resume`, app MCP server (stdlib JSON-RPC) that edits through the running editor; never touches login tokens; removes ANTHROPIC_API_KEY.
- Tests: `python -m pytest -q` (CI excludes `local`); tests set `L2R_NO_UPDATE_CHECK=1`; browser tests need Playwright Chromium (`L2R_CHROMIUM=<path>` for a preinstalled one).

## Cloud constraints + verify loop
Cloud sessions are Linux, CPU-only, no Windows/GPU/Resolve/Blender GUI/DJ software, limited network. Never claim Windows/GPU behaviour works unless the user's REPORT_LOCAL.md says so. User pastes reports → record in PROGRESS.md → fix.

## Working modes
- **GATED** (default): after a phase/fix batch (tests + CI green) update PROGRESS/CHANGELOG/HANDOFF, mark the PR ready, print "Phase N done, PR #X is ready", the steps (merge → launcher Update → checklist), "Reply with what works and what doesn't, or say 'continuous'", and this handoff in one code block. Then STOP and wait.
- **CONTINUOUS** ("continuous"/"use continuous"/"go continuous"): MODE in PROGRESS.md, one branch `continuous-<date>` + one PR, phase-labelled commits, short status + handoff after each phase, keep going. "gate"/"gated"/"stop continuous" switches back.
- Both: anything needing the user's PC/input → mark "waiting for user", say so, (continuous) skip to independent work.

## Rules
Start by reading SPEC.md, PROGRESS.md, PHASES.md, HANDOFF_PROMPT.md; `git fetch`, `git log`, check open PRs and current branch/step. Commit small, push often, keep CURRENT STEP LOG current. Low on budget → checkpoint, push, update PROGRESS.md, print handoff. Interaction: short specific questions (multiple choice), concise outcome reports, casual tone; reply in the user's language (they may write Dutch).

## Known limitations / open issues
See PROGRESS.md "Open issues" and README "Limitations". No `.drp` generation possible (Resolve's project format is a proprietary database).

## First actions for the new session
1. `git fetch --all`, read the files above, check open PRs (is PR #2 merged?).
2. Summarize your understanding back to the user in a few lines.
3. If the user pasted REPORT_LOCAL.md / test notes: record them and start fixing on a new branch from main. Otherwise ask for the FULL TEST PASS result (VERIFY_LOCAL.md) and wait.

---
The user may append a mode line such as "use continuous" below this pasted prompt.
