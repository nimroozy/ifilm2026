"""CLI entry: python -m app.workers.remote_media_import

Docker HEALTHCHECK:
  python -m app.workers.remote_media_import --healthcheck
"""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings
from app.services.media_remote_import_worker import (
    inspect_remote_import_mounts,
    run_forever,
    worker_startup_health_ok,
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [remote-media-import] %(message)s",
        stream=sys.stdout,
    )


def run_healthcheck() -> int:
    """Exit 0 when worker is healthy, 1 when unhealthy (for Docker HEALTHCHECK)."""
    get_settings.cache_clear()
    settings = get_settings()
    mounts = inspect_remote_import_mounts(settings)
    logging.getLogger(__name__).info(
        "remote_import_healthcheck enable_remote=%s enable_uploads=%s mounts=%s",
        bool(settings.enable_remote_media_import),
        bool(settings.enable_uploads),
        mounts,
    )
    if not worker_startup_health_ok(settings):
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    _configure_logging()
    if args and args[0] in {"--healthcheck", "healthcheck"}:
        raise SystemExit(run_healthcheck())
    settings = get_settings()
    run_forever(settings=settings)


if __name__ == "__main__":
    main()
