#!/usr/bin/env python3
"""Remove synthetic/fake demo catalog content only.

Retains:
  - non-demo catalog
  - TMDB-backed real demo catalog (demo_owned + metadata_source=tmdb)
  - admin accounts / roles
  - publication audit events (tombstoned)

Never deletes non-demo / real user content. Dry-run unless --confirm.

Usage:
  python -m scripts.remove_fake_demo
  python -m scripts.remove_fake_demo --confirm
"""

from __future__ import annotations

import sys

from scripts.remove_demo import main as remove_demo_main


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--fake-only" not in args:
        args = ["--fake-only", *args]
    return remove_demo_main(args, fake_only=True)


if __name__ == "__main__":
    raise SystemExit(main())
