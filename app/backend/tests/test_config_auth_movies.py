from tests.conftest import TEST_FIXTURE_PASSWORD, TEST_FIXTURE_USER


def test_health_and_config(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/live").status_code == 200
    ready = client.get("/api/health/ready")
    assert ready.status_code in (200, 503)

    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json()["API_BASE_URL"] == "/"


def test_subscriber_login_via_mock_radius_fixture(client):
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == TEST_FIXTURE_USER


def test_admin_auth_and_movie_crud(client, admin_headers):
    me = client.get("/api/admin/auth/me", headers=admin_headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert "movies" in me.json()["permissions"]

    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={
            "title": "Test Film",
            "original_title": "فیلم آزمایشی",
            "release_year": 2026,
            "duration_minutes": 100,
            "imdb_rating": 8.0,
            "genre_ids": [],
            "description": "Test",
            "status": "published",
        },
    )
    assert created.status_code == 201
    movie_id = created.json()["id"]

    listed = client.get("/api/movies")
    assert listed.status_code == 200
    body = listed.json()
    assert body["meta"]["total"] >= 1
    assert isinstance(body["data"], list)

    detail = client.get(f"/api/movies/{movie_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Test Film"

    updated = client.patch(
        f"/api/admin/movies/{movie_id}",
        headers=admin_headers,
        json={"is_featured": True},
    )
    assert updated.status_code == 200
    assert updated.json()["featured"] is True
    assert updated.json()["is_featured"] is True


def test_series_seasons_episodes_and_stream(client, admin_headers):
    series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={"title": "Test Series", "release_year": 2026, "status": "published"},
    )
    assert series.status_code == 201
    series_id = series.json()["id"]

    season = client.post(
        f"/api/admin/series/{series_id}/seasons",
        headers=admin_headers,
        json={"season_number": 1, "title": "Season 1", "status": "published"},
    )
    assert season.status_code == 201
    season_id = season.json()["id"]

    episode = client.post(
        f"/api/admin/seasons/{season_id}/episodes",
        headers=admin_headers,
        json={"episode_number": 1, "title": "Pilot", "duration_minutes": 45, "status": "published"},
    )
    assert episode.status_code == 201
    assert episode.json()["series_id"] == series_id

    movies = client.get("/api/movies").json()["data"]
    assert movies
    movie_id = movies[0]["id"]
    stream = client.get(f"/api/stream/movie/{movie_id}")
    assert stream.status_code == 200
    body = stream.json()
    assert body["playlist_url"].endswith("master.m3u8")
    assert body["qualities"]


def test_genres_and_dashboard_stats(client, admin_headers):
    created = client.post(
        "/api/admin/genres",
        headers=admin_headers,
        json={"name": "Thriller", "description": "Suspense"},
    )
    assert created.status_code == 201
    genre_id = created.json()["id"]

    genres = client.get("/api/genres")
    assert genres.status_code == 200
    assert genres.json()["meta"]["total"] >= 1

    stats = client.get("/api/admin/dashboard/stats", headers=admin_headers)
    assert stats.status_code == 200
    payload = stats.json()
    assert payload["total_genres"] >= 1
    assert "total_movies" in payload

    # Genre with no assignments can be deleted
    deleted = client.delete(f"/api/admin/genres/{genre_id}", headers=admin_headers)
    assert deleted.status_code == 200


def test_hls_service_and_cdn_sync(client, admin_headers):
    from app.services.hls import build_master_playlist, write_placeholder_package
    from app.services.radius import RadiusService

    playlist = build_master_playlist(["720p", "480p"])
    assert "#EXTM3U" in playlist
    assert "720p/index.m3u8" in playlist

    relative = write_placeholder_package("movie", 999, ["720p"])
    assert relative.startswith("movie/999")

    result = RadiusService().authenticate(TEST_FIXTURE_USER, TEST_FIXTURE_PASSWORD)
    assert result.success is True

    nodes = client.get("/api/admin/cdn/nodes", headers=admin_headers)
    assert nodes.status_code == 200
    assert len(nodes.json()) >= 1

    sync = client.post(
        "/api/admin/cdn/sync",
        headers=admin_headers,
        json={"content_type": "movie", "content_id": 1, "hls_path": "movie/1"},
    )
    assert sync.status_code == 200
    assert all(item["status"] in {"completed", "failed", "syncing", "pending"} for item in sync.json())
