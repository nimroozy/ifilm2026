"""CLI entrypoint: python -m app.workers.publishing

Also supports Docker HEALTHCHECK:
  python -m app.workers.publishing --healthcheck
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from types import FrameType

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal, get_engine
from app.services.publishing.worker import claim_due_entity, run_due_batch, run_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("publishing-worker")

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Received signal %s; shutting down", signum)
    _shutdown = True


def _load_runtime_env_file() -> None:
    """Load /run/ifilm/runtime.env into the process when present.

    Production containers keep DATABASE_URL / REDIS_URL in this file (written by
    the entrypoint). Docker HEALTHCHECK starts a fresh process without that
    environment unless compose sources the file or we load it here.
    Never logs secret values.
    """
    path = "/run/ifilm/runtime.env"
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return
    import os

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")


def _required_dependencies_ok() -> None:
    """Raise if worker process cannot load required runtime dependencies."""
    # Import-time / settings failures surface as unhealthy without leaking secrets.
    _load_runtime_env_file()
    get_settings.cache_clear()
    settings = get_settings()
    if not (settings.database_url or "").strip():
        raise RuntimeError("DATABASE_URL is not configured")
    # Touch modules the consumer needs so missing deps fail the probe.
    from app.models.content import Episode, Movie, Season, Series  # noqa: F401
    from app.services.publishing.readiness import assess_readiness  # noqa: F401
    from app.services.publishing.workflow import transition  # noqa: F401


def _database_ok(db: Session) -> None:
    db.execute(text("SELECT 1"))


def _queue_consumer_ok(db: Session) -> None:
    """Ensure the scheduled-publish claim path can initialize (no work required)."""
    # claim_due_entity runs the same FOR UPDATE queries the loop uses; None is healthy.
    claim_due_entity(db)


def run_healthcheck() -> int:
    """Exit 0 when the publishing worker is ready; 1 when unhealthy.

    Verifies dependency load, database connectivity, and queue-consumer init.
    Publishing workers do not expose HTTP — do not inherit the API :8000 probe.
    Never logs secret values.
    """
    db: Session | None = None
    try:
        _required_dependencies_ok()
        get_engine()
        db = SessionLocal()
        _database_ok(db)
        _queue_consumer_ok(db)
    except Exception:
        logger.exception("Publishing worker healthcheck failed")
        return 1
    finally:
        if db is not None:
            db.close()
    return 0


def main(argv: list[str] | None = None) -> None:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] in {"--healthcheck", "healthcheck"}:
        raise SystemExit(run_healthcheck())

    parser = argparse.ArgumentParser(description="iFilm scheduled publishing worker")
    parser.add_argument("--once", action="store_true", help="Process one claim cycle and exit")
    parser.add_argument("--batch", type=int, default=0, help="Process up to N due items and exit")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between polls")
    args = parser.parse_args(args_list)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Ensure SessionLocal is bound before creating sessions.
    get_engine()

    if args.batch > 0:
        db = SessionLocal()
        try:
            counts = run_due_batch(db, limit=args.batch)
            logger.info("Batch complete: %s", counts)
        finally:
            db.close()
        return

    if args.once:
        db = SessionLocal()
        try:
            did = run_once(db)
            logger.info("Once complete: processed=%s", did)
        finally:
            db.close()
        return

    logger.info("Publishing worker started (poll=%ss)", args.poll_interval)
    while not _shutdown:
        db = SessionLocal()
        try:
            run_due_batch(db, limit=20)
        except Exception:
            logger.exception("Publishing worker iteration failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(args.poll_interval)
    logger.info("Publishing worker stopped")


if __name__ == "__main__":
    main()
