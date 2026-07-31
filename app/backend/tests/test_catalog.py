"""Catalog administration and public API tests."""

from __future__ import annotations

from app.models.content import Movie
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.services.storage import ensure_media_layout, media_root, relative_media_path
from app.services.streaming.activation import activate_completed_package


def _seed_pkg(db_session, *, movie_id=None, episode_id=None):
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


def _workflow_publish_movie(client, admin_headers, db_session, movie_id: int) -> None:
    movie = db_session.get(Movie, movie_id)
    # Ensure readiness metadata
    if not movie.description:
        movie.description = "Synopsis for publish readiness"
    if not movie.poster_url:
        movie.poster_url = "https://placehold.co/300x450"
    if not movie.backdrop_url:
        movie.backdrop_url = "https://placehold.co/1920x800"
    if movie.release_year is None:
        movie.release_year = 2024
    db_session.add(movie)
    db_session.commit()
    if not movie.genre_links:
        genre = client.post(
            "/api/admin/genres",
            headers=admin_headers,
            json={"name": f"G{movie_id}", "slug": f"g-{movie_id}"},
        ).json()
        client.patch(
            f"/api/admin/movies/{movie_id}",
            headers=admin_headers,
            json={"genre_ids": [genre["id"]]},
        )
    _seed_pkg(db_session, movie_id=movie_id)
    assert client.post(f"/api/admin/catalog/movie/{movie_id}/submit-review", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/movie/{movie_id}/approve", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/movie/{movie_id}/publish", headers=admin_headers, json={}).status_code == 200


def test_unauthorized_admin_access(client):
    assert client.get("/api/admin/movies").status_code == 401
    assert client.post("/api/admin/movies", json={"title": "X"}).status_code == 401


def test_movie_creation_and_validation(client, admin_headers):
    bad = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "   ", "imdb_rating": 11},
    )
    assert bad.status_code == 422

    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={
            "title": "Catalog Film",
            "slug": "catalog-film",
            "release_year": 2024,
            "status": "draft",
            "poster_url": "https://placehold.co/300x450",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "catalog-film"
    assert body["status"] == "draft"

    dup = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Other", "slug": "catalog-film"},
    )
    assert dup.status_code == 409


def test_movie_update_soft_delete_and_publish(client, admin_headers, db_session):
    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={
            "title": "Publish Me",
            "slug": "publish-me",
            "status": "draft",
            "description": "Ready synopsis",
            "release_year": 2024,
            "poster_url": "https://placehold.co/300x450",
            "backdrop_url": "https://placehold.co/1920x800",
        },
    )
    movie_id = created.json()["id"]

    updated = client.patch(
        f"/api/admin/movies/{movie_id}",
        headers=admin_headers,
        json={"is_featured": True, "is_trending": True},
    )
    assert updated.status_code == 200
    assert updated.json()["is_featured"] is True

    _workflow_publish_movie(client, admin_headers, db_session, movie_id)

    public = client.get(f"/api/movies/{movie_id}")
    assert public.status_code == 200

    client.post(f"/api/admin/catalog/movie/{movie_id}/unpublish", headers=admin_headers, json={})
    assert client.get(f"/api/movies/{movie_id}").status_code == 404

    # republish from unpublished
    assert client.post(f"/api/admin/catalog/movie/{movie_id}/publish", headers=admin_headers, json={}).status_code == 200
    deleted = client.delete(f"/api/admin/movies/{movie_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/movies/{movie_id}").status_code == 404
    assert client.get(f"/api/admin/movies/{movie_id}", headers=admin_headers).status_code == 404


def test_public_endpoint_hides_drafts(client, admin_headers):
    client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Hidden Draft", "slug": "hidden-draft", "status": "draft"},
    )
    listed = client.get("/api/movies", params={"q": "Hidden Draft"})
    assert listed.status_code == 200
    items = listed.json().get("data") or listed.json().get("items") or []
    assert all(item["title"] != "Hidden Draft" for item in items)


