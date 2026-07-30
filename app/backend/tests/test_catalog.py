"""Catalog administration and public API tests."""

from __future__ import annotations


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


def test_movie_update_soft_delete_and_publish(client, admin_headers):
    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Publish Me", "slug": "publish-me", "status": "draft"},
    )
    movie_id = created.json()["id"]

    updated = client.patch(
        f"/api/admin/movies/{movie_id}",
        headers=admin_headers,
        json={"is_featured": True, "is_trending": True},
    )
    assert updated.status_code == 200
    assert updated.json()["is_featured"] is True

    published = client.post(f"/api/admin/movies/{movie_id}/publish", headers=admin_headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    public = client.get(f"/api/movies/{movie_id}")
    assert public.status_code == 200

    client.post(f"/api/admin/movies/{movie_id}/unpublish", headers=admin_headers)
    assert client.get(f"/api/movies/{movie_id}").status_code == 404

    client.post(f"/api/admin/movies/{movie_id}/publish", headers=admin_headers)
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
    assert all(item["title"] != "Hidden Draft" for item in listed.json()["data"])


def test_series_season_episode_hierarchy(client, admin_headers):
    series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={"title": "Hierarchy Show", "slug": "hierarchy-show", "status": "draft"},
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

    # Cannot publish episode while parents are draft
    bad_publish = client.post(f"/api/admin/episodes/{episode_id}/publish", headers=admin_headers)
    assert bad_publish.status_code == 400

    client.post(f"/api/admin/series/{series_id}/publish", headers=admin_headers)
    # season still draft
    still_bad = client.post(f"/api/admin/episodes/{episode_id}/publish", headers=admin_headers)
    assert still_bad.status_code == 400

    client.patch(
        f"/api/admin/seasons/{season_id}",
        headers=admin_headers,
        json={"status": "published"},
    )
    ok = client.post(f"/api/admin/episodes/{episode_id}/publish", headers=admin_headers)
    assert ok.status_code == 200
    assert ok.json()["status"] == "published"


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

    # Soft-deleted movies do not block genre deletion.
    client.delete(f"/api/admin/movies/{movie.json()['id']}", headers=admin_headers)
    allowed = client.delete(f"/api/admin/genres/{genre_id}", headers=admin_headers)
    assert allowed.status_code == 200


def test_pagination_filtering_search_sorting(client, admin_headers):
    genre = client.post(
        "/api/admin/genres",
        headers=admin_headers,
        json={"name": "Adventure", "slug": "adventure-filter"},
    ).json()
    for i, year in enumerate([2020, 2021, 2022], start=1):
        client.post(
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
                "status": "published",
                "genre_ids": [genre["id"]],
            },
        )

    page = client.get("/api/movies", params={"page": 1, "page_size": 2, "q": "Sort Film"})
    assert page.status_code == 200
    assert page.json()["meta"]["page_size"] == 2
    assert page.json()["meta"]["total"] >= 3

    filtered = client.get(
        "/api/movies",
        params={"genre": "adventure-filter", "year": 2021, "language": "Dari", "featured": True},
    )
    assert filtered.status_code == 200
    assert all(item["release_year"] == 2021 for item in filtered.json()["data"])

    sorted_rating = client.get("/api/movies", params={"q": "Sort Film", "sort": "rating_desc"})
    assert sorted_rating.status_code == 200
    ratings = [item.get("imdb_rating") or 0 for item in sorted_rating.json()["data"]]
    assert ratings == sorted(ratings, reverse=True)

    title_asc = client.get("/api/movies", params={"q": "Sort Film", "sort": "title_asc"})
    titles = [item["title"] for item in title_asc.json()["data"]]
    assert titles == sorted(titles)
