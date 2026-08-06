from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from app.core.config import Settings
from app.models.content import Episode, Movie, Series
from app.services.catalog import movie_out
from app.services.demo.artwork import write_rgb_png
from app.services.demo.cleanup import build_cleanup_plan
from app.services.tmdb.artwork import ArtworkError, store_artwork_bytes, validate_artwork_url
from app.services.tmdb.client import TMDBClient, TMDBClientError
from app.services.tmdb.curated import REAL_DEMO_SEED_VERSION
from app.services.tmdb.import_service import import_movie, import_series, refresh_demo_metadata
from app.services.tmdb.trailers import select_trailer
from tests.conftest import TEST_JWT


def _settings(tmp_path: Path | None = None, **kwargs) -> Settings:
    base = {
        "app_env": "test",
        "jwt_secret": TEST_JWT,
        "database_url": "sqlite://",
        "playback_token_secret": "playback-token-secret-for-unit-tests-32",
        "tmdb_enabled": True,
        "tmdb_api_read_token": "unit-test-tmdb-token",
        "tmdb_language": "en-US",
        "tmdb_fallback_language": "en-US",
        "artwork_root": str((tmp_path or Path("/tmp")) / "tmdb-artwork"),
        "_env_file": None,
    }
    base.update(kwargs)
    return Settings(**base)


def _movie_details(**overrides):
    data = {
        "id": 100,
        "title": "Demo Movie",
        "original_title": "Demo Movie",
        "overview": "A local imported movie.",
        "release_date": "2024-01-02",
        "runtime": 101,
        "original_language": "en",
        "spoken_languages": [{"iso_639_1": "en", "english_name": "English"}],
        "production_countries": [{"iso_3166_1": "US"}],
        "external_ids": {"imdb_id": "tt100"},
        "vote_average": 7.5,
        "genres": [{"name": "Drama"}],
        "images": {"logos": []},
        "poster_path": None,
        "backdrop_path": None,
        "translations": {"translations": []},
    }
    data.update(overrides)
    return data


def _series_details(**overrides):
    data = {
        "id": 200,
        "name": "Demo Series",
        "original_name": "Demo Series",
        "overview": "A local imported series.",
        "first_air_date": "2023-01-01",
        "last_air_date": "2024-01-01",
        "status": "Returning Series",
        "original_language": "en",
        "spoken_languages": [{"iso_639_1": "en", "english_name": "English"}],
        "origin_country": ["US"],
        "external_ids": {"imdb_id": "tt200"},
        "vote_average": 8.0,
        "genres": [{"name": "Science Fiction"}],
        "images": {"logos": []},
        "poster_path": None,
        "backdrop_path": None,
        "seasons": [{"season_number": 1}],
        "translations": {"translations": []},
    }
    data.update(overrides)
    return data


class FakeTMDB:
    def __init__(self):
        self.movie_detail_calls: list[str] = []
        self.tv_detail_calls = 0

    def search_movie(self, query, *, page=1, language=None):
        return {"results": [{"id": 100, "title": query}], "page": page}

    def search_tv(self, query, *, page=1, language=None):
        return {"results": [{"id": 200, "name": query}], "page": page}

    def movie_details(self, tmdb_id, *, language=None):
        self.movie_detail_calls.append(language or "en-US")
        return _movie_details(id=tmdb_id)

    def tv_details(self, tmdb_id, *, language=None):
        self.tv_detail_calls += 1
        return _series_details(id=tmdb_id)

    def season_details(self, tmdb_id, season_number, *, language=None):
        return {
            "id": 1,
            "name": "Season 1",
            "overview": "Season overview",
            "air_date": "2023-01-01",
            "episodes": [
                {
                    "id": 9001,
                    "episode_number": 1,
                    "name": "Pilot",
                    "overview": "Episode overview",
                    "runtime": 42,
                    "air_date": "2023-01-02",
                    "still_path": None,
                }
            ],
        }

    def configuration(self):
        return {"images": {"secure_base_url": "https://image.tmdb.org/t/p/"}}

    def movie_videos(self, tmdb_id, *, language=None):
        return {
            "results": [
                {
                    "site": "YouTube",
                    "type": "Trailer",
                    "key": "abc123",
                    "name": "Official Trailer",
                    "official": True,
                    "iso_639_1": "en",
                    "published_at": "2024-01-01T00:00:00.000Z",
                }
            ]
        }

    def tv_videos(self, tmdb_id, *, language=None):
        return {"results": []}


