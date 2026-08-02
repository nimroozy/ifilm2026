#!/usr/bin/env python3
"""Install safe, idempotent demo catalog data.

Usage (inside API container with runtime.env sourced):
  python -m scripts.seed_demo
  python -m scripts.seed_demo --credentials-file /data/artwork/.demo/credentials.txt
  DEMO_SKIP_MEDIA=1 python -m scripts.seed_demo   # metadata only

Never prints passwords. Writes credentials only to the credentials file (mode 600).
Does not enable live Radius. Does not modify JWT/DB/Radius secrets.
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
from app.services.demo.constants import DEMO_SEED_VERSION
from app.services.demo.seed import run_seed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed iFilm demo catalog data")
    parser.add_argument(
        "--credentials-file",
        default=os.environ.get("DEMO_CREDENTIALS_PATH") or "",
        help="Where to write generated credentials (mode 600). Passwords are never printed.",
    )
    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="Skip synthetic video upload/probe/HLS (metadata + users only)",
    )
    parser.add_argument(
        "--json-report",
        action="store_true",
        help="Print machine-readable report JSON (no passwords)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        validate_runtime_settings(settings)
    except RuntimeConfigurationError as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 1

    if settings.app_env in {"production", "prod", "staging"}:
        # Demo seed is allowed on prod-like hosts for staging validation, but never
        # enables Radius. Operator must opt into local demo subscriber auth separately.
        if (os.environ.get("DEMO_SEED_ALLOW_PROD") or "").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            print(
                "Seed refused: set DEMO_SEED_ALLOW_PROD=true to run on production/staging hosts",
                file=sys.stderr,
            )
            return 1

    get_engine()
    cred_path = Path(args.credentials_file) if args.credentials_file else None
    skip_media = args.skip_media or (os.environ.get("DEMO_SKIP_MEDIA") or "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    db = SessionLocal()
    try:
        report = run_seed(
            db,
            settings,
            credentials_path=cred_path,
            skip_media=skip_media,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    payload = report.as_dict()
    payload["seed_command"] = "python -m scripts.seed_demo"
    if args.json_report:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Demo seed completed (version={DEMO_SEED_VERSION}).")
        print(f"  users_added={payload['users_added']}")
        print(f"  genres={payload['genres']}")
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
