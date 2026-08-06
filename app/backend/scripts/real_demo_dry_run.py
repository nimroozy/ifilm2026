#!/usr/bin/env python3
"""Dry-run report of synthetic/fake demo catalog content (no deletions).

Lists deletes / detaches / retains / tombstones for remove_fake_demo.
Never lists non-demo or TMDB real-demo rows as deletable.

Usage:
  python -m scripts.real_demo_dry_run
"""

from __future__ import annotations

import sys

from scripts.remove_demo import main as remove_demo_main


def main(argv: list[str] | None = None) -> int:
    # Always dry-run + fake-only: ignore --confirm if passed accidentally.
    filtered = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--confirm"]
    if "--fake-only" not in filtered:
        filtered = ["--fake-only", *filtered]
    return remove_demo_main(filtered, fake_only=True)


if __name__ == "__main__":
    raise SystemExit(main())
