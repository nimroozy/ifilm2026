"""API-level availability filters and response shape."""

from __future__ import annotations

from tests.test_catalog import _seed_pkg


def test_movie_availability_fields_and_has_dubbed_filter(client, admin_headers, db_session):
    # English original + Persian dub
    created = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={
            "title": "Availability Dub Fixture",
            "language": "English",
            "description": "Synopsis for publish readiness",
            "poster_url": "https://placehold.co/300x450",
            "backdrop_url": "https://placehold.co/1920x800",
            "release_year": 2024,
            "audio": ["English", "Persian"],
            "dubbed": ["Persian"],
            "subtitles": ["English"],
            "genre_ids": [],
        },
    )
    assert created.status_code == 201, created.text
    movie = created.json()
    assert movie["audio"] == ["en", "fa"]
    assert movie["dubbed"] == ["fa"]
    assert movie["subtitles"] == ["en"]
    audio = movie["audio_availability"]
    assert audio["original_language"] == "en"
    assert audio["languages"] == ["en", "fa"]
    assert audio["dubbed_languages"] == ["fa"]
    assert audio["source"] == "admin_metadata"
    assert audio["selectable_in_player"] is False
    assert movie["subtitle_availability"]["languages"] == ["en"]

    # Persian original only — not dubbed even if dubbed duplicates original
    created2 = client.post(
        "/api/admin/movies",
        headers=admin_headers,
        json={
            "title": "Availability Original Only",
            "language": "Persian",
            "description": "Synopsis for publish readiness",
            "poster_url": "https://placehold.co/300x450",
            "backdrop_url": "https://placehold.co/1920x800",
            "release_year": 2024,
            "audio": ["Persian"],
            "dubbed": ["Persian"],
            "genre_ids": [],
        },
    )
    assert created2.status_code == 201
    body2 = created2.json()
    assert body2["audio_availability"]["dubbed_languages"] == []

    genre = client.post(
        "/api/admin/genres",
        headers=admin_headers,
        json={"name": "AvailGenre", "slug": "avail-genre"},
    ).json()

    for mid in (movie["id"], body2["id"]):
        client.patch(
            f"/api/admin/movies/{mid}",
            headers=admin_headers,
            json={"genre_ids": [genre["id"]]},
        )
        _seed_pkg(db_session, movie_id=mid)
        assert (
            client.post(
                f"/api/admin/catalog/movie/{mid}/submit-review",
                headers=admin_headers,
                json={},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/admin/catalog/movie/{mid}/approve",
                headers=admin_headers,
                json={},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/admin/catalog/movie/{mid}/publish",
                headers=admin_headers,
                json={},
            ).status_code
            == 200
        )

    dubbed_list = client.get("/api/movies", params={"has_dubbed": True, "page_size": 100})
    assert dubbed_list.status_code == 200
    titles = {m["title"] for m in dubbed_list.json()["data"]}
    assert "Availability Dub Fixture" in titles
    assert "Availability Original Only" not in titles

    subtitled = client.get("/api/movies", params={"has_subtitles": True, "page_size": 100})
    assert subtitled.status_code == 200
    sub_titles = {m["title"] for m in subtitled.json()["data"]}
    assert "Availability Dub Fixture" in sub_titles

    detail = client.get(f"/api/movies/{movie['id']}")
    assert detail.status_code == 200
    blob = detail.text
    assert "/data/" not in blob
    assert "relative_path" not in blob
    assert "storage_path" not in blob
