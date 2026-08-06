#!/usr/bin/env python3
"""Remove demo-owned fake/TMDB catalog content only.

Never deletes non-demo / real user content. Dry-run unless --confirm.

Usage:
  python -m scripts.remove_fake_demo
  python -m scripts.remove_fake_demo --confirm
"""

from __future__ import annotations

import sys

from scripts.remove_demo import main as remove_demo_main


def main(argv: list[str] | None = None) -> int:
    return remove_demo_main(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
