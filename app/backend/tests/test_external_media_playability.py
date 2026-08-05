"""External media URL validation + playability derived from packages/external."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.content import Movie
from app.models.media_assets import MediaAsset
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.services.catalog import movie_out
from app.services.media_external import ExternalMediaError, assert_safe_external_url, validate_external_media_url
from app.services.publishing.readiness import evaluate_playable_package
from app.services.storage import media_root


def test_reject_non_https_and_ssrf_hosts() -> None:
    with pytest.raises(ExternalMediaError) as http_exc:
        assert_safe_external_url("http://cdn.example.com/a.mp4")
    assert http_exc.value.code == "scheme_rejected"
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("file:///etc/passwd")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("ftp://cdn.example.com/a.mp4")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("data:text/plain,hi")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("javascript:alert(1)")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://localhost/a.mp4")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://127.0.0.1/a.mp4")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://169.254.169.254/latest/meta-data")
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url("https://10.0.0.5/a.mp4")
    with pytest.raises(ExternalMediaError) as cgnat:
        assert_safe_external_url("https://100.64.0.1/a.mp4")
    assert cgnat.value.code == "private_ip"


def test_reject_credentials_in_url() -> None:
    with pytest.raises(ExternalMediaError) as exc:
        assert_safe_external_url("https://user:secret@cdn.example.com/a.mp4")
    assert exc.value.code == "credentials_rejected"


def test_validate_external_media_url_head_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 200
        is_redirect = False
        headers = {
            "content-type": "video/mp4",
            "content-length": "12345",
            "accept-ranges": "bytes",
        }
        content = b""

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


def test_validate_external_media_head_fallback_and_hls(monkeypatch: pytest.MonkeyPatch) -> None:
    class _HeadReject:
        status_code = 405
        is_redirect = False
        headers = {}
        content = b""

    class _GetOk:
        status_code = 200
        is_redirect = False
        headers = {
            "content-type": "application/vnd.apple.mpegurl",
            "content-length": "80",
            "accept-ranges": "bytes",
        }
        content = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nhttps://cdn.example.com/720p.m3u8\n"

    class _Client:
        def __init__(self, *a, **k):
            self.gets = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def head(self, url):
            return _HeadReject()

        def get(self, url, headers=None):
            self.gets += 1
            return _GetOk()

    monkeypatch.setattr("app.services.media_external.httpx.Client", _Client)
    monkeypatch.setattr(
        "app.services.media_external.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    result = validate_external_media_url("https://cdn.example.com/master.m3u8")
    assert result.kind == "hls"


def test_validate_rejects_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 302
        is_redirect = True
        headers = {"location": "https://evil.example/a.mp4"}
        content = b""

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
    with pytest.raises(ExternalMediaError) as exc:
        validate_external_media_url("https://example.com/film.mp4")
    assert exc.value.code == "redirect_rejected"


def test_validate_rejects_playlist_private_host(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 200
        is_redirect = False
        headers = {
            "content-type": "application/vnd.apple.mpegurl",
            "content-length": "40",
        }
        content = b"#EXTM3U\nhttps://10.0.0.8/seg.ts\n"

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
    with pytest.raises(ExternalMediaError) as exc:
        validate_external_media_url("https://cdn.example.com/master.m3u8")
    assert exc.value.code == "private_ip"


def test_validate_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def head(self, url):
            raise httpx.ReadTimeout("slow")

        def get(self, *a, **k):
            raise httpx.ReadTimeout("slow")

    monkeypatch.setattr("app.services.media_external.httpx.Client", _Client)
    monkeypatch.setattr(
        "app.services.media_external.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    with pytest.raises(ExternalMediaError) as exc:
        validate_external_media_url("https://example.com/film.mp4")
    assert exc.value.code == "timeout"


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


def test_legacy_hls_path_alone_not_playable(db_session: Session) -> None:
    movie = Movie(
        title="Legacy Path Only",
        slug="legacy-path-only",
        status="published",
        description="has legacy path only",
        hls_path="/hls/legacy/master.m3u8",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    out = movie_out(movie, db_session)
    assert out.playable is False
    assert out.has_playable_package is False
    assert out.hls_path == "/hls/legacy/master.m3u8"


def test_killer_man_package_playability_regression(db_session: Session) -> None:
    """Published movie + active completed HLS package → playable without hls_path."""
    movie = Movie(
        title="The Killer Man",
        slug="the-killer-man",
        status="published",
        description="regression fixture",
        hls_path=None,
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)

    asset = MediaAsset(
        movie_id=movie.id,
        original_filename="killer.mp4",
        stored_filename="killer.mp4",
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=10,
        storage_backend="local",
        storage_path="originals/killer.mp4",
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
        master_playlist_path="packages/killer/master.m3u8",
    )
    db_session.add(package)
    db_session.commit()
    master = media_root() / "packages/killer/master.m3u8"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_text("#EXTM3U\n", encoding="utf-8")
    db_session.add(
        MediaRendition(
            package_id=package.id,
            label="720p",
            height=720,
            status="completed",
            playlist_path="packages/killer/720p.m3u8",
        )
    )
    db_session.commit()

    out = movie_out(movie, db_session)
    assert out.playable is True
    assert out.has_playable_package is True
    assert out.has_external_media is False


def test_movie_out_unplayable_without_media(db_session: Session) -> None:
    movie = Movie(title="Empty", slug="empty-movie", status="draft")
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    out = movie_out(movie, db_session)
    assert out.playable is False
    assert out.has_playable_package is False
    assert out.has_external_media is False


def test_external_not_validated_not_playable(db_session: Session) -> None:
    movie = Movie(title="Bad Ext", slug="bad-ext", status="draft")
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    db_session.add(
        MediaAsset(
            movie_id=movie.id,
            original_filename="x.mp4",
            stored_filename="",
            mime_type="video/mp4",
            extension="mp4",
            size_bytes=0,
            storage_backend="external",
            category="originals",
            upload_status="completed",
            processing_status="ready",
            source_type="external",
            external_url="https://cdn.example.com/x.mp4",
            external_kind="mp4",
            external_validated_at=None,
        )
    )
    db_session.commit()
    playable, _, status, issues = evaluate_playable_package(db_session, movie_id=movie.id)
    assert playable is False
    assert status == "external"
    assert any(i.code == "external_not_validated" for i in issues)
