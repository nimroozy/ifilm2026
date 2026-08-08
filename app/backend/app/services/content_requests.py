"""Content request workflow: validation, duplicates, catalog match, admin transitions."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.admin import AdminUser
from app.models.content import Movie, Series
from app.models.content_requests import (
    OPEN_STATUSES,
    REQUEST_STATUSES,
    WITHDRAWABLE_STATUSES,
    ContentRequest,
    ContentRequestEvent,
    utcnow,
)
from app.models.user import Subscriber
from app.services.publishing.visibility import apply_public_visibility
from app.services.rate_limit import SlidingWindowRateLimiter

logger = logging.getLogger("app.content_requests.audit")

content_request_rate_limiter = SlidingWindowRateLimiter()

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"reviewing", "approved", "rejected", "withdrawn"}),
    "reviewing": frozenset({"approved", "rejected", "withdrawn", "new"}),
    "approved": frozenset({"added", "rejected", "reviewing"}),
    "rejected": frozenset({"reviewing"}),  # explicit reopen only
    "added": frozenset(),
    "withdrawn": frozenset(),
}

ACTION_TO_STATUS = {
    "review": "reviewing",
    "approve": "approved",
    "reject": "rejected",
    "mark_added": "added",
    "reopen": "reviewing",
}


def normalize_title(value: str) -> str:
    cleaned = (value or "").strip().lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def parse_external_ids(
    *,
    tmdb_url: str | None,
    imdb_url: str | None,
    tmdb_id: int | None,
    imdb_id: str | None,
) -> tuple[int | None, str | None, str | None, str | None]:
    """Return (tmdb_id, imdb_id, tmdb_url, imdb_url) after host validation.

    Does not fetch remote URLs.
    """
    out_tmdb = tmdb_id
    out_imdb = (imdb_id or "").strip() or None
    out_tmdb_url = tmdb_url
    out_imdb_url = imdb_url

    if tmdb_url:
        _host, path = _parse_url(tmdb_url, allowed_hosts={"www.themoviedb.org", "themoviedb.org"})
        m = re.search(r"/(movie|tv)/(\d+)", path)
        if not m:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_tmdb_url", "message": "Unrecognized TMDB URL"},
            )
        parsed_id = int(m.group(2))
        if out_tmdb is not None and out_tmdb != parsed_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "tmdb_id_mismatch", "message": "TMDB id does not match URL"},
            )
        out_tmdb = parsed_id
        out_tmdb_url = f"https://www.themoviedb.org/{m.group(1)}/{parsed_id}"

    if imdb_url:
        _host, path = _parse_url(imdb_url, allowed_hosts={"www.imdb.com", "imdb.com"})
        m = re.search(r"/(title)/(tt\d+)", path, flags=re.IGNORECASE)
        if not m:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_imdb_url", "message": "Unrecognized IMDb URL"},
            )
        parsed_imdb = m.group(2).lower()
        if out_imdb and out_imdb.lower() != parsed_imdb:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "imdb_id_mismatch", "message": "IMDb id does not match URL"},
            )
        out_imdb = parsed_imdb
        out_imdb_url = f"https://www.imdb.com/title/{parsed_imdb}/"

    if out_imdb:
        if not re.fullmatch(r"tt\d{5,}", out_imdb.lower()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_imdb_id", "message": "IMDb id must look like tt1234567"},
            )
        out_imdb = out_imdb.lower()

    return out_tmdb, out_imdb, out_tmdb_url, out_imdb_url


def _parse_url(url: str, *, allowed_hosts: set[str]) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_url", "message": "URL must be http(s)"},
        )
    host = parsed.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host_key = host
    else:
        host_key = host
    if host_key not in allowed_hosts and f"www.{host_key}" not in allowed_hosts and host_key.replace("www.", "") not in {
        h.replace("www.", "") for h in allowed_hosts
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "url_host_not_allowed", "message": f"Host not allowed: {host}"},
        )
    return host, parsed.path or ""


def _catalog_public_dict(kind: str, row: Movie | Series, *, reason: str, strength: str) -> dict[str, Any]:
    slug = row.slug
    return {
        "content_type": kind,
        "id": row.id,
        "slug": slug,
        "title": row.title,
        "release_year": row.release_year,
        "poster_url": row.poster_url or "",
        "detail_path": f"/movie/{slug}" if kind == "movie" else f"/series/{slug}",
        "match_strength": strength,
        "match_reason": reason,
    }


def find_catalog_matches(
    db: Session,
    *,
    request_type: str,
    title: str,
    year: int | None,
    tmdb_id: int | None,
    imdb_id: str | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return (exact_match, fuzzy_suggestions)."""
    exact: dict[str, Any] | None = None
    suggestions: list[dict[str, Any]] = []
    norm = normalize_title(title)

    def movie_q():
        return apply_public_visibility(db.query(Movie), Movie)

    def series_q():
        return apply_public_visibility(db.query(Series), Series)

    if request_type == "movie":
        if tmdb_id is not None:
            row = movie_q().filter(Movie.tmdb_id == tmdb_id).first()
            if row:
                return _catalog_public_dict("movie", row, reason="tmdb_id", strength="exact"), []
        if imdb_id:
            row = movie_q().filter(func.lower(Movie.imdb_id) == imdb_id.lower()).first()
            if row:
                return _catalog_public_dict("movie", row, reason="imdb_id", strength="exact"), []
        if year is not None:
            row = movie_q().filter(func.lower(Movie.title) == title.strip().lower(), Movie.release_year == year).first()
            if row is None:
                # normalized compare in Python for small candidate set
                for cand in movie_q().filter(Movie.release_year == year).limit(80).all():
                    if normalize_title(cand.title) == norm:
                        row = cand
                        break
            if row:
                return _catalog_public_dict("movie", row, reason="title_year", strength="exact"), []
        # Fuzzy: title-only
        for cand in movie_q().filter(Movie.title.ilike(f"%{title.strip()[:40]}%")).limit(12).all():
            if normalize_title(cand.title) == norm:
                suggestions.append(
                    _catalog_public_dict("movie", cand, reason="title", strength="likely")
                )
            elif norm and norm in normalize_title(cand.title):
                suggestions.append(
                    _catalog_public_dict("movie", cand, reason="title_partial", strength="likely")
                )
    else:
        if tmdb_id is not None:
            row = series_q().filter(Series.tmdb_id == tmdb_id).first()
            if row:
                return _catalog_public_dict("series", row, reason="tmdb_id", strength="exact"), []
        if imdb_id:
            row = series_q().filter(func.lower(Series.imdb_id) == imdb_id.lower()).first()
            if row:
                return _catalog_public_dict("series", row, reason="imdb_id", strength="exact"), []
        if year is not None:
            row = None
            for cand in series_q().filter(Series.release_year == year).limit(80).all():
                if normalize_title(cand.title) == norm:
                    row = cand
                    break
            if row:
                return _catalog_public_dict("series", row, reason="title_year", strength="exact"), []
        for cand in series_q().filter(Series.title.ilike(f"%{title.strip()[:40]}%")).limit(12).all():
            if normalize_title(cand.title) == norm:
                suggestions.append(
                    _catalog_public_dict("series", cand, reason="title", strength="likely")
                )
            elif norm and norm in normalize_title(cand.title):
                suggestions.append(
                    _catalog_public_dict("series", cand, reason="title_partial", strength="likely")
                )

    # Deduplicate suggestions
    seen: set[tuple[str, int]] = set()
    unique: list[dict[str, Any]] = []
    for item in suggestions:
        key = (item["content_type"], item["id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return exact, unique[:8]


def find_user_duplicate(
    db: Session,
    *,
    subscriber_id: int,
    request_type: str,
    title: str,
    year: int | None,
    tmdb_id: int | None,
    imdb_id: str | None,
) -> ContentRequest | None:
    q = db.query(ContentRequest).filter(
        ContentRequest.subscriber_id == subscriber_id,
        ContentRequest.request_type == request_type,
        ContentRequest.status.in_(tuple(OPEN_STATUSES | {"rejected"})),
    )
    if tmdb_id is not None:
        hit = q.filter(ContentRequest.tmdb_id == tmdb_id).order_by(ContentRequest.id.desc()).first()
        if hit:
            return hit
    if imdb_id:
        hit = q.filter(func.lower(ContentRequest.imdb_id) == imdb_id.lower()).order_by(ContentRequest.id.desc()).first()
        if hit:
            return hit
    norm = normalize_title(title)
    hit = (
        q.filter(ContentRequest.normalized_title == norm)
        .filter(ContentRequest.year == year if year is not None else ContentRequest.year.is_(None))
        .order_by(ContentRequest.id.desc())
        .first()
    )
    return hit


def demand_count(
    db: Session,
    *,
    request_type: str,
    normalized_title: str,
    year: int | None,
    tmdb_id: int | None,
    imdb_id: str | None,
) -> int:
    q = db.query(func.count(ContentRequest.id)).filter(
        ContentRequest.request_type == request_type,
        ContentRequest.status != "withdrawn",
    )
    if tmdb_id is not None:
        return int(q.filter(ContentRequest.tmdb_id == tmdb_id).scalar() or 0)
    if imdb_id:
        return int(q.filter(func.lower(ContentRequest.imdb_id) == imdb_id.lower()).scalar() or 0)
    filt = [ContentRequest.normalized_title == normalized_title]
    if year is not None:
        filt.append(ContentRequest.year == year)
    return int(q.filter(and_(*filt)).scalar() or 0)


def _linked_paths(db: Session, row: ContentRequest) -> tuple[str | None, str | None]:
    if row.linked_movie_id:
        movie = db.get(Movie, row.linked_movie_id)
        if movie:
            return f"/movie/{movie.slug}", movie.title
    if row.linked_series_id:
        series = db.get(Series, row.linked_series_id)
        if series:
            return f"/series/{series.slug}", series.title
    return None, None


def to_public_dict(db: Session, row: ContentRequest, *, include_admin: bool = False) -> dict[str, Any]:
    path, linked_title = _linked_paths(db, row)
    payload: dict[str, Any] = {
        "id": row.id,
        "request_type": row.request_type,
        "title": row.title,
        "year": row.year,
        "tmdb_id": row.tmdb_id,
        "imdb_id": row.imdb_id,
        "tmdb_url": row.tmdb_url,
        "imdb_url": row.imdb_url,
        "preferred_language": row.preferred_language,
        "notes": row.notes,
        "status": row.status,
        "public_response": row.public_response,
        "linked_movie_id": row.linked_movie_id,
        "linked_series_id": row.linked_series_id,
        "linked_detail_path": path,
        "linked_title": linked_title,
        "demand_count": demand_count(
            db,
            request_type=row.request_type,
            normalized_title=row.normalized_title,
            year=row.year,
            tmdb_id=row.tmdb_id,
            imdb_id=row.imdb_id,
        ),
        "created_at": _iso(row.created_at) or "",
        "updated_at": _iso(row.updated_at) or "",
        "reviewed_at": _iso(row.reviewed_at),
    }
    if include_admin:
        subscriber = db.get(Subscriber, row.subscriber_id)
        payload.update(
            {
                "subscriber_id": row.subscriber_id,
                "subscriber_username": subscriber.username if subscriber else None,
                "admin_note": row.admin_note,
                "reviewed_by_admin_id": row.reviewed_by_admin_id,
                "normalized_title": row.normalized_title,
            }
        )
    return payload


def _record_event(
    db: Session,
    row: ContentRequest,
    *,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    admin: AdminUser | None = None,
    subscriber: Subscriber | None = None,
    detail: str | None = None,
) -> None:
    db.add(
        ContentRequestEvent(
            content_request_id=row.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_admin_id=admin.id if admin else None,
            actor_subscriber_id=subscriber.id if subscriber else None,
            detail=(detail or "")[:2000] or None,
            created_at=utcnow(),
        )
    )
    logger.info(
        "content_request_audit event=%s request_id=%s from=%s to=%s admin=%s subscriber=%s",
        event_type,
        row.id,
        from_status,
        to_status,
        admin.id if admin else None,
        subscriber.id if subscriber else None,
    )


def _enforce_rate_limits(db: Session, subscriber: Subscriber, settings: Settings) -> None:
    per_day = int(getattr(settings, "content_request_max_per_day", 5) or 5)
    max_open = int(getattr(settings, "content_request_max_open", 20) or 20)
    window = int(getattr(settings, "content_request_rate_window_seconds", 86400) or 86400)
    key = f"content_request:{subscriber.id}"
    if not content_request_rate_limiter.allow(key, limit=per_day, window_seconds=window):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limited",
                "message": f"Maximum {per_day} new requests per 24 hours",
            },
        )
    open_count = (
        db.query(func.count(ContentRequest.id))
        .filter(
            ContentRequest.subscriber_id == subscriber.id,
            ContentRequest.status.in_(tuple(OPEN_STATUSES)),
        )
        .scalar()
        or 0
    )
    if int(open_count) >= max_open:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "too_many_open_requests",
                "message": f"Maximum {max_open} open requests allowed",
            },
        )


