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
    assert body["producer"] == "A Producer"
    assert body["writer"] == "A Writer"
    assert body["studio"] == "iFilm Studio"
    assert body.get("tmdb_id") in (None, 0) or body.get("tmdb_id") is None


def test_manual_movie_duplicate_slug(client, admin_headers) -> None:
    first = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Dup Slug One", "slug": "manual-dup-slug", "genre_ids": []},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Dup Slug Two", "slug": "manual-dup-slug", "genre_ids": []},
    )
    assert second.status_code == 409
    assert "slug" in second.json()["detail"].lower()


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
            "acknowledge_unprotected_external": True,
        },
    )
    assert attach.status_code == 201, attach.text
    asset = attach.json()
    assert asset["source_type"] == "external"
    assert asset["external_url"].endswith("master.m3u8")

    detail = client.get(f"/api/admin/movies/{movie_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["has_external_media"] is True
    # Option A: non-demo external is not customer-playable
    assert body["playable"] is False
    assert body["has_playable_package"] is False
    asset_detail = attach.json()
    assert asset_detail["external_is_primary"] is True
    assert asset_detail["external_protection_mode"] == "unprotected_direct"
    assert "token=" not in (asset_detail.get("external_url") or "")


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


def test_season_and_episode_uniqueness(client, admin_headers) -> None:
    series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={"title": "Unique Hierarchy CMS", "description": "x", "genre_ids": []},
    )
    series_id = series.json()["id"]
    season = client.post(
        f"/api/admin/series/{series_id}/seasons",
        headers=admin_headers,
        json={"season_number": 1, "title": "S1"},
    )
    assert season.status_code == 201
    season_id = season.json()["id"]
    dup_season = client.post(
        f"/api/admin/series/{series_id}/seasons",
        headers=admin_headers,
        json={"season_number": 1, "title": "S1 again"},
    )
    assert dup_season.status_code == 409

    ep = client.post(
        f"/api/admin/seasons/{season_id}/episodes",
        headers=admin_headers,
        json={"episode_number": 1, "title": "E1", "description": "d"},
    )
    assert ep.status_code == 201
    assert ep.json()["series_id"] == series_id
    assert ep.json().get("movie_id") in (None, 0) or "movie_id" not in ep.json()
    dup_ep = client.post(
        f"/api/admin/seasons/{season_id}/episodes",
        headers=admin_headers,
        json={"episode_number": 1, "title": "E1 again", "description": "d"},
    )
    assert dup_ep.status_code == 409


def test_attach_requires_acknowledgement(client, admin_headers) -> None:
    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Need Ack", "description": "x", "genre_ids": []},
    )
    movie_id = created.json()["id"]
    attach = client.post(
        "/api/admin/media/external",
        headers=admin_headers,
        json={
            "url": "https://cdn.example.com/film.mp4",
            "owner_type": "movie",
            "owner_id": movie_id,
            "acknowledge_unprotected_external": False,
        },
    )
    assert attach.status_code == 400
    assert "acknowledge" in attach.json()["detail"].lower()


def test_external_validation_failure_does_not_attach(client, admin_headers, monkeypatch) -> None:
    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Fail Ext", "description": "x", "genre_ids": []},
    )
    movie_id = created.json()["id"]

    def _boom(url: str):
        from app.services.media_external import ExternalMediaError

        raise ExternalMediaError("unreachable", "External media URL is unreachable")

    monkeypatch.setattr("app.services.media_external_attach.validate_external_media_url", _boom)
    attach = client.post(
        "/api/admin/media/external",
        headers=admin_headers,
        json={
            "url": "https://cdn.example.com/missing.mp4",
            "owner_type": "movie",
            "owner_id": movie_id,
            "acknowledge_unprotected_external": True,
        },
    )
    assert attach.status_code == 400
    detail = client.get(f"/api/admin/movies/{movie_id}", headers=admin_headers)
    assert detail.json()["playable"] is False

