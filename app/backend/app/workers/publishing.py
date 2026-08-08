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

from app.db.session import SessionLocal, get_engine
from app.services.publishing.worker import run_due_batch, run_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("publishing-worker")

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Received signal %s; shutting down", signum)
    _shutdown = True


def run_healthcheck() -> int:
    """Exit 0 when the worker can reach the database; 1 otherwise.

    Publishing workers do not expose HTTP. Do not inherit the API curl :8000 probe.
    """
    try:
        get_engine()
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        logger.exception("Publishing worker healthcheck failed")
        return 1
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
