#!/usr/bin/env python3
"""Build real multi-audio / subtitle HLS fixtures for Player Experience V1 Ready Gate.

Creates:
  Movie A — EN + FA dub + PS dub audio; EN/FA/PS subtitles
  Movie B — single English audio, no subtitles
  Series episode — multi audio + multi subtitles

Uses real ffmpeg-generated HLS with #EXT-X-MEDIA. Does not commit media files.
Writes /tmp/ifilm-player-v1-verify.json for Playwright / curl QA.
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
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.bootstrap import seed_development_data
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db import session as session_module
from app.models.admin import AdminRole, AdminUser
from app.models.content import Episode, Genre, Movie, Season, Series
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.models.media_tracks import MediaTrack
from app.models.user import Subscriber
from app.services.storage import ensure_media_layout, media_root, relative_media_path
from app.services.streaming.activation import activate_completed_package

OUT = Path("/tmp/ifilm-player-v1-verify.json")
MEDIA_TMP = Path("/tmp/ifilm-player-v1-media")
# Long enough for resume threshold (WATCH_PROGRESS_MIN_SECONDS default 30).
DURATION = 90.0


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed:\n"
            + result.stderr.decode("utf-8", errors="replace")[-4000:]
        )


def _write_vtt(path: Path, *, language: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Simple single-cue WebVTT spanning most of the clip.
    body = (
        "WEBVTT\n\n"
        "1\n"
        "00:00:00.500 --> 00:00:10.000\n"
        f"{text}\n"
    )
    path.write_text(body, encoding="utf-8")


def _encode_video_only(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=navy:s=640x360:d={DURATION}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-g",
            "48",
            "-keyint_min",
            "48",
            "-sc_threshold",
            "0",
            "-f",
            "hls",
            "-hls_time",
            "4",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(out_dir / "segment_%03d.ts"),
            str(out_dir / "index.m3u8"),
        ]
    )


def _encode_audio(out_dir: Path, *, freq: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=f={freq}:d={DURATION}",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-f",
            "hls",
            "-hls_time",
            "4",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(out_dir / "segment_%03d.ts"),
            str(out_dir / "index.m3u8"),
        ]
    )


def _encode_muxed_single_audio(out_dir: Path) -> None:
    """Movie B: classic muxed video+audio, no EXT-X-MEDIA."""
    out_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=teal:s=640x360:d={DURATION}",
            "-f",
            "lavfi",
            "-i",
            f"sine=f=440:d={DURATION}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-f",
            "hls",
            "-hls_time",
            "4",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(out_dir / "segment_%03d.ts"),
            str(out_dir / "index.m3u8"),
        ]
    )


def _write_subtitle_playlist(out_dir: Path, vtt_name: str = "cue.vtt") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    playlist = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:12\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        "#EXT-X-PLAYLIST-TYPE:VOD\n"
        f"#EXTINF:{DURATION:.3f},\n"
        f"{vtt_name}\n"
        "#EXT-X-ENDLIST\n"
    )
    (out_dir / "index.m3u8").write_text(playlist, encoding="utf-8")


def _build_multi_master(pkg_dir: Path) -> None:
    """Movie A / episode: video + 3 audio + 3 subtitle groups."""
    _encode_video_only(pkg_dir / "240p")
    _encode_audio(pkg_dir / "audio_en", freq=440)
    _encode_audio(pkg_dir / "audio_fa", freq=520)
    _encode_audio(pkg_dir / "audio_ps", freq=600)

    _write_vtt(pkg_dir / "subs_en" / "cue.vtt", language="en", text="English subtitle cue")
    _write_vtt(pkg_dir / "subs_fa" / "cue.vtt", language="fa", text="زیرنویس فارسی")
    _write_vtt(pkg_dir / "subs_ps" / "cue.vtt", language="ps", text="پښتو لیکنه")
    for label in ("subs_en", "subs_fa", "subs_ps"):
        _write_subtitle_playlist(pkg_dir / label)

    master = """#EXTM3U
