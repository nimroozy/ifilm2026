"""Persistent ownership tracking for demo-owned rows and generated files."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.demo.constants import DEMO_DIRNAME, DEMO_OWNERSHIP_FILENAME, DEMO_SEED_VERSION


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def demo_root(settings: Settings) -> Path:
    override = (os.environ.get("DEMO_DATA_DIR") or "").strip()
    if override:
        root = Path(override)
    else:
        root = Path(settings.artwork_root) / DEMO_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def ownership_path(settings: Settings) -> Path:
    return demo_root(settings) / DEMO_OWNERSHIP_FILENAME


@dataclass
class DemoOwnership:
    seed_version: str = DEMO_SEED_VERSION
    commit_sha: str = ""
    installed_at: str = ""
    admin_usernames: list[str] = field(default_factory=list)
    admin_role_names: list[str] = field(default_factory=list)
    subscriber_usernames: list[str] = field(default_factory=list)
    genre_ids_created: list[int] = field(default_factory=list)
    genre_slugs: list[str] = field(default_factory=list)
    movie_ids: list[int] = field(default_factory=list)
    movie_slugs: list[str] = field(default_factory=list)
    series_ids: list[int] = field(default_factory=list)
    series_slugs: list[str] = field(default_factory=list)
    season_ids: list[int] = field(default_factory=list)
    episode_ids: list[int] = field(default_factory=list)
    media_asset_ids: list[str] = field(default_factory=list)
    package_ids: list[str] = field(default_factory=list)
    artwork_files: list[str] = field(default_factory=list)
    media_files: list[str] = field(default_factory=list)
    watch_progress_ids: list[int] = field(default_factory=list)
    collection_ids: list[int] = field(default_factory=list)
    collection_slugs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_version": self.seed_version,
            "commit_sha": self.commit_sha,
            "installed_at": self.installed_at,
            "admin_usernames": sorted(set(self.admin_usernames)),
            "admin_role_names": sorted(set(self.admin_role_names)),
            "subscriber_usernames": sorted(set(self.subscriber_usernames)),
            "genre_ids_created": sorted(set(self.genre_ids_created)),
            "genre_slugs": sorted(set(self.genre_slugs)),
            "movie_ids": sorted(set(self.movie_ids)),
            "movie_slugs": sorted(set(self.movie_slugs)),
            "series_ids": sorted(set(self.series_ids)),
            "series_slugs": sorted(set(self.series_slugs)),
            "season_ids": sorted(set(self.season_ids)),
            "episode_ids": sorted(set(self.episode_ids)),
            "media_asset_ids": sorted(set(self.media_asset_ids)),
            "package_ids": sorted(set(self.package_ids)),
            "artwork_files": sorted(set(self.artwork_files)),
            "media_files": sorted(set(self.media_files)),
            "watch_progress_ids": sorted(set(self.watch_progress_ids)),
            "collection_ids": sorted(set(self.collection_ids)),
            "collection_slugs": sorted(set(self.collection_slugs)),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DemoOwnership:
        return cls(
            seed_version=str(data.get("seed_version") or DEMO_SEED_VERSION),
            commit_sha=str(data.get("commit_sha") or ""),
            installed_at=str(data.get("installed_at") or ""),
            admin_usernames=list(data.get("admin_usernames") or []),
            admin_role_names=list(data.get("admin_role_names") or []),
            subscriber_usernames=list(data.get("subscriber_usernames") or []),
            genre_ids_created=[int(x) for x in (data.get("genre_ids_created") or [])],
            genre_slugs=list(data.get("genre_slugs") or []),
            movie_ids=[int(x) for x in (data.get("movie_ids") or [])],
            movie_slugs=list(data.get("movie_slugs") or []),
            series_ids=[int(x) for x in (data.get("series_ids") or [])],
            series_slugs=list(data.get("series_slugs") or []),
            season_ids=[int(x) for x in (data.get("season_ids") or [])],
            episode_ids=[int(x) for x in (data.get("episode_ids") or [])],
            media_asset_ids=list(data.get("media_asset_ids") or []),
            package_ids=list(data.get("package_ids") or []),
            artwork_files=list(data.get("artwork_files") or []),
            media_files=list(data.get("media_files") or []),
            watch_progress_ids=[int(x) for x in (data.get("watch_progress_ids") or [])],
            collection_ids=[int(x) for x in (data.get("collection_ids") or [])],
            collection_slugs=list(data.get("collection_slugs") or []),
        )


def load_ownership(settings: Settings) -> DemoOwnership:
    path = ownership_path(settings)
    if not path.is_file():
        return DemoOwnership()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DemoOwnership()
    if not isinstance(data, dict):
        return DemoOwnership()
    return DemoOwnership.from_dict(data)


def save_ownership(settings: Settings, ownership: DemoOwnership) -> Path:
    path = ownership_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ownership.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)
    return path


def clear_ownership_file(settings: Settings) -> None:
    path = ownership_path(settings)
    if path.is_file():
        path.unlink()