def test_tmdb_client_search_and_token_redaction():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer unit-test-tmdb-token"
        return httpx.Response(200, json={"results": [{"id": 1}]})

    client = TMDBClient(_settings(), http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.search_movie("demo")["results"][0]["id"] == 1

    def bad_handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("unit-test-tmdb-token leaked")

    bad = TMDBClient(_settings(), http_client=httpx.Client(transport=httpx.MockTransport(bad_handler)))
    with pytest.raises(TMDBClientError) as exc:
        bad.search_movie("demo")
    assert "unit-test-tmdb-token" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)


def test_movie_import_duplicate_trailer_and_offline_catalog(db_session, tmp_path: Path):
    settings = _settings(tmp_path)
    fake = FakeTMDB()
    result = import_movie(db_session, settings, 100, client=fake, demo_owned=True, seed_version=REAL_DEMO_SEED_VERSION)
    db_session.commit()
    movie = db_session.get(Movie, result.entity_id)
    assert movie.status == "draft"
    assert movie.tmdb_id == 100
    assert movie.metadata_source == "tmdb"
    assert movie.demo_owned is True
    assert movie.trailer_provider == "YouTube"
    assert movie.trailer_key == "abc123"
    assert movie.trailer_url == "https://www.youtube-nocookie.com/embed/abc123"

    duplicate = import_movie(db_session, settings, 100, client=fake, demo_owned=True, seed_version=REAL_DEMO_SEED_VERSION)
    db_session.commit()
    assert duplicate.entity_id == result.entity_id
    assert db_session.query(Movie).filter(Movie.tmdb_id == 100).count() == 1

    movie.status = "published"
    db_session.commit()
    assert movie_out(movie).title == "Demo Movie"


def test_series_import_episode_ownership(db_session, tmp_path: Path):
    result = import_series(
        db_session,
        _settings(tmp_path),
        200,
        client=FakeTMDB(),
        demo_owned=True,
        seed_version=REAL_DEMO_SEED_VERSION,
        seasons_limit=1,
        episodes_per_season=1,
    )
    db_session.commit()
    assert result.episode_ids
    episode = db_session.get(Episode, result.episode_ids[0])
    assert episode.tmdb_id == 9001
    assert episode.demo_owned is True
    assert episode.metadata_source == "tmdb"


def test_series_import_episode_still_when_available(db_session, tmp_path: Path, monkeypatch):
    class StillTMDB(FakeTMDB):
        def season_details(self, tmdb_id, season_number, *, language=None):
            payload = super().season_details(tmdb_id, season_number, language=language)
            payload["episodes"][0]["still_path"] = "/still.jpg"
            return payload

    from app.services.tmdb import artwork as artwork_mod
    from app.services.tmdb.artwork import StoredArtwork

    def fake_download(settings, url, *, kind, tmdb_id, tmdb_configuration=None, http_client=None):
        assert kind == "still"
        assert "still.jpg" in url
        return StoredArtwork(
            url=f"/artwork/stills/tmdb-still-{tmdb_id}.jpg",
            relative_path=f"stills/tmdb-still-{tmdb_id}.jpg",
            checksum_sha256="abc",
            size_bytes=10,
            width=320,
            height=180,
        )

    monkeypatch.setattr(artwork_mod, "download_artwork", fake_download)
    # import_service binds download_artwork at import time — patch there too
    import app.services.tmdb.import_service as import_mod

    monkeypatch.setattr(import_mod, "download_artwork", fake_download)

    result = import_series(
        db_session,
        _settings(tmp_path),
        200,
        client=StillTMDB(),
        demo_owned=True,
        seed_version=REAL_DEMO_SEED_VERSION,
        seasons_limit=1,
        episodes_per_season=1,
    )
    db_session.commit()
    episode = db_session.get(Episode, result.episode_ids[0])
    assert episode.thumbnail_url.endswith("tmdb-still-9001.jpg")
    assert any(path.startswith("stills/") for path in result.artwork_files)


