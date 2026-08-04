"""External media URL validation + playability derived from packages/external."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest import mock

import pytest
from sqlalchemy.orm import Session

from app.models.content import Movie
from app.models.media_assets import MediaAsset
from app.services.catalog import movie_out
from app.services.media_external import ExternalMediaError, assert_safe_external_url, validate_external_media_url
from app.services.publishing.readiness import evaluate_playable_package


def test_reject_non_https_and_ssrf_hosts() -> None:
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("http://cdn.example.com/a.mp4")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("file:///etc/passwd")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("ftp://cdn.example.com/a.mp4")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://localhost/a.mp4")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://127.0.0.1/a.mp4")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://169.254.169.254/latest/meta-data")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://10.0.0.5/a.mp4")


def test_validate_external_media_url_head_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 200
        is_redirect = False
        headers = {
            "content-type": "video/mp4",
            "content-length": "12345",
            "accept-ranges": "bytes",
        }

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def head(self, url):
            return _Resp()

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("app.services.media_external.httpx.Client", _Client)
    monkeypatch.setattr(
        "app.services.media_external.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    result = validate_external_media_url("https://example.com/film.mp4")
    assert result.kind == "mp4"
    assert result.content_length == 12345
    assert result.accept_ranges is True


def test_movie_out_marks_playable_from_external(db_session: Session) -> None:
    movie = Movie(
        title="External Playable",
        slug="external-playable",
        status="draft",
        description="d",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    asset = MediaAsset(
        movie_id=movie.id,
        original_filename="film.mp4",
        stored_filename="",
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=10,
        storage_backend="external",
        category="originals",
        upload_status="completed",
        processing_status="ready",
        source_type="external",
        external_url="https://cdn.example.com/film.mp4",
        external_kind="mp4",
        external_validated_at=datetime.now(UTC),
    )
    db_session.add(asset)
    db_session.commit()

    playable, package_id, status, issues = evaluate_playable_package(db_session, movie_id=movie.id)
    assert playable is True
    assert status == "external"
    assert package_id is None
    assert issues == []

    out = movie_out(movie, db_session)
    assert out.playable is True
    assert out.has_external_media is True
    assert out.has_playable_package is False


def test_movie_out_unplayable_without_media(db_session: Session) -> None:
    movie = Movie(title="Empty", slug="empty-movie", status="draft")
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    out = movie_out(movie, db_session)
    assert out.playable is False
    assert out.has_playable_package is False
    assert out.has_external_media is False
