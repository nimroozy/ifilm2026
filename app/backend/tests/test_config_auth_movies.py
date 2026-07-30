from tests.conftest import TEST_FIXTURE_PASSWORD, TEST_FIXTURE_USER


def test_health_and_config(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

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
            "year": 2026,
            "duration": 100,
            "rating": 8.0,
            "genres": ["Drama"],
            "description": "Test",
        },
    )
    assert created.status_code == 201
    movie_id = created.json()["id"]

    listed = client.get("/api/movies")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    detail = client.get(f"/api/movies/{movie_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Test Film"

    updated = client.patch(
        f"/api/admin/movies/{movie_id}",
        headers=admin_headers,
        json={"featured": True},
    )
    assert updated.status_code == 200
    assert updated.json()["featured"] is True


def test_series_and_stream_manifest(client, admin_headers):
    series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={"title": "Test Series", "year": 2026, "seasons": 1, "episode_count": 0},
    )
    assert series.status_code == 201
    series_id = series.json()["id"]

    episode = client.post(
        f"/api/admin/series/{series_id}/episodes",
        headers=admin_headers,
        json={"season": 1, "episode": 1, "title": "Pilot", "duration": 45},
    )
    assert episode.status_code == 201

    movies = client.get("/api/movies").json()["items"]
    assert movies
    movie_id = movies[0]["id"]
    stream = client.get(f"/api/stream/movie/{movie_id}")
    assert stream.status_code == 200
    body = stream.json()
    assert body["playlist_url"].endswith("master.m3u8")
    assert body["qualities"]


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
