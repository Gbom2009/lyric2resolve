# Assistant (Claude Code link) — optional

The editor has an **Assistant (Claude)** card. It sends your message to the real Claude Code CLI on your PC,
running in the background with your own Claude login (Claude Pro). Claude can then read and change the open
project through the app's own tools: merge/split blocks, fix words and timings, add/remove gaps, apply section
presets, set styles, export, start a preview render and read its progress. Every change appears live in the editor
and can be undone with **Undo** like your own edits.

**The app works fully without it.** Nothing else depends on the Assistant.

## Setup (once)
1. Install Claude Code: PowerShell `irm https://claude.ai/install.ps1 | iex` (or `npm install -g @anthropic-ai/claude-code`).
2. Open a new terminal, run `claude`, and log in with your Claude account (`/login`). Close it again.
3. Open the editor: the Assistant card shows "Claude Code <version>". If not, set `claude_cli_path` in Settings
   (`%LOCALAPPDATA%\lyric2resolve\settings\app.json`).

Check from a terminal: `.venv\Scripts\python -m lyric2resolve claude status`.

## How it works
- One Claude session per project. The id is saved in `<project folder>\claude_session.json`. The first message
  uses `claude -p --session-id <id>`, later ones `--resume <id>`, so the conversation continues after an app restart.
  **New conversation** forgets the id (your notes stay).
- `<project folder>\CLAUDE.md` holds the project's state (rewritten before every message) plus a **Notes** part that is
  never overwritten: decisions and style choices for a fresh session. Claude Code reads it automatically.
- `<project folder>\.l2r_mcp.json` registers the app's MCP server (`python -m lyric2resolve.claude_link.mcp_server`).
  Pre-allowed: the app's tools (`mcp__lyric2resolve`), reading/searching files (`Read`, `Glob`, `Grep`) and **writing /
  editing files inside the project folder only** (`Edit(./**)`, `Write(./**)`) — e.g. its notes in CLAUDE.md and custom
  scenes in `scenes/`. Anything else (writing elsewhere, running commands) is denied in background mode, and the card
  tells you what was denied.
- **📎 Attach**: images, videos or documents are saved in `<project folder>\context\`; ticked files are named in your
  next message (Claude can look at images).
- **Custom scenes / clips**: "✨ Make a clip with Claude" in the Clips card, or just ask. Claude reads the
  `custom_scene_guide` tool, writes `scenes/<name>/scene.py` and calls `render_clip`; the clip lands on the clips track.
- You can also use the tools from your own terminal: `cd` into the project folder and run
  `claude --mcp-config .l2r_mcp.json` (create the file with `python -m lyric2resolve claude mcp-config <project.json>`).
  Without the editor running, the server edits `project.json` directly.

## Privacy and limits
- The app never reads, copies or stores your Claude login and never uses an API key: it removes `ANTHROPIC_API_KEY`
  from the background process so your Claude subscription is always used.
- Claude Pro has usage limits per few hours. The card shows the usage the CLI reports and a clear notice when the limit
  is reached; try again after the reset time.
- Settings (`app.json`): `claude_model` (empty = the CLI default, or e.g. `sonnet`), `claude_permission_mode`
  (empty/`default`, `acceptEdits`, `plan`, `dontAsk`, `auto`; "bypass" is not offered), `claude_blender_mcp`.

## Optional: Blender MCP (not needed for rendering)
The community **Blender MCP** server (github.com/ahujasid/blender-mcp) lets Claude control an *open* Blender window.
Headless rendering in this app never depends on it. To try it (verify the steps against that repo's README first):
1. Install `uv` (`winget install astral-sh.uv`), then install the Blender add-on `addon.py` from that repo in Blender
   (Edit → Preferences → Add-ons → Install), open the sidebar (N) → BlenderMCP → **Connect**.
2. Set `"claude_blender_mcp": true` in `app.json`. The app then adds
   `{"blender": {"type": "stdio", "command": "uvx", "args": ["blender-mcp"]}}` to the MCP config and pre-allows its tools.
3. Ask the Assistant e.g. "open the generated .blend and make the bass bars taller".
Only use it with Blender files you trust: the add-on can run Python code inside Blender.
