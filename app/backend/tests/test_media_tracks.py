"""Media track metadata storage, RBAC, and playback session exposure."""

from __future__ import annotations

from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Genre, Movie
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.models.media_tracks import MediaTrack
from app.models.user import Subscriber
from app.services.catalog_availability import availability_for_movie, build_audio_availability
from app.services.storage import ensure_media_layout, media_root, relative_media_path
from app.services.streaming.activation import activate_completed_package


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db_session, *, username: str, permissions: list[str]) -> str:
    role = AdminRole(name=f"role-{username}-{new_uuid()[:6]}", permissions=permissions)
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=username,
        email=f"{username}@example.test",
        full_name=username,
        hashed_password=hash_password("tracks-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _asset(db_session, *, movie_id: int | None = None) -> MediaAsset:
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
        duration_seconds=600.0,
        probed_at=utcnow(),
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_track_crud_and_permissions(client, db_session):
    reader = _make_admin(db_session, username="track-reader", permissions=["processing.read"])
    manager = _make_admin(db_session, username="track-manager", permissions=["processing.manage"])
    other = _make_admin(db_session, username="movies-only", permissions=["movies.manage"])
    asset = _asset(db_session)

    assert (
        client.get(f"/api/admin/media/assets/{asset.id}/tracks", headers=_headers(other)).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/admin/media/assets/{asset.id}/tracks",
            headers=_headers(reader),
            json={"track_type": "audio", "language_code": "en"},
        ).status_code
        == 403
    )

    listed = client.get(f"/api/admin/media/assets/{asset.id}/tracks", headers=_headers(reader))
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    created = client.post(
        f"/api/admin/media/assets/{asset.id}/tracks",
        headers=_headers(manager),
        json={
            "track_type": "audio",
            "language_code": "Persian",
            "is_default": True,
            "is_dubbed": True,
            "label_key": "audio.persian_dub",
            "hls_group_id": "audio",
            "sort_order": 1,
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["language_code"] == "fa"
    assert body["is_dubbed"] is True
    assert body["label_key"] == "audio.persian_dub"
    assert "دوبله" not in (body.get("label_key") or "")

    sub = client.post(
        f"/api/admin/media/assets/{asset.id}/tracks",
        headers=_headers(manager),
        json={"track_type": "subtitle", "language_code": "ps", "is_default": True},
    )
    assert sub.status_code == 200
    assert sub.json()["is_dubbed"] is False

    listed2 = client.get(f"/api/admin/media/assets/{asset.id}/tracks", headers=_headers(reader))
    assert listed2.status_code == 200
    payload = listed2.json()
    assert len(payload["audio"]) == 1
    assert len(payload["subtitles"]) == 1

    patched = client.patch(
        f"/api/admin/media/tracks/{body['id']}",
        headers=_headers(manager),
        json={"is_default": False, "sort_order": 5},
    )
    assert patched.status_code == 200
    assert patched.json()["sort_order"] == 5

    deleted = client.delete(
        f"/api/admin/media/tracks/{body['id']}",
        headers=_headers(manager),
    )
    assert deleted.status_code == 204


def test_packaged_tracks_drive_availability_with_dubbed_flag(db_session):
    g = Genre(name="Tracks", slug=f"tracks-{new_uuid()[:6]}")
    db_session.add(g)
    db_session.flush()
    movie = Movie(
        title="Multi Audio",
        slug=f"multi-audio-{new_uuid()[:6]}",
        description="Synopsis",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        status="published",
        published_at=utcnow(),
        language="English",
    )
    movie.genre_links = [g]
    db_session.add(movie)
    db_session.flush()
    asset = _asset(db_session, movie_id=movie.id)
    db_session.add_all(
        [
            MediaTrack(
                media_asset_id=asset.id,
                track_type="audio",
                language_code="en",
                is_default=True,
                is_dubbed=False,
                hls_group_id="audio",
                sort_order=0,
                created_at=utcnow(),
                updated_at=utcnow(),
            ),
            MediaTrack(
                media_asset_id=asset.id,
                track_type="audio",
                language_code="fa",
                is_default=False,
                is_dubbed=True,
                hls_group_id="audio",
                sort_order=1,
                created_at=utcnow(),
                updated_at=utcnow(),
            ),
            MediaTrack(
                media_asset_id=asset.id,
                track_type="subtitle",
                language_code="ps",
                is_default=True,
                is_dubbed=False,
                hls_group_id="subs",
                sort_order=0,
                created_at=utcnow(),
                updated_at=utcnow(),
            ),
        ]
    )
    db_session.commit()

    audio, subs = availability_for_movie(movie, db_session, has_playable_package=True)
    assert audio.source == "package_manifest"
    assert audio.languages == ["en", "fa"]
    assert audio.dubbed_languages == ["fa"]
    assert audio.selectable_in_player is True
    assert subs.languages == ["ps"]
    assert subs.selectable_in_player is True


def test_build_audio_uses_is_dubbed_not_translated_labels():
    class FakeTrack:
        language_code = "fa"
        is_dubbed = True
        hls_group_id = "audio"

    audio = build_audio_availability(
        language="en",
        packaged_audio_tracks=[FakeTrack()],
    )
    assert audio.dubbed_languages == ["fa"]
    assert audio.source == "package_manifest"


def test_playback_session_includes_tracks(client, db_session, monkeypatch):
    monkeypatch.setenv("ENABLE_STREAMING", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    g = Genre(name="PlayTracks", slug=f"play-tracks-{new_uuid()[:6]}")
    db_session.add(g)
    db_session.flush()
    movie = Movie(
        title="Play Tracks",
        slug=f"play-tracks-{new_uuid()[:6]}",
        description="Synopsis",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        status="published",
        published_at=utcnow(),
    )
    movie.genre_links = [g]
    db_session.add(movie)
    db_session.flush()
    asset = _asset(db_session, movie_id=movie.id)
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
    db_session.add(
        MediaTrack(
            media_asset_id=asset.id,
            track_type="audio",
            language_code="en",
            is_default=True,
            is_dubbed=False,
            sort_order=0,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    db_session.add(
        MediaTrack(
            media_asset_id=asset.id,
            track_type="audio",
            language_code="fa",
            is_default=False,
            is_dubbed=True,
            sort_order=1,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    db_session.flush()
    activate_completed_package(db_session, package)
    user = Subscriber(
        username=f"track-watcher-{new_uuid()[:6]}",
        hashed_password=None,
        name="Track Watcher",
        status="active",
        package="Standard",
        service_status="active",
        identity_provider="local",
        external_subject=None,
        max_devices=3,
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(str(user.id), {"typ": "subscriber", "username": user.username})

    resp = client.post(
        "/api/playback/sessions",
        headers=_headers(token),
        json={"content_type": "movie", "content_id": movie.id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["audio_tracks"]) == 2
    assert {t["language_code"] for t in data["audio_tracks"]} == {"en", "fa"}
    assert any(t["is_dubbed"] for t in data["audio_tracks"])
    get_settings.cache_clear()
