"""G2b: series credits are detail-only (include_credits), never on browse cards."""

from __future__ import annotations

from app.models.content import Genre, Series
from app.models.credits import SeriesCastCredit
from app.services.catalog import series_out


def _seed_series_with_credits(db_session):
    genre = Genre(name="Drama", slug="drama-g2b-credits")
    db_session.add(genre)
    db_session.flush()
    series = Series(
        title="Credits Series",
        slug="credits-series-g2b",
        status="published",
        airing_status="Ongoing",
        description="Detail credits fixture",
    )
    series.genre_links = [genre]
    db_session.add(series)
    db_session.flush()
    db_session.add(
        SeriesCastCredit(
            series_id=series.id,
            tmdb_person_id=101,
            name="Ada Lovelace",
            character_name="Lead",
            profile_path="/ada.jpg",
            profile_url="https://image.tmdb.org/t/p/w185/ada.jpg",
            credit_order=0,
        )
    )
    db_session.commit()
    return series


def test_series_out_credits_opt_in(db_session):
    series = _seed_series_with_credits(db_session)
    without = series_out(series, db=db_session, public_counts=True, include_credits=False)
    assert without.credits == []
    with_credits = series_out(series, db=db_session, public_counts=True, include_credits=True)
    assert len(with_credits.credits) == 1
    assert with_credits.credits[0].name == "Ada Lovelace"
    assert with_credits.credits[0].character == "Lead"


def test_public_series_detail_includes_credits(client, db_session):
    series = _seed_series_with_credits(db_session)
    engine = db_session.get_bind()
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(str(statement))

    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        resp = client.get(f"/api/series/{series.id}")
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body.get("credits") or []) == 1
    assert body["credits"][0]["name"] == "Ada Lovelace"
    joined = " ".join(statements).lower()
    assert "series_cast_credits" in joined
    # One credits query — not N+1 cast rows as separate selects beyond the list query.
    credit_hits = sum(1 for s in statements if "series_cast_credits" in s.lower())
    assert credit_hits <= 2, f"unexpected credits query count: {credit_hits}"


def test_series_list_omits_credits_payload(client, db_session):
    _seed_series_with_credits(db_session)
    resp = client.get("/api/series?page_size=20&sort=newest")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert items
    for item in items:
        assert item.get("credits") in (None, [])