#EXT-X-VERSION:4
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",LANGUAGE="en",DEFAULT=YES,AUTOSELECT=YES,URI="audio_en/index.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Persian Dub",LANGUAGE="fa",DEFAULT=NO,AUTOSELECT=YES,URI="audio_fa/index.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Pashto Dub",LANGUAGE="ps",DEFAULT=NO,AUTOSELECT=YES,URI="audio_ps/index.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",LANGUAGE="en",DEFAULT=NO,AUTOSELECT=YES,FORCED=NO,URI="subs_en/index.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Persian",LANGUAGE="fa",DEFAULT=NO,AUTOSELECT=YES,FORCED=NO,URI="subs_fa/index.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Pashto",LANGUAGE="ps",DEFAULT=NO,AUTOSELECT=YES,FORCED=NO,URI="subs_ps/index.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=450000,RESOLUTION=640x360,CODECS="avc1.42E01E,mp4a.40.2",AUDIO="audio",SUBTITLES="subs"
240p/index.m3u8
"""
    (pkg_dir / "master.m3u8").write_text(master, encoding="utf-8")


def _build_single_master(pkg_dir: Path) -> None:
    _encode_muxed_single_audio(pkg_dir / "240p")
    master = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=450000,RESOLUTION=640x360,CODECS="avc1.42E01E,mp4a.40.2"
240p/index.m3u8
"""
    (pkg_dir / "master.m3u8").write_text(master, encoding="utf-8")


def _placeholder_original(asset_id: str, filename: str = "source.mp4") -> tuple[str, int, str]:
    dest = media_root() / "originals" / asset_id / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = b"\x00\x01IFILM-PLAYER-V1-FIXTURE" + asset_id.encode()
    dest.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    return relative_media_path(dest), len(payload), digest


