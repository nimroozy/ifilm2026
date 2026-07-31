"""Customer / dual-principal playback session create (Phase 8)."""

from __future__ import annotations

import pytest
from app.models.content import Episode, Movie, Season, Series
from app.models.media_assets import new_uuid, utcnow
from app.schemas.streaming import CustomerPlaybackSessionCreate
from pydantic import ValidationError
from tests.conftest import TEST_FIXTURE_PASSWORD, TEST_FIXTURE_USER
from tests.test_streaming_service import _admin_token, _headers, _seed_active_package


def _login_subscriber(client) -> str:
    login = client.post(
        "/api/auth/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_customer_playback_session_by_movie(client, db_session):
    movie = Movie(
        title="Playable Movie",
        slug=f"playable-{new_uuid()[:8]}",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    asset, package = _seed_active_package(db_session, movie=movie)
    assert package.is_active

    token = _login_subscriber(client)
    created = client.post(
        "/api/playback/sessions",
        headers=_headers(token),
        json={"content_type": "movie", "content_id": movie.id},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["media_asset_id"] == asset.id
    assert "/api/stream/" in body["master_playlist_url"]
    assert "token_hash" not in body
    assert "storage_path" not in body

    master = client.get(body["master_playlist_url"])
    assert master.status_code == 200
    assert f"/api/stream/{body['playback_token']}/" in master.text


def test_customer_playback_session_by_episode(client, db_session):
    series = Series(
        title="Playable Series",
        slug=f"series-play-{new_uuid()[:8]}",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(series)
    db_session.flush()
    season = Season(
        series_id=series.id,
        season_number=1,
        title="S1",
        status="published",
    )
    db_session.add(season)
    db_session.flush()
    episode = Episode(
        series_id=series.id,
        season_id=season.id,
        episode_number=1,
        title="E1",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(episode)
    db_session.commit()
    db_session.refresh(episode)

    asset = _seed_active_package(db_session)[0]
    asset.movie_id = None
    asset.episode_id = episode.id
    db_session.add(asset)
    db_session.commit()

    token = _login_subscriber(client)
    created = client.post(
        "/api/playback/sessions",
        headers=_headers(token),
        json={"content_type": "episode", "content_id": episode.id},
    )
    assert created.status_code == 201, created.text
    assert created.json()["media_asset_id"] == asset.id


def test_customer_session_requires_auth(client, db_session):
    movie = Movie(
        title="X",
        slug=f"x-play-{new_uuid()[:8]}",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    _seed_active_package(db_session, movie=movie)
    resp = client.post(
        "/api/playback/sessions",
        json={"content_type": "movie", "content_id": movie.id},
    )
    assert resp.status_code == 401


def test_customer_session_no_package_conflict(client, db_session):
    movie = Movie(
        title="No Package",
        slug=f"no-pkg-{new_uuid()[:8]}",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    token = _login_subscriber(client)
    resp = client.post(
        "/api/playback/sessions",
        headers=_headers(token),
        json={"content_type": "movie", "content_id": movie.id},
    )
    assert resp.status_code == 409


def test_admin_can_use_customer_session_endpoint(client, db_session):
    movie = Movie(
        title="Admin Play",
        slug=f"admin-play-{new_uuid()[:8]}",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    asset, _ = _seed_active_package(db_session, movie=movie)
    token = _admin_token(db_session)
    created = client.post(
        "/api/playback/sessions",
        headers=_headers(token),
        json={"media_asset_id": asset.id},
    )
    assert created.status_code == 201


def test_owner_can_revoke_own_session(client, db_session):
    movie = Movie(
        title="Revoke Me",
        slug=f"revoke-{new_uuid()[:8]}",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    _seed_active_package(db_session, movie=movie)
    token = _login_subscriber(client)
    created = client.post(
        "/api/playback/sessions",
        headers=_headers(token),
        json={"content_type": "movie", "content_id": movie.id},
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    revoked = client.post(
        f"/api/playback/sessions/{sid}/revoke",
        headers=_headers(token),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_customer_session_create_xor_validation():
    with pytest.raises(ValidationError):
        CustomerPlaybackSessionCreate()
    with pytest.raises(ValidationError):
        CustomerPlaybackSessionCreate(
            media_asset_id="a",
            content_type="movie",
            content_id=1,
        )
    ok = CustomerPlaybackSessionCreate(media_asset_id="asset-1")
    assert ok.media_asset_id == "asset-1"
