"""CLI entry: python -m app.workers.media_processing

Also supports Docker HEALTHCHECK:
  python -m app.workers.media_processing --healthcheck
"""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings
from app.services.media_processing.worker import run_forever, worker_startup_health_ok


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [media-processing] %(message)s",
        stream=sys.stdout,
    )


def run_healthcheck() -> int:
    """Exit 0 when worker is healthy, 1 when unhealthy (for Docker HEALTHCHECK)."""
    get_settings.cache_clear()
    settings = get_settings()
    from app.services.media_processing.mount_health import (
        inspect_media_mount_health,
        log_media_mount_health,
    )

    health = inspect_media_mount_health(settings)
    log_media_mount_health(health)
    if not worker_startup_health_ok(settings):
        if health.ok:
            logging.getLogger(__name__).error(
                "Media processing worker unhealthy: required ffmpeg/ffprobe binary missing"
            )
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
