"""Offline canary / shadow plan (Phase 9).

0% client redirects. Synthetic-only. Human approval required per escalation.
"""

from __future__ import annotations

from typing import Any

from app.services.branch_cache.deploy.inventory import StagingInventoryV1


def render_canary_plan(inventory: StagingInventoryV1) -> dict[str, Any]:
    return {
        "schema_version": "ifilm.branch_node.canary_shadow_plan.v1",
        "node_id": inventory.node_id,
        "environment": inventory.environment,
        "client_redirect_percent": 0,
        "client_redirect_active": False,
        "live_pilot_ready": False,
        "request_mode": "synthetic_only",
        "bounded_object_allowlist": [
            "master.m3u8",
            "720p/seg_000.ts",
        ],
        "max_bytes_total": min(64 * 1024 * 1024, inventory.capacity.max_object_bytes * 4),
        "max_duration_seconds": 300,
        "cache_watermark_protections": {
            "high_watermark_bytes": inventory.cache.high_watermark_bytes,
            "low_watermark_bytes": inventory.cache.low_watermark_bytes,
            "min_free_bytes": inventory.cache.min_free_bytes,
            "refuse_fill_when_low": True,
        },
        "origin_budget": {
            "max_concurrent_fills": inventory.capacity.max_concurrent_fills,
            "max_origin_bytes": 128 * 1024 * 1024,
            "max_origin_errors": 5,
        },
        "slo_gates": {
            "max_fill_latency_ms_p95": 2000,
            "max_error_rate": 0.01,
            "min_cache_hit_ratio_after_warm": 0.5,
        },
        "automatic_drain_criteria": [
            "origin_error_budget_exceeded",
            "disk_below_min_free",
            "certificate_expiry_window_breached",
            "dns_pin_mismatch",
            "operator_abort",
        ],
        "evidence_bundle": {
            "redact_secrets": True,
            "redact_identifiers": True,
            "include_preflight_report": True,
            "include_render_manifest_hash": True,
            "forbid_pem_bodies": True,
        },
        "escalation": {
            "human_approval_required_before_each_step": True,
            "steps": [
                "synthetic_shadow",
                "expanded_synthetic",
                "STOP_live_activation_out_of_scope",
            ],
        },
        "apply_allowed": False,
    }
