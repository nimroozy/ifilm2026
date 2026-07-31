#!/usr/bin/env python3
"""Prepare a local 640×360 HLS playable movie for Phase 8 browser verification.

Does NOT commit media files. Writes a JSON manifest under /tmp for the
Playwright runner. Requires PostgreSQL + Redis (docker compose) and ffmpeg.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "app" / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bootstrap import seed_development_data
from app.core.config import get_settings
from app.core.security import hash_password
from app.db import session as session_module
from app.models.admin import AdminRole, AdminUser
from app.models.content import Movie
from app.models.media_assets import MediaAsset, new_uuid
from app.services.media_processing.encode_job import queue_encode_hls_job
from app.services.media_processing.worker import run_once
from app.services.storage import (
    asset_storage_path,
    ensure_media_layout,
    media_root,
    relative_media_path,
)

OUT = Path("/tmp/ifilm-phase8-verify.json")
MEDIA_TMP = Path("/tmp/ifilm-phase8-media")


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def _mp4(path: Path, *, size: str = "640x360", duration: float = 8.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s={size}:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=f=440:d={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))


def main() -> int:
    _load_dotenv(BACKEND / ".env")
    os.environ["APP_ENV"] = "development"
    os.environ["CSP_MODE"] = "production"
    os.environ["MEDIA_ROOT"] = str(MEDIA_TMP)
    os.environ["ARTWORK_ROOT"] = str(MEDIA_TMP / "artwork")
    os.environ["ENABLE_UPLOADS"] = "true"
    os.environ["ENABLE_MEDIA_PROCESSING"] = "true"
    os.environ["ENABLE_HLS_ENCODING"] = "true"
    os.environ["ENABLE_LOCAL_STREAMING"] = "true"
    os.environ["ENABLE_RADIUS_LOGIN"] = "true"
    os.environ["RADIUS_ENABLED"] = "true"
    os.environ["RADIUS_MODE"] = "mock"
    os.environ["REDIS_REQUIRED"] = "false"
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.database_url or settings.database_url.startswith("sqlite"):
        raise SystemExit(f"Refusing non-Postgres DATABASE_URL: {settings.database_url!r}")
    if not settings.jwt_secret:
        raise SystemExit("JWT_SECRET is required")
    if not settings.playback_token_secret or len(settings.playback_token_secret) < 32:
        raise SystemExit("PLAYBACK_TOKEN_SECRET (≥32) is required")

    MEDIA_TMP.mkdir(parents=True, exist_ok=True)
    ensure_media_layout()

    cfg = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(cfg, "head")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session_module.reset_engine_for_tests(engine)
    SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db: Session = SessionFactory()
    try:
        seed_development_data(db, include_demo_catalog=True)

        movie = Movie(
            title="Phase8 Verify Clip",
            slug=f"phase8-verify-{new_uuid()[:8]}",
            status="published",
            published_at=datetime.now(UTC),
            description="Local verification asset",
            short_description="640x360 HLS",
            duration_minutes=1,
        )
        db.add(movie)
        db.commit()
        db.refresh(movie)

        asset_id = new_uuid()
        stored = f"{asset_id}.mp4"
        dest = asset_storage_path(category="originals", asset_id=asset_id, stored_filename=stored)
        _mp4(dest, size="640x360", duration=8.0)
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        asset = MediaAsset(
            id=asset_id,
            original_filename="phase8-verify.mp4",
            stored_filename=stored,
            mime_type="video/mp4",
            extension="mp4",
            size_bytes=dest.stat().st_size,
            checksum_sha256=digest,
            width=640,
            height=360,
            duration_seconds=8.0,
            video_codec="h264",
            audio_codec="aac",
            audio_stream_count=1,
            video_frame_rate=25.0,
            storage_backend="local",
            storage_path=relative_media_path(dest),
            category="originals",
            upload_status="completed",
            processing_status="completed",
            probed_at=datetime.now(UTC),
            probe_version="ffprobe-json-v1",
            probe_json={"format": {"format_name": "mov,mp4"}},
            movie_id=movie.id,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)

        job, package, created = queue_encode_hls_job(
            db, settings=settings, asset=asset, admin_id=None
        )
        assert created
        assert run_once(db, settings=settings, worker_id="phase8-verify") is True
        db.refresh(job)
        db.refresh(package)
        if job.status != "completed" or package.status != "completed" or not package.is_active:
            raise RuntimeError(
                f"encode failed: job={job.status} package={package.status} "
                f"err={job.error_code} {job.error_message}"
            )
        labels = sorted(r.label for r in package.renditions)
        master = media_root() / package.master_playlist_path

        role = db.query(AdminRole).filter(AdminRole.name == "superadmin").first()
        if role is None:
            role = AdminRole(
                name="superadmin",
                permissions=[
                    "streaming.read",
                    "streaming.manage",
                    "processing.read",
                    "processing.manage",
                    "movies.manage",
                    "dashboard",
                ],
            )
            db.add(role)
            db.flush()
        admin = db.query(AdminUser).filter(AdminUser.username == "admin").first()
        admin_password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "phase8-admin-pass-ok")
        if admin is None:
            admin = AdminUser(
                username="admin",
                email="admin@example.local",
                full_name="Admin",
                hashed_password=hash_password(admin_password),
                role_id=role.id,
                is_active=True,
            )
            db.add(admin)
            db.commit()

        payload = {
            "movie_id": movie.id,
            "movie_slug": movie.slug,
            "movie_title": movie.title,
            "media_asset_id": asset.id,
            "package_id": package.id,
            "rendition_labels": labels,
            "master_playlist_path": str(master),
            "player_path": f"/player/movie/{movie.id}",
            "watch_path": f"/movie/{movie.id}",
            "subscriber_user": "mobin_user_001",
            "subscriber_password": "fixture-pass-ok",
            "admin_user": "admin",
            "admin_password": admin_password,
            "media_root": str(MEDIA_TMP),
        }
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        print(f"Wrote {OUT}", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
