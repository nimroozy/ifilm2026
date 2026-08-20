"""CLI for branch-cache lab artifact validate-only / factory smoke.

Usage:
  python -m app.services.branch_cache.service --validate-only
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="branch-cache-lab")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Build the ASGI app and exit without binding a socket",
    )
    args = parser.parse_args(argv)
    if not args.validate_only:
        parser.error("only --validate-only is supported in Phase 7 (no listener)")
    from app.services.branch_cache.service.asgi import validate_lab_startup

    result = validate_lab_startup()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