def test_translation_fallback(db_session, tmp_path: Path):
    class FallbackTMDB(FakeTMDB):
        def movie_details(self, tmdb_id, *, language=None):
            self.movie_detail_calls.append(language or "en-US")
            if language == "fa-AF":
                return _movie_details(id=tmdb_id, title="Fallback Title", overview="Fallback overview")
            return _movie_details(id=tmdb_id, title="", overview="")

    settings = _settings(tmp_path, tmdb_fallback_language="fa-AF")
    result = import_movie(db_session, settings, 101, client=FallbackTMDB(), demo_owned=True, seed_version=REAL_DEMO_SEED_VERSION)
    db_session.commit()
    movie = db_session.get(Movie, result.entity_id)
    assert movie.title == "Fallback Title"
    assert movie.description == "Fallback overview"


def test_image_validation_and_ssrf_rejection(tmp_path: Path):
    settings = _settings(tmp_path)
    with pytest.raises(ArtworkError):
        validate_artwork_url("https://example.com/not-tmdb.jpg")

    png = tmp_path / "poster.png"
    write_rgb_png(png, 32, 32, (1, 2, 3), "Demo")
    stored = store_artwork_bytes(settings, png.read_bytes(), kind="poster", tmdb_id=123, content_type="image/png")
    assert stored.relative_path.startswith("posters/tmdb-poster-123-")
    assert stored.url.startswith("/artwork/posters/")
    assert (Path(settings.artwork_root) / stored.relative_path).is_file()


def test_refresh_demo_metadata_only(db_session, tmp_path: Path):
    settings = _settings(tmp_path)
    fake = FakeTMDB()
    demo = import_movie(db_session, settings, 100, client=fake, demo_owned=True, seed_version=REAL_DEMO_SEED_VERSION)
    real = Movie(title="Real", slug="real", tmdb_id=999, status="draft", metadata_source="tmdb", demo_owned=False)
    db_session.add(real)
    db_session.commit()

    fake.movie_detail_calls.clear()
    results = refresh_demo_metadata(db_session, settings, client=fake, force=True)
    db_session.commit()
    assert [r.entity_id for r in results] == [demo.entity_id]
    assert fake.movie_detail_calls


def test_refresh_demo_series_respects_curated_caps(db_session, tmp_path: Path):
    """Refresh must not expand demo series beyond curated season/episode limits."""
    from app.services.tmdb.curated import CURATED_SERIES

    curated = CURATED_SERIES[0]

    class WideTMDB(FakeTMDB):
        def tv_details(self, tmdb_id, *, language=None):
            self.tv_detail_calls += 1
            return _series_details(
                id=tmdb_id,
                seasons=[{"season_number": n} for n in range(1, 6)],
            )

        def season_details(self, tmdb_id, season_number, *, language=None):
            return {
                "id": season_number,
                "name": f"Season {season_number}",
                "overview": "Season overview",
                "air_date": "2023-01-01",
                "episodes": [
                    {
                        "id": season_number * 100 + n,
                        "episode_number": n,
                        "name": f"E{n}",
                        "overview": "Episode overview",
                        "runtime": 40,
                        "air_date": "2023-01-02",
                        "still_path": None,
                    }
                    for n in range(1, 8)
                ],
            }

    settings = _settings(tmp_path)
    fake = WideTMDB()
    import_series(
        db_session,
        settings,
        curated.tmdb_id,
        client=fake,
        demo_owned=True,
        seed_version=REAL_DEMO_SEED_VERSION,
        seasons_limit=curated.seasons,
        episodes_per_season=curated.episodes_per_season,
    )
    db_session.commit()
    refresh_demo_metadata(db_session, settings, client=fake, force=True)
    db_session.commit()
    from app.models.content import Episode, Season, Series

    series = db_session.query(Series).filter(Series.tmdb_id == curated.tmdb_id).one()
    seasons = db_session.query(Season).filter(Season.series_id == series.id).count()
    episodes = db_session.query(Episode).filter(Episode.series_id == series.id).count()
    assert seasons == curated.seasons
    assert episodes == curated.seasons * curated.episodes_per_season


