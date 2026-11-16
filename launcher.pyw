"""lyric2resolve launcher - the app's entry point (stdlib only).

Started by the Desktop/Start-menu shortcut with pythonw (no console window).
Checks for updates, then starts the app (until the editor exists, a status window).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from lyric2resolve import paths
    from lyric2resolve.updater.cli import main as cli_main

    paths.fix_mac_path()  # macOS: an app started from the Dock gets no Homebrew/git in PATH
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        args = ["--repo", str(ROOT), "launch", *args]
    try:
        return cli_main(args)
    except Exception as exc:  # last-resort error dialog: pythonw has no console
        import traceback

        from lyric2resolve import paths

        log = paths.ensure_data_dir() / "logs" / "launcher.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            import tkinter as tk
            from tkinter import messagebox

            tk.Tk().withdraw()
            messagebox.showerror("lyric2resolve", f"The launcher hit an error:\n{exc}\n\nDetails: {log}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