def _register_package(
    db: Session,
    *,
    movie_id: int | None,
    episode_id: int | None,
    multi: bool,
    title_tag: str,
) -> tuple[MediaAsset, MediaPackage, Path]:
    asset_id = new_uuid()
    package_id = new_uuid()
    storage_path, size_bytes, digest = _placeholder_original(asset_id)
    asset = MediaAsset(
        id=asset_id,
        original_filename=f"{title_tag}.mp4",
        stored_filename="source.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=size_bytes,
        checksum_sha256=digest,
        category="originals",
        upload_status="completed",
        processing_status="completed",
        storage_backend="local",
        storage_path=storage_path,
        movie_id=movie_id,
        episode_id=episode_id,
        duration_seconds=DURATION,
        probed_at=utcnow(),
    )
    db.add(asset)
    db.flush()

    package = MediaPackage(
        id=package_id,
        media_asset_id=asset.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="completed",
        is_active=False,
        duration_seconds=DURATION,
        segment_duration_seconds=4,
        rendition_count=1,
        completed_at=utcnow(),
    )
    db.add(package)
    db.flush()

    pkg_dir = media_root() / "packages" / asset.id / package.id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    if multi:
        _build_multi_master(pkg_dir)
        labels = [
            ("240p", 360, 640, 450000),
            ("audio_en", 0, 0, 96000),
            ("audio_fa", 0, 0, 96000),
            ("audio_ps", 0, 0, 96000),
            ("subs_en", 0, 0, 1000),
            ("subs_fa", 0, 0, 1000),
            ("subs_ps", 0, 0, 1000),
        ]
    else:
        _build_single_master(pkg_dir)
        labels = [("240p", 360, 640, 450000)]

    package.storage_path = relative_media_path(pkg_dir)
    package.master_playlist_path = relative_media_path(pkg_dir / "master.m3u8")
    package.rendition_count = len(labels)

    for label, height, width, bandwidth in labels:
        db.add(
            MediaRendition(
                id=new_uuid(),
                package_id=package.id,
                label=label,
                height=height,
                width=width,
                bandwidth=bandwidth,
                playlist_path=relative_media_path(pkg_dir / label / "index.m3u8"),
                segment_count=max(1, int(DURATION // 4)),
                status="completed",
            )
        )

    if multi:
        tracks = [
            ("audio", "en", True, False, "audio", 0),
            ("audio", "fa", False, True, "audio", 1),
            ("audio", "ps", False, True, "audio", 2),
            ("subtitle", "en", False, False, "subs", 0),
            ("subtitle", "fa", False, False, "subs", 1),
            ("subtitle", "ps", False, False, "subs", 2),
        ]
        for track_type, lang, is_default, is_dubbed, group, order in tracks:
            db.add(
                MediaTrack(
                    media_asset_id=asset.id,
                    track_type=track_type,
                    language_code=lang,
                    label_key=None,
                    is_default=is_default,
                    is_dubbed=is_dubbed,
                    hls_group_id=group,
                    hls_name=None,
                    sort_order=order,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )

    db.flush()
    activate_completed_package(db, package)
    db.commit()
    db.refresh(asset)
    db.refresh(package)
    return asset, package, pkg_dir


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
    os.environ["REDIS_REQUIRED"] = "false"
    os.environ.setdefault("JWT_SECRET", "player-v1-ready-gate-jwt-secret-32chars")
    os.environ.setdefault(
        "PLAYBACK_TOKEN_SECRET", "player-v1-ready-gate-playback-token-secret-32"
    )
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg2://ifilm:ifilm@127.0.0.1:5432/ifilm_player_v1",
    )
    os.environ.setdefault("ADMIN_BOOTSTRAP_USERNAME", "admin")
    os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "unit-test-admin-pass-ok")

    get_settings.cache_clear()
    MEDIA_TMP.mkdir(parents=True, exist_ok=True)
    ensure_media_layout()

    get_settings.cache_clear()
    db_url = os.environ["DATABASE_URL"]
    engine = create_engine(db_url, pool_pre_ping=True)
    # Ensure migrations
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    session_module.SessionLocal = SessionLocal
    db = SessionLocal()
    try:
        seed_development_data(db, include_demo_catalog=False)
        db.commit()

        admin = (
            db.query(AdminUser)
            .filter(AdminUser.username == os.environ["ADMIN_BOOTSTRAP_USERNAME"])
            .one()
        )
        admin_token = create_access_token(
            str(admin.id), {"typ": "admin", "username": admin.username}
        )

        # Subscriber
        sub = (
            db.query(Subscriber)
            .filter(Subscriber.username == "player-v1-subscriber")
            .one_or_none()
        )
        if sub is None:
            sub = Subscriber(
                username="player-v1-subscriber",
                hashed_password=hash_password("player-v1-subscriber-pass"),
                name="Player V1 Subscriber",
                status="active",
                package="Standard",
                service_status="active",
                identity_provider="local",
                external_subject=None,
                max_devices=5,
            )
            db.add(sub)
            db.commit()
            db.refresh(sub)
        sub_token = create_access_token(
            str(sub.id), {"typ": "subscriber", "username": sub.username}
        )

        genre = db.query(Genre).filter(Genre.slug == "player-v1-qa").one_or_none()
        if genre is None:
            genre = Genre(name="Player V1 QA", slug="player-v1-qa")
            db.add(genre)
            db.flush()

        def upsert_movie(slug: str, title: str, language: str = "English") -> Movie:
            movie = db.query(Movie).filter(Movie.slug == slug).one_or_none()
            if movie is None:
                movie = Movie(
                    title=title,
                    slug=slug,
                    description=f"{title} — Player Experience V1 Ready Gate fixture.",
                    release_year=2026,
                    poster_url="https://example.test/player-v1-poster.jpg",
                    backdrop_url="https://example.test/player-v1-backdrop.jpg",
                    status="published",
                    published_at=utcnow(),
                    duration_minutes=1,
                    language=language,
                )
                movie.genre_links = [genre]
                db.add(movie)
                db.commit()
                db.refresh(movie)
            else:
                movie.status = "published"
                movie.published_at = movie.published_at or utcnow()
                db.add(movie)
                db.commit()
                db.refresh(movie)
            return movie

        movie_a = upsert_movie("player-v1-movie-a-multi", "Player V1 Multi Audio")
        movie_b = upsert_movie("player-v1-movie-b-single", "Player V1 Single Audio")

        # Clear prior packages for these movies (idempotent re-run)
        for movie in (movie_a, movie_b):
            for asset in db.query(MediaAsset).filter(MediaAsset.movie_id == movie.id).all():
                for pkg in db.query(MediaPackage).filter(MediaPackage.media_asset_id == asset.id):
                    pkg.is_active = False
                    db.add(pkg)
                db.query(MediaTrack).filter(MediaTrack.media_asset_id == asset.id).delete()
            db.commit()

        asset_a, pkg_a, dir_a = _register_package(
            db, movie_id=movie_a.id, episode_id=None, multi=True, title_tag="movie-a"
        )
        asset_b, pkg_b, dir_b = _register_package(
            db, movie_id=movie_b.id, episode_id=None, multi=False, title_tag="movie-b"
        )

        # Series + episode
        series = db.query(Series).filter(Series.slug == "player-v1-series").one_or_none()
        if series is None:
            series = Series(
                title="Player V1 Series",
                slug="player-v1-series",
                description="Series fixture for episode multi-track playback.",
                status="published",
                published_at=utcnow(),
                language="English",
            )
            series.genre_links = [genre]
            db.add(series)
            db.flush()
        season = (
            db.query(Season)
            .filter(Season.series_id == series.id, Season.season_number == 1)
            .one_or_none()
        )
        if season is None:
            season = Season(
                series_id=series.id,
                season_number=1,
                title="Season 1",
                status="published",
                published_at=utcnow(),
            )
            db.add(season)
            db.flush()
        else:
            season.status = "published"
            season.published_at = season.published_at or utcnow()
            db.add(season)
            db.flush()
        episode = (
            db.query(Episode)
            .filter(
                Episode.series_id == series.id,
                Episode.season_id == season.id,
                Episode.episode_number == 3,
            )
            .one_or_none()
        )
        if episode is None:
            episode = Episode(
                series_id=series.id,
                season_id=season.id,
                episode_number=3,
                title="S01E03 Multi Track",
                description="Episode fixture",
                duration_minutes=1,
                status="published",
                published_at=utcnow(),
            )
            db.add(episode)
            db.commit()
            db.refresh(episode)
        else:
            episode.status = "published"
            episode.published_at = episode.published_at or utcnow()
            db.add(episode)
            db.commit()
            db.refresh(episode)

        for asset in db.query(MediaAsset).filter(MediaAsset.episode_id == episode.id).all():
            for pkg in db.query(MediaPackage).filter(MediaPackage.media_asset_id == asset.id):
                pkg.is_active = False
                db.add(pkg)
            db.query(MediaTrack).filter(MediaTrack.media_asset_id == asset.id).delete()
        db.commit()

        asset_ep, pkg_ep, dir_ep = _register_package(
            db, movie_id=None, episode_id=episode.id, multi=True, title_tag="episode-s01e03"
        )

        # Broken track fixture: admin-visible missing playlist for diagnostics
        missing_label = "audio_missing"
        (dir_a / missing_label).mkdir(exist_ok=True)
        # intentionally no index.m3u8
        db.add(
            MediaRendition(
                id=new_uuid(),
                package_id=pkg_a.id,
                label=missing_label,
                height=0,
                width=0,
                bandwidth=96000,
                playlist_path=relative_media_path(dir_a / missing_label / "index.m3u8"),
                segment_count=0,
                status="completed",
            )
        )
        db.commit()

        # Alembic version
        with engine.connect() as conn:
            try:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            except Exception:
                version = "unknown"

        master_a = (dir_a / "master.m3u8").read_text(encoding="utf-8")
        assert "#EXT-X-MEDIA:TYPE=AUDIO" in master_a
        assert 'LANGUAGE="en"' in master_a and 'LANGUAGE="fa"' in master_a
        assert master_a.count("DEFAULT=YES") == 1
        assert "#EXT-X-MEDIA:TYPE=SUBTITLES" in master_a

        payload = {
            "created_at": datetime.now(UTC).isoformat(),
            "migration_head": version,
            "media_root": str(MEDIA_TMP),
            "api_hint": "http://127.0.0.1:8020",
            "frontend_hint": "http://127.0.0.1:5173",
            "admin": {
                "username": os.environ["ADMIN_BOOTSTRAP_USERNAME"],
                "password": os.environ["ADMIN_BOOTSTRAP_PASSWORD"],
                "token": admin_token,
            },
            "subscriber": {
                "username": "player-v1-subscriber",
                "password": "player-v1-subscriber-pass",
                "token": sub_token,
                "id": sub.id,
            },
            "movie_a": {
                "id": movie_a.id,
                "slug": movie_a.slug,
                "title": movie_a.title,
                "asset_id": asset_a.id,
                "package_id": pkg_a.id,
                "player_path": f"/player/movie/{movie_a.id}",
                "multi_audio": True,
                "audio": ["en", "fa", "ps"],
                "subtitles": ["en", "fa", "ps"],
                "missing_rendition_label": missing_label,
            },
            "movie_b": {
                "id": movie_b.id,
                "slug": movie_b.slug,
                "title": movie_b.title,
                "asset_id": asset_b.id,
                "package_id": pkg_b.id,
                "player_path": f"/player/movie/{movie_b.id}",
                "multi_audio": False,
            },
            "episode": {
                "id": episode.id,
                "series_id": series.id,
                "season": 1,
                "episode_number": 3,
                "title": episode.title,
                "asset_id": asset_ep.id,
                "package_id": pkg_ep.id,
                "player_path": (
                    f"/player/episode/{episode.id}"
                    f"?series={series.id}&season=1"
                ),
            },
            "master_a_excerpt": "\n".join(master_a.splitlines()[:12]),
        }
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "out": str(OUT), "migration_head": version}, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
