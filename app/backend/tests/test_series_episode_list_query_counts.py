"""G2b: measure season episode list SQL growth (playability / tracks)."""

from __future__ import annotations

import pytest
from app.models.content import Episode, Genre, Season, Series
from app.models.media_assets import MediaAsset, new_uuid
from app.models.media_tracks import MediaTrack
from app.services.catalog import utcnow
from sqlalchemy import event


def _seed_season_with_assets(db_session, *, episode_count: int, slug: str) -> Series:
    genre = db_session.query(Genre).filter(Genre.slug == "g2b-ep-sql").one_or_none()
    if genre is None:
        genre = Genre(name="G2b Ep SQL", slug="g2b-ep-sql")
        db_session.add(genre)
        db_session.flush()

    now = utcnow()
    series = Series(
        title=f"Episode SQL Series {episode_count}",
        slug=slug,
        status="published",
        published_at=now,
        airing_status="Ended",
        description="season query measurement",
    )
    series.genre_links = [genre]
    db_session.add(series)
    db_session.flush()

    season = Season(
        series_id=series.id,
        season_number=1,
        title="Season 1",
        status="published",
        published_at=now,
    )
    db_session.add(season)
    db_session.flush()

    for i in range(1, episode_count + 1):
        ep = Episode(
            series_id=series.id,
            season_id=season.id,
            episode_number=i,
            title=f"E{i}",
            description=f"Episode {i}",
            duration_minutes=40,
            status="published",
            published_at=now,
        )
        db_session.add(ep)
        db_session.flush()
        asset = MediaAsset(
            id=new_uuid(),
            original_filename=f"e{i}.mp4",
            stored_filename=f"e{i}.mp4",
            mime_type="video/mp4",
            extension=".mp4",
            size_bytes=1024,
            category="originals",
            upload_status="completed",
            processing_status="completed",
            storage_backend="local",
            storage_path=f"originals/g2b/{slug}/e{i}.mp4",
            episode_id=ep.id,
            duration_seconds=2400.0,
            audio_stream_count=1,
            subtitle_stream_count=1,
            probe_json={"streams": [{"codec_type": "audio", "tags": {"language": "eng"}}]},
            probed_at=now,
        )
        db_session.add(asset)
        db_session.flush()
        db_session.add(
            MediaTrack(
                media_asset_id=asset.id,
                track_type="audio",
                language_code="en",
                sort_order=0,
                is_default=True,
            )
        )
        db_session.add(
            MediaTrack(
                media_asset_id=asset.id,
                track_type="subtitle",
                language_code="fa",
                sort_order=0,
                is_default=False,
            )
        )

    db_session.commit()
    return series


def _classify(statements: list[str]) -> dict[str, int]:
    buckets = {
        "playability_or_assets": 0,
        "media_tracks": 0,
        "packages": 0,
        "translations": 0,
        "other": 0,
    }
    for raw in statements:
        s = raw.lower()
        if "media_tracks" in s:
            buckets["media_tracks"] += 1
        elif "media_packages" in s or "package_files" in s:
            buckets["packages"] += 1
        elif "content_translations" in s:
            buckets["translations"] += 1
        elif "media_assets" in s:
            buckets["playability_or_assets"] += 1
        else:
            buckets["other"] += 1
    return buckets


def _measure(client, db_session, episode_count: int, slug: str) -> tuple[int, dict[str, int]]:
    series = _seed_season_with_assets(db_session, episode_count=episode_count, slug=slug)
    engine = db_session.get_bind()
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(str(statement))

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        resp = client.get(f"/api/series/{series.id}/episodes?season=1")
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert resp.status_code == 200
    assert len(resp.json()) == episode_count
    return len(statements), _classify(statements)


@pytest.mark.parametrize("episode_count", [3, 10, 20])
def test_season_episode_list_query_growth(client, db_session, episode_count):
    total, classified = _measure(
        client, db_session, episode_count, slug=f"g2b-ep-sql-{episode_count}"
    )
    print(
        f"G2B_EP_SQL episode_count={episode_count} total_queries={total} "
        f"classified={classified}"
    )
    # Batched path: asset/package/track lookups must not grow per episode.
    assert classified["playability_or_assets"] <= 2
    assert classified["media_tracks"] <= 1
    assert classified["packages"] <= 2
    assert classified["translations"] <= 1
    assert total <= 25


def test_season_episode_list_query_not_linear_unbounded(client, db_session):
    """Compare 3 vs 20 episode seasons; batched path must stay roughly flat."""
    counts: dict[int, int] = {}
    classified_by_n: dict[int, dict[str, int]] = {}
    for n in (3, 10, 20):
        total, classified = _measure(
            client, db_session, n, slug=f"g2b-ep-sql-cmp-{n}"
        )
        counts[n] = total
        classified_by_n[n] = classified
        print(f"G2B_EP_SQL_CMP n={n} total={total} classified={classified}")

    print(
        f"G2B_EP_SQL_DELTA 3→20: {counts[3]}→{counts[20]} "
        f"(delta={counts[20] - counts[3]})"
    )
    # Hard ceiling for a realistic 20-episode season after batching.
    assert counts[20] <= 25, (
        f"season episode list queries too high for 20 episodes: {counts[20]} "
        f"(classified={classified_by_n[20]})"
    )
    # Must not grow approximately linearly with episode count.
    assert counts[20] <= counts[3] + 6, (
        "Episode season list SQL still scales with episode count "
        f"(3→{counts[3]}, 10→{counts[10]}, 20→{counts[20]}). "
        "Batch playability/tracks before G2b Ready."
    )
