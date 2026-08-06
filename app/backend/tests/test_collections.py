"""Collections V1 API and service tests."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.models.collections import Collection
from app.models.content import Movie, Series
from app.services.collections import seed_demo_collections
from sqlalchemy import event


def _force_published(db_session, model, entity_id: int) -> None:
    row = db_session.get(model, entity_id)
    assert row is not None
    row.status = "published"
    row.deleted_at = None
    if hasattr(row, "published_at"):
        row.published_at = datetime.now(UTC)
    if not getattr(row, "description", None):
        row.description = "Synopsis for public visibility"
    db_session.add(row)
    db_session.commit()


def _create_published_movie(client, admin_headers, db_session, title: str, **extra) -> dict:
    payload = {
        "title": title,
        "description": f"{title} description for readiness",
        "poster_url": "https://placehold.co/300x450",
        "status": "draft",
        **extra,
    }
    created = client.post("/api/admin/movies", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    movie = created.json()
    _force_published(db_session, Movie, movie["id"])
    return client.get(f"/api/admin/movies/{movie['id']}", headers=admin_headers).json()


def _create_published_series(client, admin_headers, db_session, title: str) -> dict:
    created = client.post(
        "/api/admin/series",
        headers=admin_headers,
        json={
            "title": title,
            "description": f"{title} description for readiness",
            "poster_url": "https://placehold.co/300x450",
            "status": "draft",
        },
    )
    assert created.status_code == 201, created.text
    series = created.json()
    _force_published(db_session, Series, series["id"])
    return client.get(f"/api/admin/series/{series['id']}", headers=admin_headers).json()


def test_collection_crud_publish_archive(client, admin_headers, db_session):
    created = client.post(
        "/api/admin/collections",
        headers=admin_headers,
        json={
            "title": "Action Classics",
            "slug": "action-classics",
            "description": "Editorial action picks",
            "collection_type": "editorial",
            "is_featured": True,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "draft"
    assert body["slug"] == "action-classics"
    cid = body["id"]

    # Slug conflict
    conflict = client.post(
        "/api/admin/collections",
        headers=admin_headers,
        json={"title": "Other", "slug": "action-classics"},
    )
    assert conflict.status_code == 409

    movie = _create_published_movie(client, admin_headers, db_session, "Collection Movie One")
    draft = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={"title": "Hidden Draft Movie", "status": "draft"},
    ).json()

    add = client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": movie["id"]},
    )
    assert add.status_code == 201, add.text

    dup = client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": movie["id"]},
    )
    assert dup.status_code == 409

    both = client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": movie["id"], "series_id": 1},
    )
    assert both.status_code == 422

    missing = client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": 999999},
    )
    assert missing.status_code == 422

    client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": draft["id"]},
    )

    # Draft collection hidden publicly
    public_list = client.get("/api/catalog/collections")
    assert public_list.status_code == 200
    assert all(c["slug"] != "action-classics" for c in public_list.json()["data"])

    published = client.post(f"/api/admin/collections/{cid}/publish", headers=admin_headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    public = client.get("/api/catalog/collections/action-classics")
    assert public.status_code == 200
    payload = public.json()
    assert payload["slug"] == "action-classics"
    assert payload["item_count"] == 1
    assert all(i["movie_id"] != draft["id"] for i in payload["items"])
    assert "created_by_admin_id" not in payload
    assert "demo_owned" not in payload
    for item in payload["items"]:
        movie_payload = item.get("movie") or {}
        assert "external_url" not in movie_payload
        assert "storage_path" not in str(movie_payload)

    preview = client.get(f"/api/admin/collections/{cid}/preview", headers=admin_headers)
    assert preview.status_code == 200
    assert preview.json()["item_count"] == 1

    archived = client.post(f"/api/admin/collections/{cid}/archive", headers=admin_headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.get("/api/catalog/collections/action-classics").status_code == 404


def test_collection_reorder_and_empty_hidden(client, admin_headers, db_session):
    m1 = _create_published_movie(client, admin_headers, db_session, "Reorder A")
    m2 = _create_published_movie(client, admin_headers, db_session, "Reorder B")
    created = client.post(
        "/api/admin/collections",
        headers=admin_headers,
        json={"title": "Reorder Shelf", "slug": "reorder-shelf"},
    ).json()
    cid = created["id"]
    i1 = client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": m1["id"]},
    ).json()
    i2 = client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": m2["id"]},
    ).json()

    reordered = client.put(
        f"/api/admin/collections/{cid}/items/reorder",
        headers=admin_headers,
        json={"item_ids": [i2["id"], i1["id"]]},
    )
    assert reordered.status_code == 200, reordered.text
    ids = [item["id"] for item in reordered.json()["items"]]
    assert ids == [i2["id"], i1["id"]]

    client.post(f"/api/admin/collections/{cid}/publish", headers=admin_headers)
    # Hide all items publicly by reverting movies to draft
    for mid in (m1["id"], m2["id"]):
        db_session.query(Movie).filter(Movie.id == mid).update({"status": "draft"})
    db_session.commit()

    assert client.get("/api/catalog/collections/reorder-shelf").status_code == 404
    listing = client.get("/api/catalog/collections").json()["data"]
    assert all(c["slug"] != "reorder-shelf" for c in listing)


def test_collection_rbac_and_delete_preserves_catalog(client, admin_headers, db_session):
    # No auth
    assert client.get("/api/admin/collections").status_code == 401

    movie = _create_published_movie(client, admin_headers, db_session, "Keep Movie")
    created = client.post(
        "/api/admin/collections",
        headers=admin_headers,
        json={"title": "Temp", "slug": "temp-collection"},
    ).json()
    cid = created["id"]
    client.post(
        f"/api/admin/collections/{cid}/items",
        headers=admin_headers,
        json={"movie_id": movie["id"]},
    )
    deleted = client.delete(f"/api/admin/collections/{cid}", headers=admin_headers)
    assert deleted.status_code == 200
    assert db_session.get(Movie, movie["id"]) is not None
    assert client.get(f"/api/admin/collections/{cid}", headers=admin_headers).status_code == 404


def test_collection_seed_idempotent_preserves_manual(client, admin_headers, db_session):
    # Ensure enough published movies exist for Popular Movies seed
    for i in range(4):
        _create_published_movie(
            client, admin_headers, db_session, f"Seed Movie {i}", is_trending=True
        )

    first = seed_demo_collections(db_session)
    second = seed_demo_collections(db_session)
    assert first["seed_version"] == second["seed_version"]

    demo = (
        db_session.query(Collection)
        .filter(Collection.demo_owned.is_(True), Collection.slug == "popular-movies")
        .first()
    )
    assert demo is not None

    # Manual collection with unique slug must survive reseed
    manual = Collection(
        title="Manual Editorial",
        slug="manual-editorial",
        description="Human curated",
        collection_type="staff_pick",
        status="published",
        visibility="public",
        demo_owned=False,
    )
    db_session.add(manual)
    db_session.commit()
    manual_id = manual.id

    seed_demo_collections(db_session)
    assert db_session.get(Collection, manual_id) is not None
    assert db_session.get(Collection, manual_id).demo_owned is False


def test_collection_series_item_and_audit(client, admin_headers, db_session, caplog):
    series = _create_published_series(client, admin_headers, db_session, "Collection Series")

    with caplog.at_level(logging.INFO, logger="app.catalog.audit"):
        created = client.post(
            "/api/admin/collections",
            headers=admin_headers,
            json={"title": "Series Shelf", "slug": "series-shelf", "collection_type": "regional"},
        )
        assert created.status_code == 201
        cid = created.json()["id"]
        added = client.post(
            f"/api/admin/collections/{cid}/items",
            headers=admin_headers,
            json={"series_id": series["id"]},
        )
        assert added.status_code == 201
        assert added.json()["content_type"] == "series"
        client.post(f"/api/admin/collections/{cid}/publish", headers=admin_headers)

    messages = " ".join(r.message for r in caplog.records)
    assert "collection_created" in messages
    assert "collection_item_added" in messages
    assert "collection_published" in messages

    detail = client.get("/api/catalog/collections/series-shelf").json()
    assert detail["items"][0]["series"]["id"] == series["id"]


def test_collection_query_counts_bounded(client, admin_headers, db_session):
    movies = [
        _create_published_movie(
            client, admin_headers, db_session, f"QC Movie {i}", is_featured=True
        )
        for i in range(5)
    ]
    created = client.post(
        "/api/admin/collections",
        headers=admin_headers,
        json={
            "title": "Query Count Shelf",
            "slug": "query-count-shelf",
            "is_featured": True,
        },
    ).json()
    cid = created["id"]
    for movie in movies:
        client.post(
            f"/api/admin/collections/{cid}/items",
            headers=admin_headers,
            json={"movie_id": movie["id"]},
        )
    client.post(f"/api/admin/collections/{cid}/publish", headers=admin_headers)

    from app.db import session as session_module

    engine = session_module.engine
    statements: list[str] = []

    def before_cursor(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor)
    try:
        statements.clear()
        index = client.get("/api/catalog/collections")
        assert index.status_code == 200
        index_queries = len(statements)
        # Index should not load every item row payload path explosively.
        assert index_queries < 40, index_queries

        statements.clear()
        detail = client.get("/api/catalog/collections/query-count-shelf")
        assert detail.status_code == 200
        detail_queries = len(statements)
        assert detail_queries < 80, detail_queries

        statements.clear()
        home = client.get("/api/catalog/collections/featured/home")
        assert home.status_code == 200
        home_queries = len(statements)
        assert home_queries < 100, home_queries
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor)


def test_unknown_collection_404(client):
    assert client.get("/api/catalog/collections/does-not-exist").status_code == 404
