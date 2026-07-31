"""Phase 10 watch progress / history tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Genre, Movie
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.models.media_playback import PRINCIPAL_SUBSCRIBER, SESSION_ACTIVE, MediaPlaybackSession
from app.models.user import Subscriber
from app.models.watch_progress import UserWatchProgress
from app.services.storage import ensure_media_layout, media_root, relative_media_path
from app.services.streaming.activation import activate_completed_package
from app.services.streaming.tokens import generate_playback_token, hash_playback_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _subscriber(db_session, *, username: str = "watcher") -> tuple[Subscriber, str]:
    user = Subscriber(
        username=username,
        hashed_password=None,
        name=username,
        status="active",
        package="Standard",
        service_status="active",
        identity_provider="local",
        external_subject=None,
        max_devices=3,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(str(user.id), {"typ": "subscriber", "username": user.username})
    return user, token


def _admin_token(db_session) -> str:
    role = AdminRole(name=f"wh-role-{new_uuid()[:6]}", permissions=["streaming.manage", "movies.manage"])
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=f"wh-admin-{new_uuid()[:6]}",
        email=f"{new_uuid()[:6]}@ex.test",
        full_name="WH Admin",
        hashed_password=hash_password("admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _write_pkg(package_dir: Path) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    rendition = package_dir / "240p"
    rendition.mkdir(parents=True, exist_ok=True)
    (rendition / "segment_000.ts").write_bytes(b"\x00\x01" * 32)
    (rendition / "index.m3u8").write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nsegment_000.ts\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    (package_dir / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=400000\n240p/index.m3u8\n",
        encoding="utf-8",
    )


def _published_movie_with_package(db_session, *, slug: str = "watch-movie") -> tuple[Movie, MediaAsset, MediaPackage]:
    ensure_media_layout()
    g = Genre(name="Watch", slug=f"watch-{new_uuid()[:6]}")
    db_session.add(g)
    db_session.flush()
    movie = Movie(
        title="Watchable",
        slug=slug,
        description="Synopsis",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="published",
        published_at=utcnow(),
        duration_minutes=45,
    )
    movie.genre_links = [g]
    db_session.add(movie)
    db_session.flush()
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
        movie_id=movie.id,
        duration_seconds=600.0,
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
        duration_seconds=600.0,
        segment_duration_seconds=6,
        rendition_count=1,
        completed_at=utcnow(),
    )
    db_session.add(package)
    db_session.flush()
    pkg_dir = media_root() / "packages" / asset.id / package.id
    _write_pkg(pkg_dir)
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
    db_session.refresh(movie)
    db_session.refresh(asset)
    db_session.refresh(package)
    return movie, asset, package


def test_unauthenticated_rejected(client, db_session):
    _, asset, _ = _published_movie_with_package(db_session)
    assert client.get(f"/api/me/watch-progress/{asset.id}").status_code == 401
    assert client.put(f"/api/me/watch-progress/{asset.id}", json={"position_seconds": 40, "duration_seconds": 600}).status_code == 401


def test_admin_token_forbidden(client, db_session):
    _, asset, _ = _published_movie_with_package(db_session)
    token = _admin_token(db_session)
    resp = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=_headers(token),
        json={"position_seconds": 40, "duration_seconds": 600},
    )
    assert resp.status_code == 403


def test_upsert_progress_and_continue_watching(client, db_session):
    user, token = _subscriber(db_session)
    movie, asset, _ = _published_movie_with_package(db_session)
    headers = _headers(token)

    # Below threshold — history exists but not Continue Watching
    low = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 10, "duration_seconds": 600, "event_at": utcnow().isoformat()},
    )
    assert low.status_code == 200
    assert low.json()["position_seconds"] == 10
    cw = client.get("/api/me/continue-watching", headers=headers).json()
    assert all(i["media_asset_id"] != asset.id for i in cw)

    mid = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 120, "duration_seconds": 600, "event_at": (utcnow() + timedelta(seconds=1)).isoformat()},
    )
    assert mid.status_code == 200
    assert mid.json()["progress_percent"] == 20.0
    cw = client.get("/api/me/continue-watching", headers=headers).json()
    assert any(i["media_asset_id"] == asset.id and i["player_path"] == f"/player/movie/{movie.id}" for i in cw)

    # One row only
    assert db_session.query(UserWatchProgress).filter(UserWatchProgress.subscriber_id == user.id).count() == 1


def test_stale_update_ignored(client, db_session):
    _, token = _subscriber(db_session, username="stale-user")
    _, asset, _ = _published_movie_with_package(db_session, slug="stale-movie")
    headers = _headers(token)
    t1 = utcnow()
    client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 200, "duration_seconds": 600, "event_at": t1.isoformat()},
    )
    stale = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={
            "position_seconds": 50,
            "duration_seconds": 600,
            "event_at": (t1 - timedelta(seconds=30)).isoformat(),
        },
    )
    assert stale.status_code == 200
    assert stale.json()["position_seconds"] == 200


def test_negative_and_invalid_rejected(client, db_session):
    _, token = _subscriber(db_session, username="bad-pos")
    _, asset, _ = _published_movie_with_package(db_session, slug="bad-pos-movie")
    headers = _headers(token)
    assert (
        client.put(
            f"/api/me/watch-progress/{asset.id}",
            headers=headers,
            json={"position_seconds": -1, "duration_seconds": 600},
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/me/watch-progress/{asset.id}",
            headers=headers,
            json={"position_seconds": "not-a-number", "duration_seconds": 600},
        ).status_code
        == 422
    )


def test_completion_and_start_over(client, db_session):
    _, token = _subscriber(db_session, username="complete-user")
    _, asset, _ = _published_movie_with_package(db_session, slug="complete-movie")
    headers = _headers(token)
    done = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 550, "duration_seconds": 600, "event_at": utcnow().isoformat()},
    )
    assert done.status_code == 200
    assert done.json()["completed"] is True
    cw = client.get("/api/me/continue-watching", headers=headers).json()
    assert all(i["media_asset_id"] != asset.id for i in cw)
    hist = client.get("/api/me/watch-history", headers=headers).json()["data"]
    assert any(i["media_asset_id"] == asset.id and i["completed"] for i in hist)

    # Stale lower progress cannot roll back completion
    t_old = utcnow() - timedelta(minutes=1)
    client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 100, "duration_seconds": 600, "event_at": t_old.isoformat()},
    )
    current = client.get(f"/api/me/watch-progress/{asset.id}", headers=headers).json()
    assert current["completed"] is True

    reset = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={
            "position_seconds": 0,
            "duration_seconds": 600,
            "start_over": True,
            "event_at": (utcnow() + timedelta(seconds=2)).isoformat(),
        },
    )
    assert reset.status_code == 200
    assert reset.json()["completed"] is False
    assert reset.json()["position_seconds"] == 0


def test_idor_isolation(client, db_session):
    user_a, token_a = _subscriber(db_session, username="user-a")
    _, token_b = _subscriber(db_session, username="user-b")
    _, asset, _ = _published_movie_with_package(db_session, slug="idor-movie")
    client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=_headers(token_a),
        json={"position_seconds": 90, "duration_seconds": 600, "event_at": utcnow().isoformat()},
    )
    assert client.get(f"/api/me/watch-progress/{asset.id}", headers=_headers(token_b)).status_code == 404
    assert client.delete(f"/api/me/watch-history/{asset.id}", headers=_headers(token_b)).status_code == 404
    assert db_session.query(UserWatchProgress).filter(UserWatchProgress.subscriber_id == user_a.id).count() == 1


def test_unpublish_hides_continue_watching(client, db_session):
    _, token = _subscriber(db_session, username="unpub-user")
    movie, asset, _ = _published_movie_with_package(db_session, slug="unpub-movie")
    headers = _headers(token)
    client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 100, "duration_seconds": 600, "event_at": utcnow().isoformat()},
    )
    assert any(i["media_asset_id"] == asset.id for i in client.get("/api/me/continue-watching", headers=headers).json())
    movie.status = "unpublished"
    db_session.add(movie)
    db_session.commit()
    cw = client.get("/api/me/continue-watching", headers=headers).json()
    assert all(i["media_asset_id"] != asset.id for i in cw)
    hist = client.get("/api/me/watch-history", headers=headers).json()["data"]
    item = next(i for i in hist if i["media_asset_id"] == asset.id)
    assert item["available"] is False
    assert item["title"] == "Unavailable"
    assert item["player_path"] == ""


def test_clear_and_remove(client, db_session):
    _, token = _subscriber(db_session, username="clear-user")
    _, asset, _ = _published_movie_with_package(db_session, slug="clear-movie")
    headers = _headers(token)
    client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 80, "duration_seconds": 600, "event_at": utcnow().isoformat()},
    )
    assert client.delete(f"/api/me/watch-history/{asset.id}", headers=headers).status_code == 200
    assert client.get(f"/api/me/watch-progress/{asset.id}", headers=headers).status_code == 404
    client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=headers,
        json={"position_seconds": 80, "duration_seconds": 600, "event_at": utcnow().isoformat()},
    )
    cleared = client.delete("/api/me/watch-history", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] >= 1


def test_session_ownership_validation(client, db_session):
    user, token = _subscriber(db_session, username="sess-user")
    other, _ = _subscriber(db_session, username="sess-other")
    _, asset, package = _published_movie_with_package(db_session, slug="sess-movie")
    raw = generate_playback_token()
    session = MediaPlaybackSession(
        id=new_uuid(),
        media_asset_id=asset.id,
        media_package_id=package.id,
        principal_type=PRINCIPAL_SUBSCRIBER,
        principal_id=str(other.id),
        token_hash=hash_playback_token(raw),
        status=SESSION_ACTIVE,
        expires_at=utcnow() + timedelta(hours=1),
    )
    db_session.add(session)
    db_session.commit()
    resp = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=_headers(token),
        json={
            "position_seconds": 40,
            "duration_seconds": 600,
            "playback_session_id": session.id,
            "event_at": utcnow().isoformat(),
        },
    )
    assert resp.status_code == 403
    # Valid session for same user
    session.principal_id = str(user.id)
    db_session.add(session)
    db_session.commit()
    ok = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=_headers(token),
        json={
            "position_seconds": 40,
            "duration_seconds": 600,
            "playback_session_id": session.id,
            "event_at": utcnow().isoformat(),
        },
    )
    assert ok.status_code == 200
