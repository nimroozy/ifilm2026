"""Resolve and persist localized catalog metadata.

Rules:
- manual beats TMDB
- for ``fa``: TMDB Persian beats English fallback
- for ``ps``: English metadata (never Persian as Pashto fallback) unless manual ``ps`` exists
- for ``en``: English title/overview/tagline
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.content_translations import ContentTranslation
from app.models.media_assets import utcnow

Locale = Literal["en", "fa", "ps"]
EntityType = Literal["movie", "series", "episode", "season", "collection"]
Source = Literal["manual", "tmdb", "fallback"]

TEXT_FIELDS = ("title", "description", "short_description", "tagline", "overview", "name")


def normalize_locale(value: str | None) -> Locale:
    code = (value or "en").strip().lower().split("-", 1)[0]
    if code in {"en", "fa", "ps"}:
        return code  # type: ignore[return-value]
    return "en"


def upsert_translation(
    db: Session,
    *,
    entity_type: EntityType,
    entity_id: int,
    locale: Locale,
    field_key: str,
    value: str,
    source: Source,
    overwrite_manual: bool = False,
) -> ContentTranslation | None:
    text = (value or "").strip()
    if not text:
        return None
    row = (
        db.query(ContentTranslation)
        .filter_by(
            entity_type=entity_type,
            entity_id=entity_id,
            locale=locale,
            field_key=field_key,
        )
        .first()
    )
    if row is None:
        row = ContentTranslation(
            entity_type=entity_type,
            entity_id=entity_id,
            locale=locale,
            field_key=field_key,
            value=text,
            source=source,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(row)
        return row
    if row.source == "manual" and source != "manual" and not overwrite_manual:
        return row
    row.value = text
    row.source = source
    row.updated_at = utcnow()
    db.add(row)
    return row


def store_tmdb_locale_bundle(
    db: Session,
    *,
    entity_type: EntityType,
    entity_id: int,
    locale: Locale,
    fields: dict[str, str],
) -> int:
    """Persist TMDB fields for a locale without overwriting manual rows."""
    # Collapse aliases first so overview+description do not double-insert the same key.
    normalized: dict[str, str] = {}
    for key, value in fields.items():
        if key not in TEXT_FIELDS:
            continue
        field_key = "description" if key == "overview" else key
        if key == "name" and entity_type in {"movie", "series", "collection"}:
            field_key = "title"
        text = (value or "").strip()
        if not text:
            continue
        normalized[field_key] = text

    count = 0
    for field_key, value in normalized.items():
        row = upsert_translation(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            locale=locale,
            field_key=field_key,
            value=value,
            source="tmdb",
            overwrite_manual=False,
        )
        if row is not None:
            count += 1
    return count


def _rows_for(
    db: Session, *, entity_type: EntityType, entity_id: int
) -> list[ContentTranslation]:
    return (
        db.query(ContentTranslation)
        .filter_by(entity_type=entity_type, entity_id=entity_id)
        .all()
    )


def load_translations_for_entities(
    db: Session, *, entity_type: EntityType, entity_ids: list[int]
) -> dict[int, list[ContentTranslation]]:
    """Batch-load translations for many entities (one query)."""
    if not entity_ids:
        return {}
    rows = (
        db.query(ContentTranslation)
        .filter(
            ContentTranslation.entity_type == entity_type,
            ContentTranslation.entity_id.in_(list(dict.fromkeys(entity_ids))),
        )
        .all()
    )
    out: dict[int, list[ContentTranslation]] = {eid: [] for eid in entity_ids}
    for row in rows:
        out.setdefault(row.entity_id, []).append(row)
    return out


def resolve_text(
    db: Session,
    *,
    entity_type: EntityType,
    entity_id: int,
    field_key: str,
    locale: Locale,
    canonical: str,
    preloaded_rows: list[ContentTranslation] | None = None,
) -> tuple[str, Source]:
    """Return (value, source) for a field under locale rules."""
    source_rows = (
        preloaded_rows
        if preloaded_rows is not None
        else _rows_for(db, entity_type=entity_type, entity_id=entity_id)
    )
    rows = {(r.locale, r.field_key): r for r in source_rows}
    # Prefer explicit field; also accept overview alias for description.
    candidates_keys = [field_key]
    if field_key == "description":
        candidates_keys.append("overview")
    if field_key == "title":
        candidates_keys.append("name")

    def pick(loc: Locale, source_filter: Source | None = None) -> ContentTranslation | None:
        for key in candidates_keys:
            row = rows.get((loc, key))
            if row is None:
                continue
            if source_filter and row.source != source_filter:
                continue
            if row.value.strip():
                return row
        return None

    if locale == "fa":
        manual = pick("fa", "manual")
        if manual:
            return manual.value, "manual"
        tmdb_fa = pick("fa", "tmdb")
        if tmdb_fa:
            return tmdb_fa.value, "tmdb"
        # English fallback (canonical or stored en)
        en = pick("en")
        if en:
            return en.value, "fallback"
        if canonical.strip():
            return canonical, "fallback"
        return "", "fallback"

    if locale == "ps":
        manual_ps = pick("ps", "manual")
        if manual_ps:
            return manual_ps.value, "manual"
        # Never use Persian as Pashto fallback.
        en = pick("en")
        if en:
            return en.value, "fallback"
        if canonical.strip():
            return canonical, "fallback"
        return "", "fallback"

    # en
    manual_en = pick("en", "manual")
    if manual_en:
        return manual_en.value, "manual"
    tmdb_en = pick("en", "tmdb")
    if tmdb_en:
        return tmdb_en.value, "tmdb"
    if canonical.strip():
        return canonical, "fallback"
    return "", "fallback"


def _localized_fields_from_rows(
    *,
    db: Session,
    entity_type: EntityType,
    entity_id: int,
    locale: Locale,
    canonical: dict[str, str],
    preloaded_rows: list[ContentTranslation] | None,
) -> dict[str, Any]:
    rows = preloaded_rows
    title, title_src = resolve_text(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field_key="title",
        locale=locale,
        canonical=canonical.get("title", ""),
        preloaded_rows=rows,
    )
    description, desc_src = resolve_text(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field_key="description",
        locale=locale,
        canonical=canonical.get("description", ""),
        preloaded_rows=rows,
    )
    short, short_src = resolve_text(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field_key="short_description",
        locale=locale,
        canonical=canonical.get("short_description", ""),
        preloaded_rows=rows,
    )
    tagline, tag_src = resolve_text(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field_key="tagline",
        locale=locale,
        canonical=canonical.get("tagline", ""),
        preloaded_rows=rows,
    )
    return {
        "title": title or canonical.get("title", ""),
        "description": description or canonical.get("description", ""),
        "short_description": short or canonical.get("short_description", ""),
        "tagline": tagline,
        "localization": {
            "locale": locale,
            "sources": {
                "title": title_src,
                "description": desc_src,
                "short_description": short_src,
                "tagline": tag_src,
            },
        },
    }


def localized_movie_fields(
    db: Session,
    movie: Any,
    locale: Locale,
    *,
    preloaded_rows: list[ContentTranslation] | None = None,
) -> dict[str, Any]:
    rows = preloaded_rows
    if rows is None:
        rows = _rows_for(db, entity_type="movie", entity_id=movie.id)
    return _localized_fields_from_rows(
        db=db,
        entity_type="movie",
        entity_id=movie.id,
        locale=locale,
        canonical={
            "title": str(movie.title or ""),
            "description": str(movie.description or ""),
            "short_description": str(movie.short_description or ""),
            "tagline": "",
        },
        preloaded_rows=rows,
    )


def localized_series_fields(
    db: Session,
    series: Any,
    locale: Locale,
    *,
    preloaded_rows: list[ContentTranslation] | None = None,
) -> dict[str, Any]:
    rows = preloaded_rows
    if rows is None:
        rows = _rows_for(db, entity_type="series", entity_id=series.id)
    return _localized_fields_from_rows(
        db=db,
        entity_type="series",
        entity_id=series.id,
        locale=locale,
        canonical={
            "title": str(series.title or ""),
            "description": str(series.description or ""),
            "short_description": str(series.short_description or ""),
            "tagline": "",
        },
        preloaded_rows=rows,
    )


def localized_episode_fields(
    db: Session, episode: Any, locale: Locale
) -> dict[str, Any]:
    title, title_src = resolve_text(
        db,
        entity_type="episode",
        entity_id=episode.id,
        field_key="title",
        locale=locale,
        canonical=str(episode.title or ""),
    )
    description, desc_src = resolve_text(
        db,
        entity_type="episode",
        entity_id=episode.id,
        field_key="description",
        locale=locale,
        canonical=str(episode.description or ""),
    )
    return {
        "title": title or episode.title,
        "description": description or episode.description or "",
        "localization": {
            "locale": locale,
            "sources": {
                "title": title_src,
                "description": desc_src,
            },
        },
    }
