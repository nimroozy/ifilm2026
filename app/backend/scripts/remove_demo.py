#!/usr/bin/env python3
"""Remove demo-owned data only.

Usage:
  python -m scripts.remove_demo              # dry-run summary (all demo-owned)
  python -m scripts.remove_demo --confirm    # apply deletion
  python -m scripts.remove_demo --fake-only  # synthetic/fake demo only (keeps TMDB demo)
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.core.runtime import RuntimeConfigurationError, validate_runtime_settings
from app.db.session import SessionLocal, get_engine
from app.services.demo.cleanup import build_cleanup_plan, execute_cleanup


def main(argv: list[str] | None = None, *, fake_only: bool | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove iFilm demo-owned data")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete demo-owned rows/files (required to apply)",
    )
    parser.add_argument(
        "--fake-only",
        action="store_true",
        help="Delete synthetic/fake demo rows only; retain TMDB-backed demo catalog",
    )
    args = parser.parse_args(argv)
    mode_fake_only = fake_only if fake_only is not None else bool(args.fake_only)

    settings = get_settings()
    try:
        validate_runtime_settings(settings)
    except RuntimeConfigurationError as exc:
        print(f"Cleanup refused: {exc}", file=sys.stderr)
        return 1

    get_engine()
    db = SessionLocal()
    try:
        plan = build_cleanup_plan(db, settings, fake_only=mode_fake_only)
        for line in plan.summary_lines():
            print(line)
        if not args.confirm:
            print("Dry-run only. Re-run with --confirm to delete the listed demo-owned data.")
            return 0
        execute_cleanup(db, settings, plan)
        label = "Fake demo cleanup" if mode_fake_only else "Demo cleanup"
        print(f"{label} applied (admins/audit retained; non-demo preserved).")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
