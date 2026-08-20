"""Compose capacity + workload + gates into one offline lab report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.branch_cache.ops.capacity_planner import (
    CapacityPlanInput,
    RenditionSpec,
    plan_branch_cache_capacity,
)
from app.services.branch_cache.ops.metrics_export import render_prometheus_text, snapshot_for_export
from app.services.branch_cache.ops.node_health import NodeHealthInput, evaluate_branch_node_health
from app.services.branch_cache.ops.pilot_gates import GateThresholds, evaluate_pilot_gates
from app.services.branch_cache.ops.workload_sim import run_workload_simulation


def run_phase5_lab_report(
    *,
    cache_root: Path,
    origin_root: Path,
    settings: Settings,
    public_key_pem: str,
    thresholds: GateThresholds | None = None,
) -> dict[str, Any]:
    """Full Phase 5 offline lab report. Never sets live_pilot_ready=true."""
    plan = plan_branch_cache_capacity(
        CapacityPlanInput(
            renditions=[
                RenditionSpec("240p", 400_000),
                RenditionSpec("480p", 1_400_000),
                RenditionSpec("720p", 2_800_000),
            ],
            peak_concurrent_viewers=100,
            working_set_titles=20,
            avg_title_duration_hours=1.0,
            retention_hours=24,
            replication_factor=1,
            headroom_percent=20,
            expected_hit_ratio=0.7,
            min_free_bytes=1_000_000_000,
            origin_egress_cap_bps=2_000_000_000,
        )
    )
    workload = run_workload_simulation(
        cache_root=cache_root,
        origin_root=origin_root,
        settings=settings,
        public_key_pem=public_key_pem,
    )
    gates = evaluate_pilot_gates(
        workload=workload,
        capacity=plan.as_dict(),
        central_playback_preserved=True,
        thresholds=thresholds,
    )
    health = evaluate_branch_node_health(
        NodeHealthInput(
            public_key_pem=public_key_pem,
            cache_root=cache_root,
            protocol_version="1.0",
            draining=False,
            origin_adapter_mode="local_dir",
            disk_total_bytes=plan.recommended_disk_bytes,
            disk_used_bytes=int(workload.get("cache", {}).get("used_bytes") or 0),
            min_free_bytes=plan.min_free_bytes,
            has_private_signing_key=False,
            has_portal_or_sas_credentials=False,
        ),
        settings=settings,
    )
    metrics_snap = snapshot_for_export(const_labels={"node_role": "branch_lab", "env": "test"})
    return {
        "phase": 5,
        "label": "hybrid_cdn_phase5_lab_report",
        "dependency_order": ["#81", "#82", "#83", "#84", "phase5"],
        "capacity": plan.as_dict(),
        "workload": {
            "totals": workload.get("totals"),
            "phases": workload.get("phases"),
            "live_network": False,
        },
        "gates": gates,
        "node_health": health,
        "metrics_export": {
            "endpoint_enabled": False,
            "snapshot": metrics_snap,
            "prometheus_text_bytes": len(render_prometheus_text(metrics_snap).encode("utf-8")),
        },
        "live_pilot_ready": False,
        "requires_human_approval": True,
        "requires_staging_evidence": True,
        "client_redirect_active": False,
    }
