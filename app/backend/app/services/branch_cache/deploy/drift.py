"""Idempotence and drift detection for Phase 9 rendered artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.branch_cache.deploy.inventory import StagingInventoryV1, is_unreviewed_placeholder
from app.services.branch_cache.deploy.render import MANIFEST_NAME, render_all


def _dir_fingerprint(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(root)).replace("\\", "/")
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def render_twice_identical(inventory: StagingInventoryV1, tmp_root: Path) -> dict[str, Any]:
    a = tmp_root / "a"
    b = tmp_root / "b"
    man_a = render_all(inventory, a)
    man_b = render_all(inventory, b)
    fp_a = _dir_fingerprint(a)
    fp_b = _dir_fingerprint(b)
    identical = fp_a == fp_b and man_a["manifest_sha256"] == man_b["manifest_sha256"]
    return {
        "identical": identical,
        "manifest_sha256_a": man_a["manifest_sha256"],
        "manifest_sha256_b": man_b["manifest_sha256"],
        "files_a": fp_a,
        "files_b": fp_b,
    }


def detect_drift(
    *,
    expected_manifest: dict[str, Any],
    current_dir: Path,
    unexpected_image_digest: str | None = None,
    unexpected_cert_fingerprint: str | None = None,
    unexpected_firewall_hash: str | None = None,
) -> dict[str, Any]:
    """Compare rendered tree + optional unexpected mutations."""
    reasons: list[str] = []
    current_manifest_path = current_dir / MANIFEST_NAME
    if not current_manifest_path.is_file():
        reasons.append("manifest_missing")
        return {
            "drift": True,
            "reasons": reasons,
            "incomplete_inputs": True,
            "plan_success": False,
            "apply_allowed": False,
            "live_pilot_ready": False,
            "client_redirect_active": False,
        }

    current = json.loads(current_manifest_path.read_text(encoding="utf-8"))
    if current.get("manifest_sha256") != expected_manifest.get("manifest_sha256"):
        reasons.append("manifest_hash_mismatch")
    if current.get("image_digest") != expected_manifest.get("image_digest"):
        reasons.append("image_digest_drift")
    if unexpected_image_digest and unexpected_image_digest != expected_manifest.get("image_digest"):
        reasons.append("unexpected_image_change")
    if unexpected_cert_fingerprint:
        reasons.append("unexpected_cert_change")
    if unexpected_firewall_hash:
        expected_fw = (expected_manifest.get("artifact_sha256") or {}).get(
            "firewall-egress.plan.md"
        )
        if unexpected_firewall_hash != expected_fw:
            reasons.append("unexpected_firewall_change")

    sig = (current.get("signing") or {}).get("signature", "")
    pub_fp = (current.get("signing") or {}).get("public_key_fingerprint_sha256", "")
    incomplete_inputs = (
        is_unreviewed_placeholder(str(sig))
        or is_unreviewed_placeholder(str(pub_fp))
        or str(sig).upper().startswith("REQUIRED:")
    )

    drift = bool(reasons)
    return {
        "drift": drift,
        "reasons": reasons,
        "incomplete_inputs": incomplete_inputs,
        "plan_success": (not drift) and (not incomplete_inputs),
        "apply_allowed": False,
        "live_pilot_ready": False,
        "client_redirect_active": False,
    }
