#!/usr/bin/env python3
"""Install TMDB-backed realistic demo catalog data.

Usage:
  python -m scripts.seed_real_demo
  DEMO_SKIP_MEDIA=1 python -m scripts.seed_real_demo --json-report

Requires TMDB_ENABLED=true and TMDB_API_READ_TOKEN. Never prints token values or
generated passwords. Never enables live Radius.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.runtime import RuntimeConfigurationError, validate_runtime_settings
from app.db.session import SessionLocal, get_engine
from app.services.tmdb.curated import REAL_DEMO_SEED_VERSION
from app.services.tmdb.seed_real import seed_real_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed TMDB-backed iFilm demo catalog data")
    parser.add_argument("--credentials-file", default=os.environ.get("DEMO_CREDENTIALS_PATH") or "")
    parser.add_argument("--skip-media", action="store_true", help="Skip synthetic Demo Clip media generation")
    parser.add_argument("--json-report", action="store_true", help="Print machine-readable report JSON")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        validate_runtime_settings(settings)
    except RuntimeConfigurationError as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 1

    if settings.app_env in {"production", "prod", "staging"}:
        if (os.environ.get("DEMO_SEED_ALLOW_PROD") or "").lower() not in {"1", "true", "yes", "on"}:
            print("Seed refused: set DEMO_SEED_ALLOW_PROD=true to run on production/staging hosts", file=sys.stderr)
            return 1

    get_engine()
    skip_media = args.skip_media or (os.environ.get("DEMO_SKIP_MEDIA") or "").lower() in {"1", "true", "yes", "on"}
    db = SessionLocal()
    try:
        report = seed_real_demo(
            db,
            settings,
            credentials_path=Path(args.credentials_file) if args.credentials_file else None,
            skip_media=skip_media,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    payload = report.as_dict()
    payload["seed_command"] = "python -m scripts.seed_real_demo"
    if args.json_report:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Real demo seed completed (version={REAL_DEMO_SEED_VERSION}).")
        print(f"  movies={payload['movies']}")
        print(f"  series={payload['series']}")
        print(f"  seasons={payload['seasons']}")
        print(f"  episodes={payload['episodes']}")
        print(f"  media_assets={payload['media_assets']}")
        print(f"  active_hls_packages={payload['active_hls_packages']}")
        print(f"  published_items={payload['published_items']}")
        print(f"  credentials_file={payload['credentials_path']} (not printed)")
        if payload["deviations"]:
            print("  deviations:")
            for item in payload["deviations"]:
                print(f"    - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
