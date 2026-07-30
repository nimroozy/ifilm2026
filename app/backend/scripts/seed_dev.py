#!/usr/bin/env python3
"""Explicit development seed command.

Usage:
  APP_ENV=development \
  JWT_SECRET=... \
  DATABASE_URL=... \
  ADMIN_BOOTSTRAP_PASSWORD=... \
  python -m scripts.seed_dev
"""

from __future__ import annotations

import sys

from app.bootstrap import seed_development_data
from app.core.config import get_settings
from app.core.runtime import RuntimeConfigurationError, is_dev_like, validate_runtime_settings
from app.db.session import SessionLocal, get_engine


def main() -> int:
    settings = get_settings()
    try:
        validate_runtime_settings(settings)
        if not is_dev_like(settings.app_env):
            raise RuntimeConfigurationError("seed_dev may only run when APP_ENV is development or test")
        get_engine()
        db = SessionLocal()
        try:
            seed_development_data(db, include_demo_catalog=True)
        finally:
            db.close()
    except RuntimeConfigurationError as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 1
    print("Development seed completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
