"""Asset libraries: fonts (Google Fonts, OFL/Apache) and textures (CC0, Phase 13)."""

from __future__ import annotations


def main(argv: list[str]) -> int:
    """lyric2resolve assets sync [--fonts] [--textures] | install-fonts | list-fonts"""
    import argparse

    ap = argparse.ArgumentParser(prog="lyric2resolve assets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="download the curated free asset libraries (run on your PC)")
    s.add_argument("--fonts", action="store_true")
    s.add_argument("--textures", action="store_true")
    sub.add_parser("install-fonts", help="install downloaded + custom fonts for your Windows user")
    sub.add_parser("list-fonts")
    args = ap.parse_args(argv)
    from . import fonts

    if args.cmd == "list-fonts":
        for f in fonts.list_fonts():
            print(f"{f['family']:24} {f['source']:8} {f['license']}")
        return 0
    if args.cmd == "install-fonts":
        try:
            names = fonts.install_fonts()
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"Installed {len(names)} font files for your user. Restart DaVinci Resolve to see them.")
        return 0
    do_fonts = args.fonts or not args.textures
    rc = 0
    if do_fonts:
        rep = fonts.sync()
        print(f"Fonts: {len(rep.added)} new/updated, {len(rep.skipped)} unchanged, "
              f"{len(rep.rejected)} rejected (license), {len(rep.failed)} failed")
        for f in rep.failed:
            print("  FAILED", f)
        print(f"Folder: {fonts.fonts_dir()}  (credits in CREDITS.md). Next: lyric2resolve assets install-fonts")
        rc |= 1 if rep.failed else 0
    if args.textures or not args.fonts:
        try:
            from . import textures  # Phase 13
        except ImportError:
            print("Texture sync arrives in a later update.")
        else:
            rc |= textures.main_sync()
    return rc
