#!/usr/bin/env python3
"""Refresh TMDB metadata for demo-owned rows only."""

from __future__ import annotations

import argparse
import json
import sys

from app.core.config import get_settings
from app.core.runtime import RuntimeConfigurationError, validate_runtime_settings
from app.db.session import SessionLocal, get_engine
from app.services.tmdb.refresh import refresh_real_demo_metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh TMDB metadata for demo-owned catalog rows")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-report", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        validate_runtime_settings(settings)
    except RuntimeConfigurationError as exc:
        print(f"Refresh refused: {exc}", file=sys.stderr)
        return 1

    get_engine()
    db = SessionLocal()
    try:
        results = refresh_real_demo_metadata(db, settings, force=args.force)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Refresh failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    payload = {
        "refreshed": len(results),
        "results": [result.__dict__ for result in results],
    }
    if args.json_report:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Refreshed {payload['refreshed']} demo-owned TMDB rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
