#!/usr/bin/env python3
"""Explicit production/staging admin bootstrap + encoding profiles.

Never seeds demo catalog. Never enables fixture auth.
"""

from __future__ import annotations

import sys

from app.bootstrap import SUPER_PERMISSIONS, seed_encoding_profiles
from app.core.config import get_settings
from app.core.runtime import (
    RuntimeConfigurationError,
    require_admin_bootstrap_password,
    validate_runtime_settings,
)
from app.core.security import hash_password
from app.db.session import SessionLocal, get_engine
from app.models.admin import AdminRole, AdminUser


def main() -> int:
    settings = get_settings()
    try:
        validate_runtime_settings(settings)
        if settings.app_env not in {"production", "prod", "staging"}:
            raise RuntimeConfigurationError(
                "seed_production_admin requires APP_ENV=production or staging"
            )
        admin_password = require_admin_bootstrap_password(settings)
        get_engine()
        db = SessionLocal()
        try:
            inserted = seed_encoding_profiles(db)
            role = db.query(AdminRole).filter(AdminRole.name == "Super Admin").one_or_none()
            if role is None:
                role = AdminRole(name="Super Admin", permissions=SUPER_PERMISSIONS)
                db.add(role)
                db.flush()
            else:
                role.permissions = SUPER_PERMISSIONS

            admin = (
                db.query(AdminUser)
                .filter(AdminUser.username == settings.admin_bootstrap_username)
                .one_or_none()
            )
            if admin is None:
                admin = AdminUser(
                    username=settings.admin_bootstrap_username,
                    email=settings.admin_bootstrap_email,
                    hashed_password=hash_password(admin_password),
                    full_name="System Administrator",
                    is_active=True,
                    role_id=role.id,
                )
                db.add(admin)
            else:
                admin.hashed_password = hash_password(admin_password)
                admin.email = settings.admin_bootstrap_email
                admin.is_active = True
                admin.role_id = role.id
            db.commit()
            print(
                f"Admin bootstrap completed (encoding_profiles_inserted={inserted}, "
                f"admin={settings.admin_bootstrap_username}). Demo catalog was NOT seeded."
            )
        finally:
            db.close()
    except RuntimeConfigurationError as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
