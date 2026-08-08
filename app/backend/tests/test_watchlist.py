"""Subscriber watchlist + continue-watching dismiss tests."""

from __future__ import annotations

from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Genre, Movie, Series
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.models.user import Subscriber, WatchlistItem
from app.models.watch_progress import UserWatchProgress
from app.services.storage import ensure_media_layout
from app.services.streaming.activation import activate_completed_package


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _subscriber(db_session, *, username: str = "wl-user") -> tuple[Subscriber, str]:
    user = Subscriber(
        username=username,
        hashed_password=None,
        name=username,
        status="active",
        package="Standard",
        service_status="active",
        identity_provider="local",
        max_devices=3,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(str(user.id), {"typ": "subscriber", "username": user.username})
    return user, token


def _admin_token(db_session) -> str:
    role = AdminRole(name=f"wl-role-{new_uuid()[:6]}", permissions=["movies.manage"])
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=f"wl-admin-{new_uuid()[:6]}",
        email=f"{new_uuid()[:6]}@ex.test",
        full_name="WL Admin",
        hashed_password=hash_password("admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _published_movie(db_session, *, slug: str = "wl-movie") -> Movie:
    g = Genre(name="WL", slug=f"wl-{new_uuid()[:6]}")
    db_session.add(g)
    db_session.flush()
    movie = Movie(
        title="Watchlist Movie",
        slug=slug,
        description="Synopsis",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="published",
        published_at=utcnow(),
        duration_minutes=100,
    )
    movie.genre_links = [g]
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _published_series(db_session, *, slug: str = "wl-series") -> Series:
    g = Genre(name="WLS", slug=f"wls-{new_uuid()[:6]}")
    db_session.add(g)
    db_session.flush()
    series = Series(
        title="Watchlist Series",
        slug=slug,
        description="Series synopsis",
        release_year=2023,
        poster_url="https://example.test/sp.jpg",
        backdrop_url="https://example.test/sb.jpg",
        status="published",
        published_at=utcnow(),
    )
    series.genre_links = [g]
    db_session.add(series)
    db_session.commit()
    db_session.refresh(series)
    return series


def test_watchlist_crud_movie_and_series(client, db_session):
    user, token = _subscriber(db_session)
    movie = _published_movie(db_session, slug=f"wl-m-{new_uuid()[:6]}")
    series = _published_series(db_session, slug=f"wl-s-{new_uuid()[:6]}")

    add_m = client.post("/api/me/watchlist", headers=_headers(token), json={"movie_id": movie.id})
    assert add_m.status_code == 201, add_m.text
    body = add_m.json()
    assert body["content_type"] == "movie"
    assert body["movie_id"] == movie.id
    assert body["available"] is True
    assert body["detail_path"] == f"/movie/{movie.slug}"

    add_s = client.post("/api/me/watchlist", headers=_headers(token), json={"series_id": series.id})
    assert add_s.status_code == 201, add_s.text
    assert add_s.json()["content_type"] == "series"

    listed = client.get("/api/me/watchlist", headers=_headers(token))
    assert listed.status_code == 200
    data = listed.json()["data"]
    assert len(data) == 2
    assert {row["content_type"] for row in data} == {"movie", "series"}

    mem = client.get(
        "/api/me/watchlist/membership",
        headers=_headers(token),
        params={"movie_id": movie.id},
    )
    assert mem.status_code == 200
    assert mem.json()["in_watchlist"] is True
    assert mem.json()["item_id"] == add_m.json()["id"]

    removed = client.delete(f"/api/me/watchlist/{add_m.json()['id']}", headers=_headers(token))
    assert removed.status_code == 200
    assert removed.json()["deleted"] == 1

    cleared = client.delete("/api/me/watchlist", headers=_headers(token))
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 1

    empty = client.get("/api/me/watchlist", headers=_headers(token))
    assert empty.json()["meta"]["total"] == 0


def test_watchlist_duplicate_and_xor_validation(client, db_session):
    _, token = _subscriber(db_session, username="wl-dup")
    movie = _published_movie(db_session, slug=f"wl-dup-{new_uuid()[:6]}")

    first = client.post("/api/me/watchlist", headers=_headers(token), json={"movie_id": movie.id})
    assert first.status_code == 201
    dup = client.post("/api/me/watchlist", headers=_headers(token), json={"movie_id": movie.id})
    assert dup.status_code == 409

    both = client.post(
        "/api/me/watchlist",
        headers=_headers(token),
        json={"movie_id": movie.id, "series_id": 1},
    )
    assert both.status_code == 422

    neither = client.post("/api/me/watchlist", headers=_headers(token), json={})
    assert neither.status_code == 422


def test_watchlist_authz(client, db_session):
    movie = _published_movie(db_session, slug=f"wl-auth-{new_uuid()[:6]}")
    anon = client.get("/api/me/watchlist")
    assert anon.status_code == 401

    admin = client.get("/api/me/watchlist", headers=_headers(_admin_token(db_session)))
    assert admin.status_code == 403

    user_a, token_a = _subscriber(db_session, username="wl-a")
    user_b, token_b = _subscriber(db_session, username="wl-b")
    added = client.post("/api/me/watchlist", headers=_headers(token_a), json={"movie_id": movie.id})
    assert added.status_code == 201
    # Other subscriber cannot delete A's item by id
    denied = client.delete(f"/api/me/watchlist/{added.json()['id']}", headers=_headers(token_b))
    assert denied.status_code == 404
    assert db_session.get(WatchlistItem, added.json()["id"]) is not None
    assert user_a.id != user_b.id


def test_watchlist_tombstone_unpublished(client, db_session):
    _, token = _subscriber(db_session, username="wl-tomb")
    movie = _published_movie(db_session, slug=f"wl-tomb-{new_uuid()[:6]}")
    added = client.post("/api/me/watchlist", headers=_headers(token), json={"movie_id": movie.id})
    assert added.status_code == 201
    movie.status = "draft"
    movie.published_at = None
    db_session.add(movie)
    db_session.commit()

    listed = client.get("/api/me/watchlist", headers=_headers(token))
    row = listed.json()["data"][0]
    assert row["available"] is False
    assert row["title"] == "Unavailable"
    assert row["poster_url"] == ""
    assert row["detail_path"] == ""


def test_watchlist_delete_does_not_cascade_catalog(client, db_session):
    _, token = _subscriber(db_session, username="wl-cascade")
    movie = _published_movie(db_session, slug=f"wl-cas-{new_uuid()[:6]}")
    mid = movie.id
    added = client.post("/api/me/watchlist", headers=_headers(token), json={"movie_id": mid})
    client.delete(f"/api/me/watchlist/{added.json()['id']}", headers=_headers(token))
    assert db_session.get(Movie, mid) is not None


def test_dismiss_continue_watching_keeps_history(client, db_session):
    from app.services.storage import media_root, relative_media_path

    user, token = _subscriber(db_session, username="cw-dismiss")
    ensure_media_layout()
    movie = _published_movie(db_session, slug=f"cw-d-{new_uuid()[:6]}")
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
    pkg_dir.mkdir(parents=True, exist_ok=True)
    rendition = pkg_dir / "240p"
    rendition.mkdir(parents=True, exist_ok=True)
    (rendition / "segment_000.ts").write_bytes(b"\x00\x01" * 32)
    (rendition / "index.m3u8").write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nsegment_000.ts\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    (pkg_dir / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=400000\n240p/index.m3u8\n",
        encoding="utf-8",
    )
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

    put = client.put(
        f"/api/me/watch-progress/{asset.id}",
        headers=_headers(token),
        json={
            "position_seconds": 120,
            "duration_seconds": 600,
            "event_at": utcnow().isoformat(),
        },
    )
    assert put.status_code == 200, put.text
    cw = client.get("/api/me/continue-watching", headers=_headers(token))
    assert cw.status_code == 200
    assert len(cw.json()) == 1

    dismissed = client.delete(f"/api/me/continue-watching/{asset.id}", headers=_headers(token))
    assert dismissed.status_code == 200
    cw2 = client.get("/api/me/continue-watching", headers=_headers(token))
    assert cw2.json() == []

    hist = client.get("/api/me/watch-history", headers=_headers(token))
    assert hist.json()["meta"]["total"] == 1
    row = db_session.query(UserWatchProgress).filter_by(subscriber_id=user.id).one()
    assert row.hidden_from_continue is True
