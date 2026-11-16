# CLAUDE.md — conventions for sessions working on this repo

- Read SPEC.md, PROGRESS.md, PHASES.md, HANDOFF_PROMPT.md first. Repo = source of truth.
- Python ≥ 3.10, src layout (`src/lyric2resolve`). Run tests: `python -m pytest -q` (CI uses `-m "not local"`).
- Cross-platform: `pathlib` only, no hardcoded paths/shell assumptions. Windows is the target.
- `lyric2resolve.updater` and `launcher.pyw` must stay **stdlib only**.
- GUI (Tkinter) = thin layer; all logic in plain functions/classes testable without a display.
- Heavy deps (torch, whisper, librosa, bpy, ffmpeg) behind small interfaces; mock in tests; real tests `@pytest.mark.local`.
- User data never in the repo: use `lyric2resolve.paths.data_dir()`.
- Every PR: CHANGELOG.md entry (plain language: new / changed / what to test), update PROGRESS.md + HANDOFF_PROMPT.md, VERIFY_LOCAL.md for PC-only checks.
- Never put secrets/tokens in the repo or logs.
