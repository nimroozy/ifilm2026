"""Phase 9 publishing workflow tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Episode, Genre, Movie, Season, Series
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.models.publication import MediaPublicationEvent
from app.services.publishing.worker import run_once
from app.services.storage import ensure_media_layout, media_root, relative_media_path
from app.services.streaming.activation import activate_completed_package


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db_session, *, username: str, permissions: list[str]) -> str:
    role = AdminRole(name=f"role-{username}", permissions=permissions)
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=username,
        email=f"{username}@example.test",
        full_name=username,
        hashed_password=hash_password("publish-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _write_mini_package(package_dir: Path) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    rendition = package_dir / "240p"
    rendition.mkdir(parents=True, exist_ok=True)
    (rendition / "segment_000.ts").write_bytes(b"\x00\x01" * 64)
    (rendition / "index.m3u8").write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:6.0,\nsegment_000.ts\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    (package_dir / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=400000,RESOLUTION=426x240\n240p/index.m3u8\n',
        encoding="utf-8",
    )


def _seed_active_package(db_session, *, movie_id: int | None = None, episode_id: int | None = None):
    ensure_media_layout()
    asset = MediaAsset(
        id=new_uuid(),
        original_filename="clip.mp4",
        stored_filename="clip.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=1000,
        category="originals",
        upload_status="completed",
        processing_status="completed",
        storage_backend="local",
        storage_path=f"originals/{new_uuid()}/clip.mp4",
        movie_id=movie_id,
        episode_id=episode_id,
        width=640,
        height=360,
        probed_at=utcnow(),
    )
    db_session.add(asset)
    db_session.flush()
    package = MediaPackage(
        id=new_uuid(),
        media_asset_id=asset.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="completed",
        is_active=False,
        segment_duration_seconds=6,
        rendition_count=1,
        completed_at=utcnow(),
    )
    db_session.add(package)
    db_session.flush()
    pkg_dir = media_root() / "packages" / asset.id / package.id
    _write_mini_package(pkg_dir)
    package.storage_path = relative_media_path(pkg_dir)
    package.master_playlist_path = relative_media_path(pkg_dir / "master.m3u8")
    db_session.add(
        MediaRendition(
            id=new_uuid(),
            package_id=package.id,
            label="240p",
            height=240,
            width=426,
            bandwidth=400000,
            playlist_path=relative_media_path(pkg_dir / "240p" / "index.m3u8"),
            segment_count=1,
            status="completed",
        )
    )
    db_session.flush()
    activate_completed_package(db_session, package)
    db_session.commit()
    return asset, package


def _genre(db_session) -> Genre:
    g = Genre(name="Drama", slug=f"drama-{new_uuid()[:8]}")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


def _ready_movie(db_session, *, slug: str = "pub-movie") -> Movie:
    g = _genre(db_session)
    movie = Movie(
        title="Publishable Movie",
        slug=slug,
        description="A full synopsis for readiness.",
        release_year=2024,
        poster_url="https://example.test/poster.jpg",
        backdrop_url="https://example.test/backdrop.jpg",
        status="draft",
    )
    movie.genre_links = [g]
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    _seed_active_package(db_session, movie_id=movie.id)
    return movie


WORKFLOW_PERMS = [
    "catalog.read",
    "catalog.edit",
    "catalog.review",
    "catalog.approve",
    "catalog.publish",
    "catalog.archive",
    "movies.read",
    "movies.manage",
    "series.read",
    "series.manage",
]


def test_full_movie_publish_unpublish_visibility(client, db_session, admin_headers):
    # Super admin from fixture has merged permissions after seed.
    movie = _ready_movie(db_session, slug="vis-movie")

    # Draft not public
    assert client.get(f"/api/movies/{movie.slug}").status_code == 404
    assert all(m["slug"] != movie.slug for m in client.get("/api/movies").json()["data"])

    mid = movie.id
    assert client.post(f"/api/admin/catalog/movie/{mid}/submit-review", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/movie/{mid}/approve", headers=admin_headers, json={}).status_code == 200
    pub = client.post(f"/api/admin/catalog/movie/{mid}/publish", headers=admin_headers, json={})
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    assert client.get(f"/api/movies/{movie.slug}").status_code == 200
    search = client.get("/api/search", params={"q": "Publishable"}).json()
    assert any(m["slug"] == movie.slug for m in search["movies"])

    unpub = client.post(f"/api/admin/catalog/movie/{mid}/unpublish", headers=admin_headers, json={"reason": "qa"})
    assert unpub.status_code == 200
    assert unpub.json()["status"] == "unpublished"
    assert client.get(f"/api/movies/{movie.slug}").status_code == 404

    history = client.get(f"/api/admin/catalog/movie/{mid}/publication-history", headers=admin_headers)
    assert history.status_code == 200
    events = history.json()
    assert len(events) >= 4
    types = {e["event_type"] for e in events}
    assert "review_submitted" in types
    assert "approval_granted" in types
    assert "publication_executed" in types
    assert "unpublished" in types


def test_publish_requires_active_package(client, db_session, admin_headers):
    g = _genre(db_session)
    movie = Movie(
        title="No Package",
        slug="no-pkg",
        description="Synopsis here",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="approved",
    )
    movie.genre_links = [g]
    db_session.add(movie)
    db_session.commit()

    resp = client.post(f"/api/admin/catalog/movie/{movie.id}/publish", headers=admin_headers, json={})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "not_ready"


def test_invalid_transition(client, db_session, admin_headers):
    movie = _ready_movie(db_session, slug="bad-trans")
    # draft cannot publish directly
    resp = client.post(f"/api/admin/catalog/movie/{movie.id}/publish", headers=admin_headers, json={})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_transition"


def test_permission_enforcement(client, db_session):
    movie = _ready_movie(db_session, slug="perm-movie")
    token = _make_admin(db_session, username="editor-only", permissions=["catalog.edit", "catalog.read", "movies.manage"])
    headers = _headers(token)
    # edit cannot submit review
    assert client.post(f"/api/admin/catalog/movie/{movie.id}/submit-review", headers=headers, json={}).status_code == 403
    # movies.manage cannot publish
    movie.status = "approved"
    db_session.add(movie)
    db_session.commit()
    assert client.post(f"/api/admin/catalog/movie/{movie.id}/publish", headers=headers, json={}).status_code == 403


def test_patch_cannot_set_status(client, db_session, admin_headers):
    movie = _ready_movie(db_session, slug="patch-status")
    resp = client.patch(
        f"/api/admin/movies/{movie.id}",
        headers=admin_headers,
        json={"status": "published"},
    )
    # status field removed from schema → ignored / validation error
    assert resp.status_code in {200, 422}
    db_session.refresh(movie)
    assert movie.status == "draft"


def test_scheduled_publish_worker(client, db_session, admin_headers):
    movie = _ready_movie(db_session, slug="sched-movie")
    mid = movie.id
    client.post(f"/api/admin/catalog/movie/{mid}/submit-review", headers=admin_headers, json={})
    client.post(f"/api/admin/catalog/movie/{mid}/approve", headers=admin_headers, json={})
    future = utcnow() + timedelta(hours=2)
    sched = client.post(
        f"/api/admin/catalog/movie/{mid}/schedule",
        headers=admin_headers,
        json={"scheduled_publish_at": future.isoformat()},
    )
    assert sched.status_code == 200
    assert sched.json()["status"] == "scheduled"
    assert client.get("/api/movies/sched-movie").status_code == 404

    # Make due
    movie = db_session.get(Movie, mid)
    movie.scheduled_publish_at = utcnow() - timedelta(seconds=5)
    db_session.add(movie)
    db_session.commit()

    assert run_once(db_session) is True
    db_session.refresh(movie)
    assert movie.status == "published"
    assert client.get("/api/movies/sched-movie").status_code == 200

    # Idempotent — nothing due
    assert run_once(db_session) is False


def test_scheduled_readiness_recheck_fails_safely(db_session, admin_headers, client):
    movie = _ready_movie(db_session, slug="sched-fail")
    mid = movie.id
    client.post(f"/api/admin/catalog/movie/{mid}/submit-review", headers=admin_headers, json={})
    client.post(f"/api/admin/catalog/movie/{mid}/approve", headers=admin_headers, json={})
    future = utcnow() + timedelta(hours=1)
    client.post(
        f"/api/admin/catalog/movie/{mid}/schedule",
        headers=admin_headers,
        json={"scheduled_publish_at": future.isoformat()},
    )
    # Break package
    db_session.query(MediaPackage).update({"is_active": False, "status": "failed"})
    movie = db_session.get(Movie, mid)
    movie.scheduled_publish_at = utcnow() - timedelta(seconds=1)
    db_session.add(movie)
    db_session.commit()

    run_once(db_session)
    db_session.refresh(movie)
    assert movie.status == "approved"
    assert movie.scheduled_publish_at is None
    failed = (
        db_session.query(MediaPublicationEvent)
        .filter(MediaPublicationEvent.entity_id == mid, MediaPublicationEvent.event_type == "publication_failed")
        .count()
    )
    assert failed >= 1


def test_series_requires_published_episode(client, db_session, admin_headers):
    g = _genre(db_session)
    series = Series(
        title="Needs Ep",
        slug="needs-ep",
        description="Series synopsis",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="approved",
    )
    series.genre_links = [g]
    db_session.add(series)
    db_session.commit()
    resp = client.post(f"/api/admin/catalog/series/{series.id}/publish", headers=admin_headers, json={})
    assert resp.status_code == 409

    season = Season(series_id=series.id, season_number=1, title="S1", status="published")
    db_session.add(season)
    db_session.flush()
    episode = Episode(
        season_id=season.id,
        series_id=series.id,
        episode_number=1,
        title="E1",
        status="published",
    )
    db_session.add(episode)
    db_session.commit()
    _seed_active_package(db_session, episode_id=episode.id)

    ok = client.post(f"/api/admin/catalog/series/{series.id}/publish", headers=admin_headers, json={})
    assert ok.status_code == 200
    assert ok.json()["status"] == "published"


def test_featured_does_not_override_unpublished(client, db_session):
    g = _genre(db_session)
    movie = Movie(
        title="Featured Draft",
        slug="feat-draft",
        description="x",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="draft",
        is_featured=True,
        is_trending=True,
    )
    movie.genre_links = [g]
    db_session.add(movie)
    db_session.commit()
    featured = client.get("/api/movies", params={"featured": True}).json()["data"]
    assert all(m["slug"] != "feat-draft" for m in featured)


def test_readiness_endpoint(client, db_session, admin_headers):
    movie = _ready_movie(db_session, slug="ready-ep")
    resp = client.get(f"/api/admin/catalog/movie/{movie.id}/publication-readiness", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["playable"] is True
    assert "submit_review" in body["allowed_actions"]
