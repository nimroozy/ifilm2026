#!/usr/bin/env python3
"""Remove demo-owned data only.

Usage:
  python -m scripts.remove_demo              # dry-run summary
  python -m scripts.remove_demo --confirm    # apply deletion
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.core.runtime import RuntimeConfigurationError, validate_runtime_settings
from app.db.session import SessionLocal, get_engine
from app.services.demo.cleanup import build_cleanup_plan, execute_cleanup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove iFilm demo-owned data")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete demo-owned rows/files (required to apply)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        validate_runtime_settings(settings)
    except RuntimeConfigurationError as exc:
        print(f"Cleanup refused: {exc}", file=sys.stderr)
        return 1

    get_engine()
    db = SessionLocal()
    try:
        plan = build_cleanup_plan(db, settings)
        for line in plan.summary_lines():
            print(line)
        if not args.confirm:
            print("Dry-run only. Re-run with --confirm to delete the listed demo-owned data.")
            return 0
        execute_cleanup(db, settings, plan)
        print("Demo cleanup applied (demo-owned data only).")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