def create_request(
    db: Session,
    subscriber: Subscriber,
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    request_type = payload["request_type"]
    title = payload["title"]
    year = payload.get("year")
    tmdb_id, imdb_id, tmdb_url, imdb_url = parse_external_ids(
        tmdb_url=payload.get("tmdb_url"),
        imdb_url=payload.get("imdb_url"),
        tmdb_id=payload.get("tmdb_id"),
        imdb_id=payload.get("imdb_id"),
    )
    force = bool(payload.get("force"))

    exact, suggestions = find_catalog_matches(
        db,
        request_type=request_type,
        title=title,
        year=year,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
    )
    if exact:
        return {
            "outcome": "already_available",
            "message": "This title is already available.",
            "request": None,
            "catalog_item": exact,
            "suggestions": [],
        }

    dup = find_user_duplicate(
        db,
        subscriber_id=subscriber.id,
        request_type=request_type,
        title=title,
        year=year,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
    )
    if dup:
        return {
            "outcome": "existing_request",
            "message": "You already have an open request for this title.",
            "request": to_public_dict(db, dup),
            "catalog_item": None,
            "suggestions": suggestions,
        }

    if suggestions and not force:
        return {
            "outcome": "suggestions",
            "message": "Similar titles may already be available. Confirm to continue.",
            "request": None,
            "catalog_item": None,
            "suggestions": suggestions,
        }

    _enforce_rate_limits(db, subscriber, settings)

    now = utcnow()
    row = ContentRequest(
        subscriber_id=subscriber.id,
        request_type=request_type,
        title=title.strip(),
        normalized_title=normalize_title(title),
        year=year,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        tmdb_url=tmdb_url,
        imdb_url=imdb_url,
        preferred_language=payload.get("preferred_language"),
        notes=payload.get("notes"),
        status="new",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        row,
        event_type="created",
        from_status=None,
        to_status="new",
        subscriber=subscriber,
    )
    db.flush()
    return {
        "outcome": "created",
        "message": "Request submitted for review.",
        "request": to_public_dict(db, row),
        "catalog_item": None,
        "suggestions": [],
    }


def list_for_subscriber(
    db: Session,
    subscriber: Subscriber,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    page = max(1, page)
    page_size = max(1, min(page_size, 50))
    q = db.query(ContentRequest).filter(ContentRequest.subscriber_id == subscriber.id)
    total = q.count()
    rows = (
        q.order_by(ContentRequest.created_at.desc(), ContentRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [to_public_dict(db, r) for r in rows], total


def get_for_subscriber(db: Session, subscriber: Subscriber, request_id: int) -> dict[str, Any]:
    row = (
        db.query(ContentRequest)
        .filter(ContentRequest.id == request_id, ContentRequest.subscriber_id == subscriber.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return to_public_dict(db, row)


def withdraw(db: Session, subscriber: Subscriber, request_id: int) -> dict[str, Any]:
    row = (
        db.query(ContentRequest)
        .filter(ContentRequest.id == request_id, ContentRequest.subscriber_id == subscriber.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if row.status not in WITHDRAWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "not_withdrawable",
                "message": "Only new or reviewing requests can be withdrawn",
            },
        )
    previous = row.status
    row.status = "withdrawn"
    row.updated_at = utcnow()
    _record_event(
        db,
        row,
        event_type="withdrawn",
        from_status=previous,
        to_status="withdrawn",
        subscriber=subscriber,
    )
    db.flush()
    return to_public_dict(db, row)


def admin_list(
    db: Session,
    *,
    status_filter: str | None = None,
    request_type: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    query = db.query(ContentRequest)
    if status_filter and status_filter in REQUEST_STATUSES:
        query = query.filter(ContentRequest.status == status_filter)
    if request_type in {"movie", "series"}:
        query = query.filter(ContentRequest.request_type == request_type)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                ContentRequest.title.ilike(like),
                ContentRequest.normalized_title.ilike(like),
                ContentRequest.imdb_id.ilike(like),
            )
        )
    total = query.count()
    rows = (
        query.order_by(ContentRequest.created_at.desc(), ContentRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    aggregates = aggregate_demand(db, limit=25)
    return {
        "items": [to_public_dict(db, r, include_admin=True) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "aggregates": aggregates,
    }


def aggregate_demand(db: Session, *, limit: int = 25) -> list[dict[str, Any]]:
    rows = (
        db.query(ContentRequest)
        .filter(ContentRequest.status != "withdrawn")
        .order_by(ContentRequest.created_at.desc())
        .limit(2000)
        .all()
    )
    buckets: dict[tuple[str, str, int | None, int | None, str | None], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.request_type,
            row.normalized_title,
            row.year,
            row.tmdb_id,
            (row.imdb_id or "").lower() or None,
        )
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "request_type": row.request_type,
                "title": row.title,
                "normalized_title": row.normalized_title,
                "year": row.year,
                "tmdb_id": row.tmdb_id,
                "imdb_id": row.imdb_id,
                "request_count": 0,
                "open_count": 0,
                "preferred_languages": {},
                "latest_requested_at": None,
            }
            buckets[key] = bucket
        bucket["request_count"] += 1
        if row.status in OPEN_STATUSES:
            bucket["open_count"] += 1
        if row.preferred_language:
            langs = bucket["preferred_languages"]
            langs[row.preferred_language] = int(langs.get(row.preferred_language, 0)) + 1
        created = _iso(row.created_at)
        if created and (bucket["latest_requested_at"] is None or created > bucket["latest_requested_at"]):
            bucket["latest_requested_at"] = created
            bucket["title"] = row.title
    ranked = sorted(
        buckets.values(),
        key=lambda b: (-b["request_count"], -(b["open_count"]), b["latest_requested_at"] or ""),
    )
    return ranked[:limit]


def admin_get(db: Session, request_id: int) -> dict[str, Any]:
    row = db.get(ContentRequest, request_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    events = (
        db.query(ContentRequestEvent)
        .filter(ContentRequestEvent.content_request_id == row.id)
        .order_by(ContentRequestEvent.created_at.desc(), ContentRequestEvent.id.desc())
        .limit(50)
        .all()
    )
    return {
        "request": to_public_dict(db, row, include_admin=True),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "actor_admin_id": e.actor_admin_id,
                "actor_subscriber_id": e.actor_subscriber_id,
                "detail": e.detail,
                "created_at": _iso(e.created_at) or "",
            }
            for e in events
        ],
    }


def admin_transition(
    db: Session,
    admin: AdminUser,
    request_id: int,
    *,
    action: str,
    admin_note: str | None = None,
    public_response: str | None = None,
    linked_movie_id: int | None = None,
    linked_series_id: int | None = None,
) -> dict[str, Any]:
    row = db.get(ContentRequest, request_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if action not in ACTION_TO_STATUS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown action")
    target = ACTION_TO_STATUS[action]
    if action == "reopen" and row.status != "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_transition", "message": "Only rejected requests can be reopened"},
        )
    allowed = ALLOWED_TRANSITIONS.get(row.status, frozenset())
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_transition",
                "message": f"Cannot transition from {row.status} to {target}",
            },
        )

    if action == "mark_added":
        if row.request_type == "movie":
            if linked_movie_id is None or linked_series_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Movie requests must link a movie",
                )
            movie = db.get(Movie, linked_movie_id)
            if movie is None:
                raise HTTPException(status_code=404, detail="Movie not found")
            row.linked_movie_id = movie.id
            row.linked_series_id = None
            if not public_response:
                public_response = "Available now"
        else:
            if linked_series_id is None or linked_movie_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Series requests must link a series",
                )
            series = db.get(Series, linked_series_id)
            if series is None:
                raise HTTPException(status_code=404, detail="Series not found")
            row.linked_series_id = series.id
            row.linked_movie_id = None
            if not public_response:
                public_response = "Available now"

    previous = row.status
    row.status = target
    row.updated_at = utcnow()
    row.reviewed_by_admin_id = admin.id
    row.reviewed_at = utcnow()
    if admin_note is not None:
        row.admin_note = admin_note.strip() or None
    if public_response is not None:
        row.public_response = public_response.strip() or None
    _record_event(
        db,
        row,
        event_type=f"admin_{action}",
        from_status=previous,
        to_status=target,
        admin=admin,
        detail=admin_note,
    )
    db.flush()
    return to_public_dict(db, row, include_admin=True)
