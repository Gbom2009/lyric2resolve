"""CLI entry point: app commands + updater commands (launch, check-update, update, rollback, ...)."""

from __future__ import annotations

import importlib
import sys

# command -> module with main(argv) (imported lazily so the launcher stays light)
APP_COMMANDS = {
    "audio-check": "lyric2resolve.audio",
    "transcribe": "lyric2resolve.transcription",
    "analyze": "lyric2resolve.analysis",
    "editor": "lyric2resolve.editor.app",
    "assets": "lyric2resolve.assets",
    "export": "lyric2resolve.export",
    "visuals": "lyric2resolve.visuals.blender_gen",
    "render": "lyric2resolve.render",
    "ideas": "lyric2resolve.visuals.prompts",
    "claude": "lyric2resolve.claude_link",
    "mcp-server": "lyric2resolve.claude_link.mcp_server",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in APP_COMMANDS:
        return importlib.import_module(APP_COMMANDS[argv[0]]).main(argv[1:])
    from lyric2resolve.updater.cli import main as updater_main

    return updater_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
