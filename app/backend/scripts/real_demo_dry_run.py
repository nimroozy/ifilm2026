#!/usr/bin/env python3
"""Dry-run report of demo-owned fake/TMDB catalog content (no deletions).

Usage:
  python -m scripts.real_demo_dry_run
"""

from __future__ import annotations

import sys

from scripts.remove_demo import main as remove_demo_main


def main(argv: list[str] | None = None) -> int:
    # Always dry-run: ignore --confirm if passed accidentally.
    filtered = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--confirm"]
    return remove_demo_main(filtered)


if __name__ == "__main__":
    raise SystemExit(main())
