"""Public catalog must never expose draft, archived, or soft-deleted content."""

from __future__ import annotations

from app.models.content import Episode, Movie, Season, Series
from app.services.catalog import utcnow


def _force_published(db_session, model, entity_id: int) -> None:
    row = db_session.get(model, entity_id)
    row.status = "published"
    row.published_at = row.published_at or utcnow()
    row.deleted_at = None
    db_session.add(row)
    db_session.commit()


def _seed_visibility_matrix(admin_headers, client, db_session):
    """Create published + hidden catalog rows via admin API and ORM status force."""
    genre = client.post(
        "/api/admin/genres",
        headers=admin_headers,
        json={"name": "Isolation", "slug": "isolation"},
    ).json()

    published = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={
            "title": "Visible Movie",
            "slug": "visible-movie",
            "status": "draft",
            "is_featured": True,
            "is_trending": True,
            "genre_ids": [genre["id"]],
        },
    ).json()
    _force_published(db_session, Movie, published["id"])

    draft = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Draft Movie", "slug": "draft-movie", "status": "draft", "is_featured": True},
    ).json()

    archived = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Archived Movie", "slug": "archived-movie", "status": "draft", "is_trending": True},
    ).json()
    _force_published(db_session, Movie, archived["id"])
    client.delete(f"/api/admin/movies/{archived['id']}", headers=admin_headers)

    series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={
            "title": "Visible Series",
            "slug": "visible-series",
            "status": "draft",
            "is_featured": True,
            "is_trending": True,
            "genre_ids": [genre["id"]],
        },
    ).json()
    _force_published(db_session, Series, series["id"])

    draft_series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={"title": "Draft Series", "slug": "draft-series", "status": "draft", "is_featured": True},
    ).json()

    archived_series = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={"title": "Archived Series", "slug": "archived-series", "status": "draft"},
    ).json()
    _force_published(db_session, Series, archived_series["id"])
    client.delete(f"/api/admin/series/{archived_series['id']}", headers=admin_headers)

    pub_season = client.post(
        f"/api/admin/series/{series['id']}/seasons",
        headers=admin_headers,
        json={"season_number": 1, "title": "S1", "status": "draft"},
    ).json()
    _force_published(db_session, Season, pub_season["id"])
    draft_season = client.post(
        f"/api/admin/series/{series['id']}/seasons",
        headers=admin_headers,
        json={"season_number": 2, "title": "S2 Draft", "status": "draft"},
    ).json()

    pub_ep = client.post(
        f"/api/admin/seasons/{pub_season['id']}/episodes",
        headers=admin_headers,
        json={"episode_number": 1, "title": "E1", "status": "draft"},
    ).json()
    _force_published(db_session, Episode, pub_ep["id"])
    draft_ep = client.post(
        f"/api/admin/seasons/{pub_season['id']}/episodes",
        headers=admin_headers,
        json={"episode_number": 2, "title": "E2 Draft", "status": "draft"},
    ).json()
    client.post(
        f"/api/admin/seasons/{draft_season['id']}/episodes",
        headers=admin_headers,
        json={"episode_number": 1, "title": "Hidden season ep", "status": "draft"},
    )

    soft = Movie(
        title="Soft Deleted Movie",
        slug="soft-deleted-movie",
        status="published",
        is_featured=True,
        is_trending=True,
        deleted_at=utcnow(),
    )
    soft_series = Series(
        title="Soft Deleted Series",
        slug="soft-deleted-series",
        status="published",
        deleted_at=utcnow(),
    )
    db_session.add_all([soft, soft_series])
    db_session.commit()
    soft_id = soft.id
    soft_series_id = soft_series.id

    return {
        "genre": genre,
        "published": published,
        "draft": draft,
        "archived": archived,
        "series": series,
        "draft_series": draft_series,
        "archived_series": archived_series,
        "pub_season": pub_season,
        "draft_season": draft_season,
        "pub_ep": pub_ep,
        "draft_ep": draft_ep,
        "soft_id": soft_id,
        "soft_series_id": soft_series_id,
    }


def _items(payload: dict):
    return payload.get("data") or payload.get("items") or []


def test_public_movies_hide_unpublished(client, admin_headers, db_session):
    data = _seed_visibility_matrix(admin_headers, client, db_session)

    listed = _items(client.get("/api/movies").json())
    titles = {m["title"] for m in listed}
    assert "Visible Movie" in titles
    assert "Draft Movie" not in titles
    assert "Archived Movie" not in titles
    assert "Soft Deleted Movie" not in titles

    assert client.get(f"/api/movies/{data['draft']['id']}").status_code == 404
    assert client.get("/api/movies/draft-movie").status_code == 404
    assert client.get(f"/api/movies/{data['archived']['id']}").status_code == 404
    assert client.get("/api/movies/archived-movie").status_code == 404
    assert client.get(f"/api/movies/{data['soft_id']}").status_code == 404
    assert client.get(f"/api/movies/{data['published']['id']}").status_code == 200
    assert client.get("/api/movies/visible-movie").status_code == 200

    featured = _items(client.get("/api/movies", params={"featured": True}).json())
    assert all(m["status"] == "published" for m in featured)
    assert all(m["title"] != "Draft Movie" for m in featured)

    trending = _items(client.get("/api/movies", params={"trending": True}).json())
    assert all(m["status"] == "published" for m in trending)
    assert all(m["title"] != "Archived Movie" for m in trending)


def test_public_series_seasons_episodes_hide_unpublished(client, admin_headers, db_session):
    data = _seed_visibility_matrix(admin_headers, client, db_session)

    listed = _items(client.get("/api/series").json())
    titles = {s["title"] for s in listed}
    assert "Visible Series" in titles
    assert "Draft Series" not in titles
    assert "Archived Series" not in titles
    assert "Soft Deleted Series" not in titles

    assert client.get(f"/api/series/{data['draft_series']['id']}").status_code == 404
    assert client.get("/api/series/draft-series").status_code == 404
    assert client.get(f"/api/series/{data['soft_series_id']}").status_code == 404

    seasons = client.get(f"/api/series/{data['series']['id']}/seasons").json()
    season_titles = {s["title"] for s in seasons}
    assert "S1" in season_titles
    assert "S2 Draft" not in season_titles

    episodes = client.get(f"/api/series/{data['series']['id']}/episodes").json()
    ep_titles = {e["title"] for e in episodes}
    assert "E1" in ep_titles
    assert "E2 Draft" not in ep_titles
    assert "Hidden season ep" not in ep_titles

    pub_eps = client.get(f"/api/seasons/{data['pub_season']['id']}/episodes").json()
    assert {e["title"] for e in pub_eps} == {"E1"}
    assert client.get(f"/api/seasons/{data['draft_season']['id']}/episodes").status_code == 404


def test_public_search_hides_unpublished(client, admin_headers, db_session):
    _seed_visibility_matrix(admin_headers, client, db_session)
    result = client.get("/api/search", params={"q": "Movie"}).json()
    movie_titles = {m["title"] for m in result["movies"]}
    assert "Visible Movie" in movie_titles
    assert "Draft Movie" not in movie_titles
    assert "Archived Movie" not in movie_titles
    assert "Soft Deleted Movie" not in movie_titles

    series_result = client.get("/api/search", params={"q": "Series"}).json()
    series_titles = {s["title"] for s in series_result["series"]}
    assert "Visible Series" in series_titles
    assert "Draft Series" not in series_titles
    assert "Archived Series" not in series_titles
