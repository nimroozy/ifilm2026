"""CLI entry: python -m app.workers.cdn_provisioning

Privileged, opt-in worker that executes queued CDN provisioning runs over SSH.
Never runs inside the web process. Supports Docker HEALTHCHECK:
  python -m app.workers.cdn_provisioning --healthcheck
"""

from __future__ import annotations

import logging
import signal
import socket
import sys
import time
from datetime import UTC, datetime, timedelta
from types import FrameType

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging_filters import install_token_redaction_logging
from app.models.cdn_management import CDNProvisionRun, ManagedCDNNode
from app.services import cdn_management as mgmt
from app.services.cdn_provisioner import ProvisionExecutor

logger = logging.getLogger("app.workers.cdn_provisioning")
_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Signal %s received; finishing current run then exiting", signum)
    _shutdown = True


def default_worker_id(settings: Settings) -> str:
    configured = (settings.cdn_provisioning_worker_id or "").strip()
    return configured or f"cdn-{socket.gethostname()}"[:128]


def worker_startup_ok(settings: Settings) -> tuple[bool, str]:
    if not settings.enable_cdn_provisioning:
        return False, "ENABLE_CDN_PROVISIONING is false"
    if not (settings.integration_secrets_key or "").strip():
        return False, "INTEGRATION_SECRETS_KEY is not configured"
    if not (settings.cdn_central_base_url or "").strip().startswith("https://"):
        return False, "CDN_CENTRAL_BASE_URL must be an https URL"
    try:
        import paramiko  # noqa: F401
    except ImportError:
        return False, "paramiko is not installed"
    return True, "ok"


def recover_stale_runs(db: Session, *, settings: Settings) -> int:
    """Mark runs that a dead worker left in ``running`` as failed so they can be retried."""
    cutoff = datetime.now(UTC) - timedelta(seconds=int(settings.cdn_provisioning_stale_after_seconds))
    stale = (
        db.query(CDNProvisionRun)
        .filter(CDNProvisionRun.status == mgmt.PROVISION_RUNNING, CDNProvisionRun.claimed_at < cutoff)
        .all()
    )
    for run in stale:
        run.status = mgmt.PROVISION_FAILED
        run.error_code = "worker_lost"
        run.finished_at = datetime.now(UTC)
        run.log_text = (run.log_text or "") + "\nFAILED: worker lost (stale claim recovered)\n"
        node = db.get(ManagedCDNNode, run.node_id)
        if node is not None:
            node.provision_status = mgmt.PROVISION_FAILED
            node.last_error = f"{run.step or 'unknown'}: worker_lost"
            node.last_error_at = datetime.now(UTC)
            db.add(node)
        db.add(run)
    if stale:
        db.commit()
    return len(stale)


def claim_next_run(db: Session, *, worker_id: str) -> CDNProvisionRun | None:
    """Atomically claim one queued run (SKIP LOCKED on PostgreSQL)."""
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        row = db.execute(
            text(
                """
                SELECT id FROM cdn_provision_runs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
        ).first()
        run = db.get(CDNProvisionRun, row[0]) if row else None
    else:
        run = (
            db.query(CDNProvisionRun)
            .filter(CDNProvisionRun.status == mgmt.PROVISION_QUEUED)
            .order_by(CDNProvisionRun.created_at.asc())
            .with_for_update()
            .first()
        )
    if run is None:
        return None
    run.status = mgmt.PROVISION_RUNNING
    run.claimed_by = worker_id
    run.claimed_at = datetime.now(UTC)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_once(db: Session, *, executor: ProvisionExecutor, settings: Settings, worker_id: str) -> bool:
    recover_stale_runs(db, settings=settings)
    run = claim_next_run(db, worker_id=worker_id)
    if run is None:
        return False
    logger.info("cdn_provision_claimed run_id=%s node_id=%s action=%s", run.id, run.node_id, run.action)
    executor.execute(db, run, worker_id=worker_id)
    return True


def run_forever(*, settings: Settings | None = None) -> None:
    global _shutdown
    _shutdown = False
    settings = settings or get_settings()
    ok, reason = worker_startup_ok(settings)
    if not ok:
        logger.error("CDN provisioning worker refusing to start: %s", reason)
        raise SystemExit(1)
    from app.db.session import SessionLocal, get_engine

    install_token_redaction_logging()
    worker_id = default_worker_id(settings)
    executor = ProvisionExecutor(settings=settings)
    logger.info("CDN provisioning worker starting id=%s", worker_id)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    get_engine()
    while not _shutdown:
        db = SessionLocal()
        try:
            processed = run_once(db, executor=executor, settings=settings, worker_id=worker_id)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            processed = False
        finally:
            db.close()
        if not processed:
            time.sleep(float(settings.cdn_provisioning_poll_seconds))


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [cdn-provisioning] %(message)s",
        stream=sys.stdout,
    )


def run_healthcheck() -> int:
    get_settings.cache_clear()
    ok, reason = worker_startup_ok(get_settings())
    if not ok:
        logging.getLogger(__name__).error("CDN provisioning worker unhealthy: %s", reason)
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    _configure_logging()
    if args and args[0] in {"--healthcheck", "healthcheck"}:
        raise SystemExit(run_healthcheck())
    run_forever(settings=get_settings())


if __name__ == "__main__":
    main()