def test_series_season_episode_hierarchy(client, admin_headers, db_session):
    series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={
            "title": "Hierarchy Show",
            "slug": "hierarchy-show",
            "status": "draft",
            "description": "Series synopsis",
            "release_year": 2024,
            "poster_url": "https://placehold.co/300x450",
            "backdrop_url": "https://placehold.co/1920x800",
        },
    )
    assert series.status_code == 201
    series_id = series.json()["id"]

    season = client.post(
        f"/api/admin/series/{series_id}/seasons",
        headers=admin_headers,
        json={"season_number": 1, "title": "S1", "status": "draft"},
    )
    assert season.status_code == 201
    season_id = season.json()["id"]

    dup_season = client.post(
        f"/api/admin/series/{series_id}/seasons",
        headers=admin_headers,
        json={"season_number": 1, "title": "S1 again"},
    )
    assert dup_season.status_code == 409

    episode = client.post(
        f"/api/admin/seasons/{season_id}/episodes",
        headers=admin_headers,
        json={"episode_number": 1, "title": "Pilot", "status": "draft"},
    )
    assert episode.status_code == 201
    episode_id = episode.json()["id"]

    dup_ep = client.post(
        f"/api/admin/seasons/{season_id}/episodes",
        headers=admin_headers,
        json={"episode_number": 1, "title": "Pilot 2"},
    )
    assert dup_ep.status_code == 409

    # Episode cannot publish from draft (invalid transition) without review chain + package
    bad_publish = client.post(f"/api/admin/episodes/{episode_id}/publish", headers=admin_headers)
    assert bad_publish.status_code == 400

    _seed_pkg(db_session, episode_id=episode_id)
    assert client.post(f"/api/admin/catalog/episode/{episode_id}/submit-review", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/episode/{episode_id}/approve", headers=admin_headers, json={}).status_code == 200
    ok = client.post(f"/api/admin/catalog/episode/{episode_id}/publish", headers=admin_headers, json={})
    assert ok.status_code == 200
    assert ok.json()["status"] == "published"

    # Season + series publish for public hierarchy
    assert client.post(f"/api/admin/catalog/season/{season_id}/submit-review", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/season/{season_id}/approve", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/season/{season_id}/publish", headers=admin_headers, json={}).status_code == 200

    genre = client.post(
        "/api/admin/genres",
        headers=admin_headers,
        json={"name": "Hierarchy", "slug": "hierarchy-genre"},
    ).json()
    client.patch(f"/api/admin/series/{series_id}", headers=admin_headers, json={"genre_ids": [genre["id"]]})
    assert client.post(f"/api/admin/catalog/series/{series_id}/submit-review", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/series/{series_id}/approve", headers=admin_headers, json={}).status_code == 200
    assert client.post(f"/api/admin/catalog/series/{series_id}/publish", headers=admin_headers, json={}).status_code == 200


def test_genre_creation_and_delete_blocked_when_in_use(client, admin_headers):
    genre = client.post(
        "/api/admin/genres",
        headers=admin_headers,
        json={"name": "Noir", "slug": "noir"},
    )
    assert genre.status_code == 201
    genre_id = genre.json()["id"]

    movie = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Noir Film", "slug": "noir-film", "genre_ids": [genre_id]},
    )
    assert movie.status_code == 201

    blocked = client.delete(f"/api/admin/genres/{genre_id}", headers=admin_headers)
    assert blocked.status_code == 409

    client.delete(f"/api/admin/movies/{movie.json()['id']}", headers=admin_headers)
    allowed = client.delete(f"/api/admin/genres/{genre_id}", headers=admin_headers)
    assert allowed.status_code == 200


def test_pagination_filtering_search_sorting(client, admin_headers, db_session):
    genre = client.post(
        "/api/admin/genres",
        headers=admin_headers,
        json={"name": "Adventure", "slug": "adventure-filter"},
    ).json()
    for i, year in enumerate([2020, 2021, 2022], start=1):
        created = client.post(
            "/api/admin/movies",
            headers=admin_headers,
            json={
                "title": f"Sort Film {i}",
                "slug": f"sort-film-{i}",
                "release_year": year,
                "language": "Dari",
                "imdb_rating": float(i),
                "is_featured": i == 2,
                "is_trending": i == 3,
                "status": "draft",
                "description": "Synopsis",
                "poster_url": "https://placehold.co/300x450",
                "backdrop_url": "https://placehold.co/1920x800",
                "genre_ids": [genre["id"]],
            },
        )
        assert created.status_code == 201
        _workflow_publish_movie(client, admin_headers, db_session, created.json()["id"])

    page = client.get("/api/movies", params={"page": 1, "page_size": 2, "q": "Sort Film"})
    assert page.status_code == 200
    meta = page.json()["meta"]
    assert meta["page_size"] == 2
    assert meta["total"] >= 3
    items_key = "data" if "data" in page.json() else "items"

    filtered = client.get(
        "/api/movies",
        params={"genre": "adventure-filter", "year": 2021, "language": "Dari", "featured": True},
    )
    assert filtered.status_code == 200
    assert all(item["release_year"] == 2021 for item in filtered.json()[items_key])

    sorted_rating = client.get("/api/movies", params={"q": "Sort Film", "sort": "rating_desc"})
    assert sorted_rating.status_code == 200
    ratings = [item.get("imdb_rating") or 0 for item in sorted_rating.json()[items_key]]
    assert ratings == sorted(ratings, reverse=True)

    title_asc = client.get("/api/movies", params={"q": "Sort Film", "sort": "title_asc"})
    titles = [item["title"] for item in title_asc.json()[items_key]]
    assert titles == sorted(titles)
