"""Canonical media lifecycle states (logical overlay on existing columns).

See docs/media/PIPELINE.md — single source of truth for Train T0.
"""

from __future__ import annotations

from typing import Any

# Documented canonical states — do not invent parallel status columns in T0.
CANONICAL_STATES = (
    "uploaded",
    "probing",
    "ready",
    "encoding",
    "packaged",
    "published",
    "failed",
)

_ACTIVE_JOB = frozenset({"queued", "running", "retry_wait"})
_ENCODE_PACKAGE = frozenset({"pending", "encoding", "validating", "promoting"})


def canonical_media_state(
    asset: Any,
    *,
    active_job_type: str | None = None,
    active_job_status: str | None = None,
    active_package_status: str | None = None,
    has_active_completed_package: bool = False,
    catalog_published: bool = False,
) -> str:
    """Derive a canonical lifecycle state for diagnostics.

    Prefer passing job/package context from the caller when available.
    """
    upload_status = getattr(asset, "upload_status", None) or ""
    processing_status = getattr(asset, "processing_status", None) or "none"
    probed_at = getattr(asset, "probed_at", None)

    if upload_status == "failed" or processing_status == "failed":
        return "failed"
    if active_job_status == "failed" or active_package_status == "failed":
        return "failed"

    if upload_status not in {"completed", "stored"}:
        # Still uploading / pending — closest canonical bucket is uploaded once
        # the row exists; treat non-complete as uploaded until failed.
        if upload_status in {"pending", "uploading", "finalizing"}:
            return "uploaded"
        return "failed" if upload_status else "uploaded"

    if has_active_completed_package:
        return "published" if catalog_published else "packaged"

    if active_job_type == "encode_hls" and active_job_status in _ACTIVE_JOB:
        return "encoding"
    if active_package_status in _ENCODE_PACKAGE:
        return "encoding"
    if processing_status in {"queued", "processing", "retry_wait"} and probed_at is not None:
        return "encoding"

    if active_job_type == "probe" and active_job_status in _ACTIVE_JOB:
        return "probing"
    if processing_status in {"queued", "processing", "retry_wait"} and probed_at is None:
        return "probing"

    if probed_at is not None or processing_status in {"completed", "requires_repackage", "ready"}:
        return "ready"

    return "uploaded"
