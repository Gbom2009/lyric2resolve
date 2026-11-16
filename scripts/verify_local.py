"""Run all local checks on your PC and write REPORT_LOCAL.md / REPORT_LOCAL.json.

    .venv\\Scripts\\python.exe scripts\\verify_local.py            all checks
    .venv\\Scripts\\python.exe scripts\\verify_local.py --quick    skip slow checks (model loads, renders)
    .venv\\Scripts\\python.exe scripts\\verify_local.py --offline  skip network checks
    .venv\\Scripts\\python.exe scripts\\verify_local.py --only gpu torch_cuda

Paste REPORT_LOCAL.md into the Claude session.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from lyric2resolve import verify  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", type=Path, default=REPO)
    args = ap.parse_args(argv)
    verify.register_pending()
    ctx = verify.Context(repo=REPO, quick=args.quick, offline=args.offline)
    results = verify.run_checks(ctx, set(args.only) if args.only else None)
    for r in results:
        print(f"{r.status.upper():5} {r.name:24} {r.detail}")
    md, js = verify.write_report(results, ctx, args.out)
    print(f"\nReport written: {md}\n(also {js})")
    return 1 if any(r.status == verify.FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
