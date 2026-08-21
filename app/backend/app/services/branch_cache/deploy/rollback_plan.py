"""Deterministic rollback / removal PLAN (Phase 9).

Limited to the candidate service and validated staging cache root.
Destructive commands are never executed by this package or its tests.
"""

from __future__ import annotations

from typing import Any

from app.services.branch_cache.deploy.inventory import StagingInventoryV1

_FORBIDDEN_DELETE_ROOTS = frozenset(
    {"/", "/etc", "/var", "/usr", "/home", "/root", "/tmp", "/boot", "/dev", "/proc", "/sys"}
)


def validate_cache_root_for_plan(path: str) -> bool:
    text = (path or "").rstrip("/")
    if not text.startswith("/"):
        return False
    if text in _FORBIDDEN_DELETE_ROOTS:
        return False
    # Must look dedicated.
    return "ifilm" in text.lower() or "branch" in text.lower()


def render_rollback_plan(inventory: StagingInventoryV1) -> dict[str, Any]:
    cache_ok = validate_cache_root_for_plan(inventory.cache.device_or_path)
    return {
        "schema_version": "ifilm.branch_node.rollback_plan.v1",
        "node_id": inventory.node_id,
        "scope": "candidate_service_and_dedicated_cache_root_only",
        "cache_root": inventory.cache.device_or_path,
        "cache_root_validated": cache_ok,
        "steps": [
            {"id": "drain", "action": "graceful_drain", "executes": False},
            {"id": "stop", "action": "stop_candidate_service", "executes": False},
            {"id": "unmount_certs", "action": "unmount_readonly_cert_binds", "executes": False},
            {"id": "unmount_cache", "action": "unmount_dedicated_cache_volume", "executes": False},
            {
                "id": "restore_prior_digest",
                "action": "restore_prior_image_digest_and_config",
                "executes": False,
                "requires": "recorded_prior_digest",
            },
            {
                "id": "preserve_forensics",
                "action": "copy_redacted_evidence_bundle",
                "executes": False,
            },
            {
                "id": "optional_purge_cache",
                "action": "delete_only_validated_staging_cache_root",
                "executes": False,
                "forbidden_if_unvalidated": True,
                "allowed_root_only_if": inventory.cache.device_or_path if cache_ok else None,
            },
        ],
        "never": [
            "rm -rf /",
            "delete outside validated staging cache root",
            "touch production compose",
            "mutate installer",
            "disable unrelated services",
        ],
        "live_pilot_ready": False,
        "client_redirect_active": False,
        "apply_allowed": False,
        "tests_must_not_execute_destructive_commands": True,
    }
