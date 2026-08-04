"""API coverage for manual movie/series create + external media attach."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.media_assets import MediaAsset
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.services.media_external import ExternalMediaValidation
from app.services.storage import media_root


def test_manual_movie_create_draft(client, admin_headers) -> None:
    response = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={
            "title": "Manual Draft Film",
            "description": "Created without TMDB",
            "release_year": 2024,
            "duration_minutes": 100,
            "language": "en",
            "country": "AF",
            "age_rating": "PG",
            "director": "A Director",
            "producer": "A Producer",
            "writer": "A Writer",
            "studio": "iFilm Studio",
            "is_featured": False,
            "is_trending": False,
            "genre_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Manual Draft Film"
    assert body["status"] == "draft"
    assert body["slug"]
    assert body["playable"] is False


def test_attach_external_media_sets_playable(client, admin_headers, db_session, monkeypatch) -> None:
    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "External Hosted", "description": "x", "genre_ids": []},
    )
    assert created.status_code == 201
    movie_id = created.json()["id"]

    monkeypatch.setattr(
        "app.services.media_external_attach.validate_external_media_url",
        lambda url: ExternalMediaValidation(
            url=url,
            kind="hls",
            content_type="application/vnd.apple.mpegurl",
            content_length=100,
            accept_ranges=True,
            validated_at=datetime.now(UTC),
        ),
    )
    attach = client.post(
        "/api/admin/media/external",
        headers=admin_headers,
        json={
            "url": "https://cdn.example.com/movie/master.m3u8",
            "owner_type": "movie",
            "owner_id": movie_id,
        },
    )
    assert attach.status_code == 201, attach.text
    asset = attach.json()
    assert asset["source_type"] == "external"
    assert asset["external_url"].endswith("master.m3u8")

    detail = client.get(f"/api/admin/movies/{movie_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["playable"] is True
    assert detail.json()["has_external_media"] is True


def test_uploaded_package_marks_playable(client, admin_headers, db_session) -> None:
    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Packaged Film", "description": "x", "genre_ids": []},
    )
    movie_id = created.json()["id"]
    asset = MediaAsset(
        movie_id=movie_id,
        original_filename="pack.mp4",
        stored_filename="pack.mp4",
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=10,
        storage_backend="local",
        storage_path="originals/pack.mp4",
        category="originals",
        upload_status="completed",
        processing_status="ready",
        source_type="uploaded",
    )
    db_session.add(asset)
    db_session.flush()
    package = MediaPackage(
        media_asset_id=asset.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="completed",
        is_active=True,
        master_playlist_path="packages/x/master.m3u8",
    )
    db_session.add(package)
    db_session.commit()

    master = media_root() / "packages/x/master.m3u8"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_text("#EXTM3U\n", encoding="utf-8")

    db_session.add(
        MediaRendition(
            package_id=package.id,
            label="720p",
            height=720,
            status="completed",
            playlist_path="packages/x/720p.m3u8",
        )
    )
    db_session.commit()

    detail = client.get(f"/api/admin/movies/{movie_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["playable"] is True
    assert body["has_playable_package"] is True
    assert body["has_external_media"] is False


def test_manual_series_season_episode(client, admin_headers) -> None:
    series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={"title": "Manual Series CMS Z9", "description": "no tmdb", "genre_ids": []},
    )
    assert series.status_code == 201, series.text
    series_id = series.json()["id"]
    assert series.json()["status"] == "draft"

    season = client.post(
        f"/api/admin/series/{series_id}/seasons",
        headers=admin_headers,
        json={"season_number": 3, "title": "Season Three CMS"},
    )
    assert season.status_code == 201, season.text
    season_id = season.json()["id"]
    assert season.json()["series_id"] == series_id

    episode = client.post(
        f"/api/admin/seasons/{season_id}/episodes",
        headers=admin_headers,
        json={
            "episode_number": 9,
            "title": "Manual Episode Nine CMS",
            "description": "Pilot",
            "duration_minutes": 42,
        },
    )
    assert episode.status_code == 201, episode.text
    body = episode.json()
    assert body["season_id"] == season_id
    assert body["series_id"] == series_id
    assert body["episode_number"] == 9
    assert body["title"] == "Manual Episode Nine CMS"
    assert body["playable"] is False
    assert body["status"] == "draft"
