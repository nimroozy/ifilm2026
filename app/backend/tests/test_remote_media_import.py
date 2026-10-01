"""Remote MP4 import: SSRF, streaming transfer, signed URL redaction."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.models.content import Movie
from app.models.media_processing import JOB_TYPE_REMOTE_MEDIA_IMPORT
from app.services.media_external import ExternalMediaError, assert_safe_external_url
from app.services.media_external_attach import mask_external_url
from app.services.media_remote_import import (
    execute_remote_media_import,
    queue_remote_media_import,
    validate_remote_import_url,
)
from cryptography.fernet import Fernet


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


@pytest.fixture
def import_settings(tmp_path, encryption_key, monkeypatch):
    media = tmp_path / "media"
    media.mkdir()
    monkeypatch.setenv("MEDIA_ROOT", str(media))
    monkeypatch.setenv("ENABLE_UPLOADS", "true")
    monkeypatch.setenv("ENABLE_REMOTE_MEDIA_IMPORT", "true")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


def _movie(db_session) -> Movie:
    from app.models.media_assets import new_uuid

    movie = Movie(
        title="Import Test",
        slug=f"import-test-{new_uuid()[:8]}",
        status="draft",
        description="d",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.example.com/a.mp4",
        "file:///tmp/a.mp4",
        "ftp://cdn.example.com/a.mp4",
        "data:video/mp4;base64,aaa",
        "https://user:pass@cdn.example.com/a.mp4",
        "https://localhost/a.mp4",
        "https://127.0.0.1/a.mp4",
        "https://10.0.0.5/a.mp4",
        "https://192.168.1.1/a.mp4",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/a.mp4",
        "https://[fe80::1]/a.mp4",
    ],
)
def test_assert_safe_external_url_rejects_unsafe(url):
    with pytest.raises(ExternalMediaError):
        assert_safe_external_url(url)


def test_mask_external_url_hides_query_tokens():
    masked = mask_external_url(
        "https://cdn.example.com/movies/title/movie.mp4?token=SUPERSECRET&expires=999"
    )
    assert masked is not None
    assert "SUPERSECRET" not in masked
    assert masked.endswith("?…")
    assert "cdn.example.com" in masked


def test_validate_rejects_hls(import_settings, monkeypatch):
    from datetime import UTC, datetime

    from app.services import media_external
    from fastapi import HTTPException

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda url, **kwargs: media_external.ExternalMediaValidation(
            url=url,
            kind="hls",
            content_type="application/vnd.apple.mpegurl",
            content_length=100,
            accept_ranges=False,
            validated_at=datetime.now(UTC),
        ),
    )
    with pytest.raises(HTTPException) as exc:
        validate_remote_import_url("https://cdn.example.com/master.m3u8", settings=import_settings)
    assert "HLS" in str(exc.value.detail) or "deferred" in str(exc.value.detail).lower()


def test_queue_and_execute_import_streams_without_buffering(
    db_session, import_settings, encryption_key, monkeypatch
):
    movie = _movie(db_session)
    payload = b"\x00\x00\x00\x18ftypmp42" + (b"0" * (256 * 1024))
    url = "https://cdn.example.com/movies/title/movie.mp4?token=SECRETTOKEN"

    class FakeValidation:
        url = "https://cdn.example.com/movies/title/movie.mp4?token=SECRETTOKEN"
        kind = "mp4"
        content_type = "video/mp4"
        content_length = len(payload)
        accept_ranges = True
        validated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda *a, **k: FakeValidation(),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.assert_safe_external_url",
        lambda u: (u, "cdn.example.com"),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.validate_content_compatibility",
        lambda **kwargs: None,
    )

    job, record, asset = queue_remote_media_import(
        db_session,
        settings=import_settings,
        url=url,
        owner_type="movie",
        owner_id=movie.id,
        destination="local_origin",
        admin_id=1,
    )
    assert job.job_type == JOB_TYPE_REMOTE_MEDIA_IMPORT
    assert record.source_url_display.endswith("?…") or "SECRETTOKEN" not in record.source_url_display
    assert b"SECRETTOKEN" not in record.source_url_ciphertext
    public = __import__(
        "app.services.media_remote_import", fromlist=["remote_import_public"]
    ).remote_import_public(record, job)
    assert "SECRETTOKEN" not in str(public)

    # Mock streaming GET
    class FakeStream:
        def __init__(self):
            self.status_code = 200
            self.headers = {"content-length": str(len(payload)), "content-type": "video/mp4"}

        @property
        def is_redirect(self):
            return False

        def iter_bytes(self, chunk_size=1024):
            for i in range(0, len(payload), chunk_size):
                yield payload[i : i + chunk_size]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, headers=None):
            assert "SECRETTOKEN" in url  # worker may use decrypted URL internally
            return FakeStream()

    monkeypatch.setattr("app.services.media_remote_import.httpx.Client", FakeClient)

    # Claim-like: set running
    job.status = "running"
    db_session.add(job)
    db_session.commit()

    execute_remote_media_import(db_session, settings=import_settings, job=job)
    db_session.refresh(job)
    db_session.refresh(record)
    db_session.refresh(asset)
    assert job.status == "completed"
    assert record.phase == "completed"
    assert asset.upload_status == "completed"
    assert asset.source_type == "uploaded"
    assert asset.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert Path(import_settings.media_root, asset.storage_path).is_file()


def test_api_validate_and_start_masks_secrets(
    client, admin_headers, db_session, import_settings, encryption_key, monkeypatch
):
    movie = _movie(db_session)

    class FakeValidation:
        url = "https://cdn.example.com/a.mp4?sig=SECRET"
        kind = "mp4"
        content_type = "video/mp4"
        content_length = 1000
        accept_ranges = False
        validated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda *a, **k: FakeValidation(),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.assert_safe_external_url",
        lambda u: (FakeValidation.url, "cdn.example.com"),
    )
    validated = client.post(
        "/api/admin/media/remote-import/validate",
        headers=admin_headers,
        json={"url": "https://cdn.example.com/a.mp4?sig=SECRET"},
    )
    assert validated.status_code == 200, validated.text
    body = validated.json()
    assert "SECRET" not in body["url_display"]
    started = client.post(
        "/api/admin/media/remote-import",
        headers=admin_headers,
        json={
            "url": "https://cdn.example.com/a.mp4?sig=SECRET",
            "owner_type": "movie",
            "owner_id": movie.id,
            "destination": "local_origin",
        },
    )
    assert started.status_code == 201, started.text
    out = started.json()
    assert "SECRET" not in str(out)
    assert out["phase"] == "queued"
    assert out["media_asset_id"]


def test_resume_uses_range_206_and_ignored_range_restarts(
    db_session, import_settings, encryption_key, monkeypatch
):
    movie = _movie(db_session)
    first = b"\x00\x00\x00\x18ftypmp42" + (b"A" * 1024)
    second = b"B" * 2048
    payload = first + second
    url = "https://cdn.example.com/movie.mp4?token=SECRET"

    class FakeValidation:
        url = "https://cdn.example.com/movie.mp4?token=SECRET"
        kind = "mp4"
        content_type = "video/mp4"
        content_length = len(payload)
        accept_ranges = True
        validated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda *a, **k: FakeValidation(),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.assert_safe_external_url",
        lambda u: (u, "cdn.example.com"),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.validate_content_compatibility",
        lambda **kwargs: None,
    )

    job, record, asset = queue_remote_media_import(
        db_session,
        settings=import_settings,
        url=url,
        owner_type="movie",
        owner_id=movie.id,
        destination="local_origin",
        admin_id=1,
    )

    from app.services.storage import media_root

    part = media_root() / "temp" / f"remote-import-{asset.id}.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(first)
    record.accept_ranges = True
    record.bytes_downloaded = len(first)
    db_session.add(record)
    job.status = "running"
    db_session.add(job)
    db_session.commit()

    seen = {"range": None, "status": 206}

    class FakeStream:
        def __init__(self):
            self.status_code = seen["status"]
            self.headers = {
                "content-length": str(len(second) if seen["status"] == 206 else len(payload)),
                "content-type": "video/mp4",
            }
            if seen["status"] == 206:
                self.headers["content-range"] = f"bytes {len(first)}-{len(payload) - 1}/{len(payload)}"

        @property
        def is_redirect(self):
            return False

        def iter_bytes(self, chunk_size=1024):
            body = second if self.status_code == 206 else payload
            for i in range(0, len(body), chunk_size):
                yield body[i : i + chunk_size]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, headers=None):
            seen["range"] = (headers or {}).get("Range")
            return FakeStream()

    monkeypatch.setattr("app.services.media_remote_import.httpx.Client", FakeClient)
    execute_remote_media_import(db_session, settings=import_settings, job=job)
    db_session.refresh(job)
    db_session.refresh(asset)
    assert seen["range"] == f"bytes={len(first)}-"
    assert job.status == "completed"
    assert asset.checksum_sha256 == hashlib.sha256(payload).hexdigest()

    # Ignored Range (200) must restart cleanly — use distinct payload for unique checksum.
    first_b = b"\x00\x00\x00\x18ftypmp42" + (b"C" * 512)
    second_b = b"D" * 1536
    payload_b = first_b + second_b

    class FakeValidationB:
        url = "https://cdn.example.com/movie2.mp4?token=SECRET"
        kind = "mp4"
        content_type = "video/mp4"
        content_length = len(payload_b)
        accept_ranges = True
        validated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda *a, **k: FakeValidationB(),
    )

    job2, record2, asset2 = queue_remote_media_import(
        db_session,
        settings=import_settings,
        url="https://cdn.example.com/movie2.mp4?token=SECRET",
        owner_type="movie",
        owner_id=movie.id,
        destination="local_origin",
        admin_id=1,
    )
    part2 = media_root() / "temp" / f"remote-import-{asset2.id}.part"
    part2.parent.mkdir(parents=True, exist_ok=True)
    part2.write_bytes(first_b)
    record2.accept_ranges = True
    db_session.add(record2)
    job2.status = "running"
    db_session.add(job2)
    db_session.commit()
    seen["status"] = 200
    seen["payload"] = payload_b
    seen["second"] = second_b
    seen["range"] = None

    class FakeStream200:
        def __init__(self):
            self.status_code = 200
            self.headers = {
                "content-length": str(len(payload_b)),
                "content-type": "video/mp4",
            }

        @property
        def is_redirect(self):
            return False

        def iter_bytes(self, chunk_size=1024):
            for i in range(0, len(payload_b), chunk_size):
                yield payload_b[i : i + chunk_size]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeClient200(FakeClient):
        def stream(self, method, url, headers=None):
            seen["range"] = (headers or {}).get("Range")
            return FakeStream200()

    monkeypatch.setattr("app.services.media_remote_import.httpx.Client", FakeClient200)
    execute_remote_media_import(db_session, settings=import_settings, job=job2)
    db_session.refresh(job2)
    db_session.refresh(asset2)
    assert job2.status == "completed"
    assert asset2.checksum_sha256 == hashlib.sha256(payload_b).hexdigest()


def test_disk_capacity_refusal(import_settings, monkeypatch):
    from fastapi import HTTPException

    class FakeValidation:
        url = "https://cdn.example.com/huge.mp4"
        kind = "mp4"
        content_type = "video/mp4"
        content_length = 10 * 1024 * 1024 * 1024
        accept_ranges = False
        validated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda *a, **k: FakeValidation(),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.assert_safe_external_url",
        lambda u: (u, "cdn.example.com"),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import._disk_free_bytes",
        lambda path: 100,
    )
    with pytest.raises(HTTPException) as exc:
        validate_remote_import_url("https://cdn.example.com/huge.mp4", settings=import_settings)
    assert "storage" in str(exc.value.detail).lower()


def test_episode_remote_import_queues(client, admin_headers, db_session, import_settings, encryption_key, monkeypatch):
    from app.models.content import Episode, Season, Series
    from app.models.media_assets import new_uuid

    series = Series(title="Imp Series", slug=f"imp-series-{new_uuid()[:6]}", status="draft")
    db_session.add(series)
    db_session.flush()
    season = Season(series_id=series.id, season_number=1, title="S1", status="draft")
    db_session.add(season)
    db_session.flush()
    episode = Episode(
        season_id=season.id,
        series_id=series.id,
        episode_number=1,
        title="E1",
        status="draft",
    )
    db_session.add(episode)
    db_session.commit()
    db_session.refresh(episode)

    class FakeValidation:
        url = "https://cdn.example.com/ep.mp4"
        kind = "mp4"
        content_type = "video/mp4"
        content_length = 1000
        accept_ranges = False
        validated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda *a, **k: FakeValidation(),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.assert_safe_external_url",
        lambda u: (FakeValidation.url, "cdn.example.com"),
    )
    started = client.post(
        "/api/admin/media/remote-import",
        headers=admin_headers,
        json={
            "url": "https://cdn.example.com/ep.mp4",
            "owner_type": "episode",
            "owner_id": episode.id,
            "destination": "local_origin",
        },
    )
    assert started.status_code == 201, started.text
    assert started.json()["owner_type"] == "episode"
    assert started.json()["owner_id"] == episode.id


def test_max_bytes_enforced_during_transfer(
    db_session, import_settings, encryption_key, monkeypatch
):
    movie = _movie(db_session)
    monkeypatch.setenv("REMOTE_IMPORT_MAX_BYTES", "1024")
    get_settings.cache_clear()
    settings = get_settings()
    payload = b"\x00\x00\x00\x18ftypmp42" + (b"Z" * 4096)
    url = "https://cdn.example.com/big.mp4"

    class FakeValidation:
        url = "https://cdn.example.com/big.mp4"
        kind = "mp4"
        content_type = "video/mp4"
        content_length = None  # unknown length — enforce during transfer
        accept_ranges = False
        validated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    monkeypatch.setattr(
        "app.services.media_remote_import.validate_external_media_url",
        lambda *a, **k: FakeValidation(),
    )
    monkeypatch.setattr(
        "app.services.media_remote_import.assert_safe_external_url",
        lambda u: (u, "cdn.example.com"),
    )

    job, record, asset = queue_remote_media_import(
        db_session,
        settings=settings,
        url=url,
        owner_type="movie",
        owner_id=movie.id,
        destination="local_origin",
        admin_id=1,
    )
    job.status = "running"
    db_session.add(job)
    db_session.commit()

    class FakeStream:
        status_code = 200
        headers = {"content-type": "video/mp4"}

        @property
        def is_redirect(self):
            return False

        def iter_bytes(self, chunk_size=1024):
            for i in range(0, len(payload), chunk_size):
                yield payload[i : i + chunk_size]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, headers=None):
            return FakeStream()

    monkeypatch.setattr("app.services.media_remote_import.httpx.Client", FakeClient)
    execute_remote_media_import(db_session, settings=settings, job=job)
    db_session.refresh(job)
    db_session.refresh(record)
    assert job.status == "failed"
    assert job.error_code == "too_large"
    from app.services.storage import media_root

    part = media_root() / "temp" / f"remote-import-{asset.id}.part"
    assert not part.exists()