def test_artwork_replaces_prior_file_for_same_tmdb_id(tmp_path: Path):
    settings = _settings(tmp_path)
    png_a = tmp_path / "a.png"
    png_b = tmp_path / "b.png"
    write_rgb_png(png_a, 16, 16, (1, 2, 3), "A")
    write_rgb_png(png_b, 16, 16, (200, 100, 50), "B")
    first = store_artwork_bytes(settings, png_a.read_bytes(), kind="poster", tmdb_id=42, content_type="image/png")
    second = store_artwork_bytes(settings, png_b.read_bytes(), kind="poster", tmdb_id=42, content_type="image/png")
    root = Path(settings.artwork_root) / "posters"
    files = list(root.glob("tmdb-poster-42-*"))
    assert len(files) == 1
    assert files[0].name == Path(second.relative_path).name
    assert first.checksum_sha256 != second.checksum_sha256


def test_trailer_selection_and_no_trailer():
    selected = select_trailer(
        {
            "results": [
                {"site": "YouTube", "type": "Teaser", "key": "tease", "official": True, "iso_639_1": "en"},
                {"site": "YouTube", "type": "Trailer", "key": "trailer", "official": True, "iso_639_1": "en"},
            ]
        },
        language="en-US",
    )
    assert selected is not None
    assert selected.key == "trailer"
    assert select_trailer({"results": [{"site": "Vimeo", "type": "Trailer", "key": "x"}]}) is None


def test_cleanup_isolates_demo_owned_rows(db_session, tmp_path: Path):
    settings = _settings(tmp_path)
    demo = Movie(title="Demo", slug="tmdb-demo", tmdb_id=1, status="draft", metadata_source="tmdb", demo_owned=True)
    real = Movie(title="Real", slug="real-movie", tmdb_id=2, status="draft", metadata_source="tmdb", demo_owned=False)
    db_session.add_all([demo, real])
    db_session.commit()
    plan = build_cleanup_plan(db_session, settings)
    assert demo.id in plan.movie_ids
    assert real.id not in plan.movie_ids
    assert any("Demo" in title for title in plan.movie_titles)
    assert not any("Real" in title and "real-movie" in title for title in plan.movie_titles)


