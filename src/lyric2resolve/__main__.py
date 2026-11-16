"""CLI entry point. Phase 1 only offers updater commands; later phases add the pipeline."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from lyric2resolve.updater.cli import main as updater_main

    return updater_main(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
