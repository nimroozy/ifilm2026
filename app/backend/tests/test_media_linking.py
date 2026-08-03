"""Tests for media asset attach/detach linking."""

from __future__ import annotations

from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Movie
from app.models.media_assets import MediaAsset, utcnow
from app.services.storage import ensure_media_layout


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
        hashed_password=hash_password("link-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _asset(
    db_session,
    *,
    filename: str = "clip.mp4",
    mime: str = "video/mp4",
    category: str = "originals",
    upload_status: str = "completed",
    movie_id: int | None = None,
    episode_id: int | None = None,
) -> MediaAsset:
    ensure_media_layout()
    asset = MediaAsset(
        original_filename=filename,
        stored_filename=filename,
        mime_type=mime,
        extension=".mp4",
        size_bytes=1024,
        category=category,
        upload_status=upload_status,
        processing_status="none",
        movie_id=movie_id,
        episode_id=episode_id,
        checksum_sha256=None,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_link_requires_manage_permission(client, db_session):
    reader = _make_admin(db_session, username="link-reader", permissions=["upload.read"])
    asset = _asset(db_session)
    movie = db_session.query(Movie).first()
    assert movie is not None
    resp = client.post(
        f"/api/admin/media/assets/{asset.id}/link",
        headers=_headers(reader),
        json={"owner_type": "movie", "owner_id": movie.id},
    )
    assert resp.status_code == 403


def test_link_movie_and_list_by_owner(client, admin_headers, db_session):
    movie = db_session.query(Movie).first()
    assert movie is not None
    asset = _asset(db_session, filename="movie-master.mp4")

    linked = client.post(
        f"/api/admin/media/assets/{asset.id}/link",
        headers=admin_headers,
        json={"owner_type": "movie", "owner_id": movie.id},
    )
    assert linked.status_code == 200, linked.text
    body = linked.json()
    assert body["movie_id"] == movie.id
    assert body["episode_id"] is None

    listed = client.get(
        "/api/admin/media/assets",
        headers=admin_headers,
        params={"movie_id": movie.id},
    )
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["data"]}
    assert asset.id in ids

    # Idempotent re-link
    again = client.post(
        f"/api/admin/media/assets/{asset.id}/link",
        headers=admin_headers,
        json={"owner_type": "movie", "owner_id": movie.id},
    )
    assert again.status_code == 200


def test_link_conflict_when_already_owned(client, admin_headers, db_session):
    movie_a = db_session.query(Movie).first()
    assert movie_a is not None
    movie_b = Movie(
        title="Other Movie",
        slug="other-movie-link-test",
        status="draft",
    )
    db_session.add(movie_b)
    db_session.commit()
    db_session.refresh(movie_b)
    asset = _asset(db_session, movie_id=movie_a.id)

    conflict = client.post(
        f"/api/admin/media/assets/{asset.id}/link",
        headers=admin_headers,
        json={"owner_type": "movie", "owner_id": movie_b.id},
    )
    assert conflict.status_code == 409


def test_link_rejects_non_video(client, admin_headers, db_session):
    movie = db_session.query(Movie).first()
    asset = _asset(db_session, filename="poster.jpg", mime="image/jpeg", category="posters")
    resp = client.post(
        f"/api/admin/media/assets/{asset.id}/link",
        headers=admin_headers,
        json={"owner_type": "movie", "owner_id": movie.id},
    )
    assert resp.status_code == 400


def test_list_unassigned_linkable(client, admin_headers, db_session):
    free = _asset(db_session, filename="free.mp4")
    movie = db_session.query(Movie).first()
    _asset(db_session, filename="taken.mp4", movie_id=movie.id)

    resp = client.get(
        "/api/admin/media/assets",
        headers=admin_headers,
        params={"unassigned": True, "video_only": True, "linkable_only": True, "q": "free"},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]
    ids = {item["id"] for item in items}
    assert free.id in ids
    assert all(item["movie_id"] is None and item["episode_id"] is None for item in items)


def test_detach_draft_ok_and_preserves_asset(client, admin_headers, db_session):
    movie = db_session.query(Movie).first()
    movie.status = "draft"
    db_session.add(movie)
    db_session.commit()
    asset = _asset(db_session, movie_id=movie.id)

    resp = client.post(
        f"/api/admin/media/assets/{asset.id}/detach",
        headers=admin_headers,
        json={},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["movie_id"] is None
    assert resp.json()["episode_id"] is None

    still = client.get(f"/api/admin/media/assets/{asset.id}", headers=admin_headers)
    assert still.status_code == 200
    assert still.json()["upload_status"] == "completed"


def test_detach_published_blocked_without_force(client, admin_headers, db_session):
    movie = db_session.query(Movie).first()
    movie.status = "published"
    movie.published_at = utcnow()
    db_session.add(movie)
    db_session.commit()
    asset = _asset(db_session, movie_id=movie.id)

    blocked = client.post(
        f"/api/admin/media/assets/{asset.id}/detach",
        headers=admin_headers,
        json={},
    )
    assert blocked.status_code == 409

    forced = client.post(
        f"/api/admin/media/assets/{asset.id}/detach",
        headers=admin_headers,
        json={"force_unpublish": True},
    )
    assert forced.status_code == 200, forced.text
    db_session.refresh(movie)
    assert movie.status == "unpublished"
    assert forced.json()["movie_id"] is None


def test_link_episode(client, admin_headers, db_session):
    from app.models.content import Episode, Season, Series

    series = db_session.query(Series).first()
    if series is None:
        series = Series(title="Link Series", slug="link-series-test", status="draft")
        db_session.add(series)
        db_session.flush()
    season = db_session.query(Season).filter(Season.series_id == series.id).first()
    if season is None:
        season = Season(series_id=series.id, season_number=1, title="S1", status="draft")
        db_session.add(season)
        db_session.flush()
    episode = db_session.query(Episode).filter(Episode.season_id == season.id).first()
    if episode is None:
        episode = Episode(
            season_id=season.id,
            series_id=series.id,
            episode_number=1,
            title="E1",
            status="draft",
        )
        db_session.add(episode)
        db_session.commit()
        db_session.refresh(episode)

    asset = _asset(db_session, filename="ep1.mp4")
    linked = client.post(
        f"/api/admin/media/assets/{asset.id}/link",
        headers=admin_headers,
        json={"owner_type": "episode", "owner_id": episode.id},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["episode_id"] == episode.id
    assert linked.json()["movie_id"] is None

    listed = client.get(
        "/api/admin/media/assets",
        headers=admin_headers,
        params={"episode_id": episode.id},
    )
    assert listed.status_code == 200
    assert any(item["id"] == asset.id for item in listed.json()["data"])


def test_upload_session_with_owner_preselection(client, admin_headers, db_session):
    movie = db_session.query(Movie).first()
    assert movie is not None
    created = client.post(
        "/api/admin/media/sessions",
        headers=admin_headers,
        json={
            "filename": "owned.mp4",
            "mime_type": "video/mp4",
            "size_bytes": 10,
            "category": "originals",
            "movie_id": movie.id,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["media_asset"]["movie_id"] == movie.id
