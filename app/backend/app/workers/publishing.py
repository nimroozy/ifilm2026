"""CLI entrypoint: python -m app.workers.publishing"""

from __future__ import annotations

import argparse
import logging
import signal
import time
from types import FrameType

from app.db.session import SessionLocal
from app.services.publishing.worker import run_due_batch, run_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("publishing-worker")

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Received signal %s; shutting down", signum)
    _shutdown = True


def main() -> None:
    parser = argparse.ArgumentParser(description="iFilm scheduled publishing worker")
    parser.add_argument("--once", action="store_true", help="Process one claim cycle and exit")
    parser.add_argument("--batch", type=int, default=0, help="Process up to N due items and exit")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between polls")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

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