def test_cleanup_ignores_preserved_demo_slug_rows(db_session, tmp_path: Path):
    """Former fake-demo titles kept as non-demo must never enter the delete plan."""
    from app.services.demo.ownership import DemoOwnership, save_ownership

    settings = _settings(tmp_path)
    preserved = Movie(
        title="Kabul Nights",
        slug="demo-kabul-nights",
        status="published",
        metadata_source="manual",
        demo_owned=False,
    )
    demo = Movie(
        title="Inception",
        slug="inception",
        tmdb_id=27205,
        status="published",
        metadata_source="tmdb",
        demo_owned=True,
    )
    preserved_series = Series(
        title="Mountain Echo",
        slug="demo-series-mountain-echo",
        status="published",
        metadata_source="manual",
        demo_owned=False,
    )
    demo_series = Series(
        title="Stranger Things",
        slug="stranger-things",
        tmdb_id=66732,
        status="published",
        metadata_source="tmdb",
        demo_owned=True,
    )
    db_session.add_all([preserved, demo, preserved_series, demo_series])
    db_session.commit()

    ownership = DemoOwnership(
        seed_version="2.0.0",
        movie_ids=[preserved.id, demo.id],
        series_ids=[preserved_series.id, demo_series.id],
        movie_slugs=[preserved.slug, demo.slug],
        series_slugs=[preserved_series.slug, demo_series.slug],
        artwork_files=[
            "posters/demo-demo-kabul-nights.png",
            "posters/tmdb-inception.jpg",
        ],
        media_files=[
            "/data/media/temp/demo-seed/demo-kabul-nights.mp4",
            "/data/media/temp/demo-seed/inception-clip.mp4",
        ],
    )
    save_ownership(settings, ownership)

    plan = build_cleanup_plan(db_session, settings)
    assert plan.movie_ids == [demo.id]
    assert plan.series_ids == [demo_series.id]
    assert all("demo_owned=True" in title for title in plan.movie_titles)
    assert all("demo_owned=True" in title for title in plan.series_titles)
    assert not any("Kabul Nights" in title for title in plan.movie_titles)
    assert not any("Mountain Echo" in title for title in plan.series_titles)
    assert not any("kabul-nights" in path for path in plan.media_files)
    assert any("inception-clip" in path for path in plan.media_files)


def test_public_movies_200_after_model_update(client):
    response = client.get("/api/movies")
    assert response.status_code == 200


def test_curated_real_demo_v3_catalog_shape():
    from app.services.tmdb.curated import (
        CURATED_MOVIES,
        CURATED_SERIES,
        REAL_DEMO_SEED_VERSION,
        curated_episode_clip_count,
        curated_movie_clip_count,
    )

    assert REAL_DEMO_SEED_VERSION == "3.0.0"
    assert len(CURATED_MOVIES) >= 15
    assert len(CURATED_SERIES) >= 5
    assert curated_movie_clip_count() >= 6
    assert curated_episode_clip_count() >= 6
    movie_ids = [m.tmdb_id for m in CURATED_MOVIES]
    series_ids = [s.tmdb_id for s in CURATED_SERIES]
    assert len(movie_ids) == len(set(movie_ids))
    assert len(series_ids) == len(set(series_ids))
    genre_labels = {g for m in CURATED_MOVIES for g in m.genres}
    for required in (
        "Action",
        "Drama",
        "Comedy",
        "Family",
        "Animation",
        "Thriller",
        "Science Fiction",
        "Documentary",
    ):
        assert required in genre_labels
    for series in CURATED_SERIES:
        assert series.seasons <= 2
        assert series.episodes_per_season <= 3


def test_remove_fake_demo_cli_is_dry_run_by_default(monkeypatch, tmp_path: Path):
    from scripts import real_demo_dry_run, remove_fake_demo

    calls: list[tuple[list[str] | None, bool | None]] = []

    def fake_main(argv=None, *, fake_only=None):
        calls.append((list(argv) if argv is not None else None, fake_only))
        return 0

    monkeypatch.setattr(remove_fake_demo, "remove_demo_main", fake_main)
    monkeypatch.setattr(real_demo_dry_run, "remove_demo_main", fake_main)
    assert remove_fake_demo.main([]) == 0
    assert remove_fake_demo.main(["--confirm"]) == 0
    assert real_demo_dry_run.main(["--confirm"]) == 0
    assert calls[0][1] is True
    assert "--fake-only" in (calls[0][0] or [])
    assert calls[1][1] is True
    assert "--confirm" in (calls[1][0] or [])
    assert calls[2][1] is True
    assert "--confirm" not in (calls[2][0] or [])
