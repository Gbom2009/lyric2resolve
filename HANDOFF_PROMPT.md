# HANDOFF PROMPT — lyric2resolve

You are continuing **lyric2resolve**, a Windows app (Python, NVIDIA/CUDA) that turns a song + its acapella into a DaVinci Resolve timeline with synced lyric text clips, plus a browser editor, karaoke mode, audio-reactive Blender visuals, font/texture libraries, a Claude Code link and a git-based auto-updater with its own launcher. Repo: `github.com/Gbom2009/lyric2resolve`. It is built in small phases by cloud Claude Code sessions, alternating between two user accounts. **The repo is the source of truth** — if this text and the repo disagree, trust the repo (main, open PRs, PROGRESS.md, git log).

## Where everything lives
- `SPEC.md` full spec (verbatim) · `PHASES.md` phase plan (goal/files/tests/user checklist per phase) · `PROGRESS.md` MODE, status table, CURRENT STEP LOG, decisions, feedback, pasted local reports · `CHANGELOG.md` plain-language entries (shown by the updater) · `VERIFY_LOCAL.md` + `scripts/verify_local.py` things only the user's PC can verify · `CLAUDE.md` coding conventions · `INSTALL.md` first-time install.

## Current state (update every checkpoint)
- Phase 0 (planning docs): done, on `main` (initial commit).
- Phase 1 (skeleton + launcher/updater): **in progress** — see PROGRESS.md CURRENT STEP LOG for the exact step.
- Open PR: see PROGRESS.md / GitHub. Waiting for user test result: no.
- MODE: **gated**. Waiting for user input: nothing yet.

## Git workflow
- `main` = merged, CI-green work only. Never push to main directly (only the Phase 0 initial commit did).
- One branch per phase from fresh main (`phase-NN-slug`), draft PR into main at first push, small commits, push after each, CHANGELOG entry + same summary in the PR description, mark ready when done + CI green.
- User's fixes after testing go first on the NEXT phase branch as commits "Fixes from testing phase N" (or a small fix PR if urgent).
- The user never tests PRs: they merge, then update their installed copy with the launcher's **Update** button (git fetch + ff-only/hard-reset to origin/main, rollback tag, dependency step, self-check; auto-rollback on failure).

## Architecture / key decisions
- src layout `src/lyric2resolve/`, modules: updater (stdlib only), audio, analysis, transcription, editor (FastAPI + vanilla JS, no build step), export, karaoke, visuals/render, assets, claude_link.
- User data outside the clone: `%LOCALAPPDATA%\lyric2resolve` (override env `LYRIC2RESOLVE_DATA`) — projects, assets, settings, cache, models. The updater never touches it.
- Hardware/OS-specific code behind small interfaces; heavy models mocked in tests; real tests marked `@pytest.mark.local` (skipped in CI).

## Cloud constraints + verify loop
Cloud sessions are Linux, CPU-only, no Windows/GPU/Resolve/Blender/DJ software, limited network. Never claim Windows/GPU behaviour works unless the user's `REPORT_LOCAL.md` (from `scripts/verify_local.py`) says so. User pastes reports → record in PROGRESS.md → fix issues.

## Working modes
- **GATED** (default): after a phase is done (tests + CI green) update PROGRESS/CHANGELOG/HANDOFF, mark PR ready, print: "Phase N done, PR #X is ready"; steps (merge → launcher Update → TEST CHECKLIST from PHASES.md); "Reply with what works and what doesn't, or say 'continuous'"; this handoff prompt in one code block. Then STOP and wait.
- **CONTINUOUS** (user says "continuous"/"use continuous"/"go continuous"): set MODE in PROGRESS.md, one branch `continuous-<date>` + one PR, phase-labelled commits, short status + handoff after each phase, keep going. "gate"/"gated"/"stop continuous" switches back.
- Both: anything needing the user's PC/input → mark "waiting for user", say so, (continuous) skip to an independent phase.

## Rules
Start by reading SPEC.md, PROGRESS.md, PHASES.md, HANDOFF_PROMPT.md; `git fetch`, `git log`, check open PRs and current branch/step. Commit small, push often, keep CURRENT STEP LOG current. Low on budget → checkpoint, push, update PROGRESS.md, print handoff. Interaction: short specific questions (multiple choice), concise outcome reports, casual tone; reply in the user's language (they may write Dutch).

## Known limitations / open issues
See PROGRESS.md "Open issues". No `.drp` generation possible (Resolve project format is proprietary/binary database).

## First actions for the new session
1. `git fetch --all`, read the files above, check open PRs.
2. Summarize your understanding back to the user in a few lines.
3. Continue the current step from PROGRESS.md, or wait for the user's test feedback if a phase is marked "PR open / waiting for test".

---
The user may append a mode line such as "use continuous" below this pasted prompt.
