"""Narrow playback eligibility abstraction (Phase 7).

Supported principals:
- admin: operational verification (always eligible when authenticated + streaming enabled)
- subscriber: only assets whose linked catalog entity is published and not deleted

Subscriber subscription/payment/Radius entitlement rules are deferred.
Assets without determinable published ownership are denied.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.models.content import Episode, Movie, Season, Series
from app.models.media_assets import MediaAsset
from app.models.user import Subscriber

DENY_UNAUTHENTICATED = "unauthenticated"
DENY_UNSUPPORTED_PRINCIPAL = "unsupported_principal"
DENY_UNPUBLISHED = "unpublished"
DENY_DELETED = "deleted"
DENY_NO_OWNER = "ownership_undetermined"
DENY_OWNER_MISSING = "owner_missing"
DENY_ASSET_MISSING = "asset_missing"


@dataclass(frozen=True)
class EligibilityResult:
    allowed: bool
    denial_code: str | None = None
    reason: str | None = None

    @classmethod
    def allow(cls) -> EligibilityResult:
        return cls(allowed=True)

    @classmethod
    def deny(cls, code: str, reason: str) -> EligibilityResult:
        return cls(allowed=False, denial_code=code, reason=reason)


class PlaybackEligibilityService:
    """Single place for playback allow/deny decisions."""

    def can_play(
        self,
        db: Session,
        *,
        principal: AdminUser | Subscriber | None,
        media_asset: MediaAsset | None,
    ) -> EligibilityResult:
        if principal is None:
            return EligibilityResult.deny(
                DENY_UNAUTHENTICATED, "Authentication required for playback"
            )
        if media_asset is None:
            return EligibilityResult.deny(DENY_ASSET_MISSING, "Media asset not found")

        if isinstance(principal, AdminUser):
            if not principal.is_active:
                return EligibilityResult.deny(
                    DENY_UNAUTHENTICATED, "Admin account is inactive"
                )
            return EligibilityResult.allow()

        if isinstance(principal, Subscriber):
            if principal.status != "active":
                return EligibilityResult.deny(
                    DENY_UNAUTHENTICATED, "Subscriber account is inactive"
                )
            return self._subscriber_catalog_visibility(db, media_asset)

        return EligibilityResult.deny(
            DENY_UNSUPPORTED_PRINCIPAL, "Unsupported principal type"
        )

    def _subscriber_catalog_visibility(
        self, db: Session, asset: MediaAsset
    ) -> EligibilityResult:
        if asset.movie_id is not None:
            movie = db.get(Movie, asset.movie_id)
            return self._check_entity(movie, label="movie")
        if asset.episode_id is not None:
            episode = db.get(Episode, asset.episode_id)
            ep_result = self._check_entity(episode, label="episode")
            if not ep_result.allowed:
                return ep_result
            assert episode is not None
            series = db.get(Series, episode.series_id) if episode.series_id else None
            series_result = self._check_entity(series, label="series")
            if not series_result.allowed:
                return series_result
            if episode.season_id:
                season = db.get(Season, episode.season_id)
                return self._check_entity(season, label="season")
            return ep_result
        if asset.series_id is not None:
            series = db.get(Series, asset.series_id)
            return self._check_entity(series, label="series")
        if asset.season_id is not None:
            season = db.get(Season, asset.season_id)
            season_result = self._check_entity(season, label="season")
            if not season_result.allowed:
                return season_result
            assert season is not None
            series = db.get(Series, season.series_id) if season.series_id else None
            return self._check_entity(series, label="series")
        return EligibilityResult.deny(
            DENY_NO_OWNER,
            "Media asset has no published catalog owner; playback denied",
        )

    def _check_entity(self, entity, *, label: str) -> EligibilityResult:
        if entity is None:
            return EligibilityResult.deny(
                DENY_OWNER_MISSING, f"Linked {label} was not found"
            )
        deleted_at = getattr(entity, "deleted_at", None)
        if deleted_at is not None:
            return EligibilityResult.deny(
                DENY_DELETED, f"Linked {label} is deleted or archived"
            )
        status = getattr(entity, "status", None)
        if status != "published":
            return EligibilityResult.deny(
                DENY_UNPUBLISHED, f"Linked {label} is not published"
            )
        return EligibilityResult.allow()


playback_eligibility = PlaybackEligibilityService()
