"""Phase 5 offline pilot readiness / capacity / SLO lab tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.services.branch_cache.ops.capacity_planner import (
    CapacityPlanError,
    CapacityPlanInput,
    RenditionSpec,
    checked_mul,
    plan_branch_cache_capacity,
)
from app.services.branch_cache.ops.lab_report import run_phase5_lab_report
from app.services.branch_cache.ops.metrics_export import (
    MetricsExportError,
    render_prometheus_text,
    snapshot_for_export,
)
from app.services.branch_cache.ops.node_health import NodeHealthInput, evaluate_branch_node_health
from app.services.branch_cache.ops.pilot_gates import GateThresholds, evaluate_pilot_gates
from app.services.branch_cache.ops.workload_sim import (
    build_deterministic_trace,
    run_workload_simulation,
)
from app.services.object_storage.status import safe_storage_status
from app.services.object_storage.validation import collect_object_storage_errors
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _pem_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv, pub


def _settings(**kwargs) -> Settings:
    priv, pub = _pem_pair()
    base = dict(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_cdn_sync=False,
        enable_branch_cache_control_plane=True,
        enable_edge_grant_issue=True,
        enable_branch_cache_data_plane_sim=True,
        enable_branch_cache_pull_through=True,
        enable_branch_cache_local_serve=True,
        enable_branch_cache_pilot_lab=True,
        edge_grant_private_key_pem=priv,
        edge_grant_public_key_pem=pub,
        edge_grant_key_id="eg1",
        edge_grant_ttl_seconds=120,
        _env_file=None,
    )
    base.update(kwargs)
    return Settings(**base)


def test_phase5_flag_default_off():
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        _env_file=None,
    )
    assert settings.enable_branch_cache_pilot_lab is False
    status = safe_storage_status(settings)
    assert status["policy"]["live_pilot_requires_human_and_staging"] is True
    assert status["roles"]["branch_cache"]["client_redirect_active"] is False


def test_prod_rejects_pilot_lab_flag():
    settings = _settings(app_env="production", enable_branch_cache_pilot_lab=True)
    # Also need data plane sim false to isolate, or both rejected
    settings = _settings(
        app_env="production",
        enable_branch_cache_pilot_lab=True,
        enable_branch_cache_data_plane_sim=False,
        enable_branch_cache_pull_through=False,
        enable_branch_cache_local_serve=False,
    )
    errors = collect_object_storage_errors(settings)
    assert any("PILOT_LAB" in e for e in errors)


def test_capacity_planner_happy_path():
    plan = plan_branch_cache_capacity(
        CapacityPlanInput(
            renditions=[
                RenditionSpec("720p", 2_800_000),
                RenditionSpec("1080p", 5_000_000),
            ],
            peak_concurrent_viewers=100,
            working_set_titles=20,
            avg_title_duration_hours=2.0,
            retention_hours=48,
            headroom_percent=25,
            expected_hit_ratio=0.8,
            min_free_bytes=1_000_000_000,
            origin_egress_cap_bps=5_000_000_000,
        )
    )
    assert plan.safe is True
    assert plan.recommended_disk_bytes > plan.working_set_bytes
    assert plan.high_watermark_bytes > plan.low_watermark_bytes
    assert plan.as_dict()["live_pilot_claim"] is False


def test_capacity_planner_rejects_unsafe_and_overflow():
    with pytest.raises(CapacityPlanError):
        plan_branch_cache_capacity(
            CapacityPlanInput(
                renditions=[],
                peak_concurrent_viewers=1,
                working_set_titles=1,
                avg_title_duration_hours=1.0,
                retention_hours=24,
            )
        )
    with pytest.raises(CapacityPlanError) as exc:
        plan_branch_cache_capacity(
            CapacityPlanInput(
                renditions=[RenditionSpec("x", 1)],
                peak_concurrent_viewers=1,
                working_set_titles=1,
                avg_title_duration_hours=1.0,
                retention_hours=24,
                high_watermark_ratio=0.5,
                low_watermark_ratio=0.9,
            )
        )
    assert exc.value.code == "watermarks"
    with pytest.raises(CapacityPlanError) as exc2:
        checked_mul(10**18, 10**18)
    assert exc2.value.code == "overflow"

    # Cap exceeded → unsafe plan (not necessarily raise)
    plan = plan_branch_cache_capacity(
        CapacityPlanInput(
            renditions=[RenditionSpec("1080p", 5_000_000)],
            peak_concurrent_viewers=10_000,
            working_set_titles=10,
            avg_title_duration_hours=2.0,
            retention_hours=24,
            expected_hit_ratio=0.1,
            origin_egress_cap_bps=1_000_000,  # tiny
        )
    )
    assert plan.safe is False
    assert "expected_origin_bps_exceeds_cap" in plan.rejection_reasons


def test_capacity_rejects_nan_inf():
    with pytest.raises(CapacityPlanError):
        plan_branch_cache_capacity(
            CapacityPlanInput(
                renditions=[RenditionSpec("720p", 1_000_000)],
                peak_concurrent_viewers=10,
                working_set_titles=5,
                avg_title_duration_hours=float("nan"),
                retention_hours=24,
            )
        )


def test_workload_simulation_deterministic(tmp_path: Path):
    settings = _settings()
    t1 = build_deterministic_trace()
    t2 = build_deterministic_trace()
    assert [(e.phase, e.relative_path, e.session_id) for e in t1] == [
        (e.phase, e.relative_path, e.session_id) for e in t2
    ]
    a = run_workload_simulation(
        cache_root=tmp_path / "c1",
        origin_root=tmp_path / "o1",
        settings=settings,
        public_key_pem=settings.edge_grant_public_key_pem,
    )
    b = run_workload_simulation(
        cache_root=tmp_path / "c2",
        origin_root=tmp_path / "o2",
        settings=settings,
        public_key_pem=settings.edge_grant_public_key_pem,
    )
    assert a["totals"]["requests"] == b["totals"]["requests"]
    assert a["totals"]["hit_ratio"] == b["totals"]["hit_ratio"]
    assert a["live_network"] is False
    assert a["phases"]["origin_outage"]["fallbacks"] >= 1
    assert a["phases"]["recovery"]["requests"] >= 1


def test_pilot_gates_pass_and_fail():
    good = {
        "totals": {
            "requests": 100,
            "hits": 60,
            "misses": 20,
            "fallbacks": 10,
            "auth_fails": 0,
            "hit_ratio": 0.75,
            "origin_bytes": 1000,
            "served_bytes": 5000,
            "approx_bytes_saved": 4000,
            "p95_fill_latency_ms": 50,
            "evicted": 2,
            "partial_files_remaining": 0,
        },
        "cache": {"used_bytes": 1000, "high_watermark_bytes": 10_000},
    }
    report = evaluate_pilot_gates(
        workload=good, capacity={"safe": True}, central_playback_preserved=True
    )
    assert report["lab_gates_passed"] is True
    assert report["classification"] == "lab_ready"
    assert report["live_pilot_ready"] is False
    assert report["requires_human_approval"] is True

    bad = {
        "totals": {
            "requests": 100,
            "hits": 5,
            "misses": 50,
            "fallbacks": 80,
            "auth_fails": 20,
            "hit_ratio": 0.05,
            "origin_bytes": 9000,
            "served_bytes": 1000,
            "approx_bytes_saved": 0,
            "p95_fill_latency_ms": 9000,
            "evicted": 500,
            "partial_files_remaining": 3,
        },
        "cache": {"used_bytes": 9900, "high_watermark_bytes": 10_000},
    }
    fail = evaluate_pilot_gates(
        workload=bad,
        capacity={"safe": False},
        central_playback_preserved=False,
        thresholds=GateThresholds(min_hit_ratio=0.5, max_fallback_rate=0.2),
    )
    assert fail["lab_gates_passed"] is False
    assert fail["live_pilot_ready"] is False
    assert "hit_ratio_below_threshold" in fail["pass_fail_reasons"]


def test_metrics_export_cardinality_and_redaction():
    snap = snapshot_for_export(const_labels={"node_role": "branch_lab", "env": "test"})
    assert snap["endpoint_enabled"] is False
    text = render_prometheus_text(snap)
    assert "endpoint_enabled=" in text
    assert "PRIVATE" not in text
    with pytest.raises(MetricsExportError):
        snapshot_for_export(const_labels={"token": "abc"})
    with pytest.raises(MetricsExportError):
        snapshot_for_export(const_labels={"subscriber_id": "1"})
    with pytest.raises(MetricsExportError):
        snapshot_for_export(const_labels={"raw_url": "http://x"})


def test_node_health_forbids_secrets_and_checks_root(tmp_path: Path):
    _, pub = _pem_pair()
    root = tmp_path / "cache-root"
    root.mkdir()
    ok = evaluate_branch_node_health(
        NodeHealthInput(
            public_key_pem=pub,
            cache_root=root,
            protocol_version="1.0",
            origin_adapter_mode="local_dir",
            disk_total_bytes=10_000_000_000,
            disk_used_bytes=1_000_000_000,
            min_free_bytes=1_000_000_000,
        )
    )
    assert ok["ready"] is True
    assert ok["live_serving_allowed"] is False

    bad = evaluate_branch_node_health(
        NodeHealthInput(
            public_key_pem="",
            cache_root=Path("/"),
            protocol_version="2",
            has_private_signing_key=True,
            has_portal_or_sas_credentials=True,
            origin_adapter_mode="live_http",
            clock_skew_seconds=999,
        )
    )
    assert bad["ready"] is False
    reasons = bad["fail_reasons"]
    assert "private_key_forbidden" in reasons
    assert "portal_sas_forbidden" in reasons


def test_lab_report_never_claims_live_pilot(tmp_path: Path):
    settings = _settings()
    report = run_phase5_lab_report(
        cache_root=tmp_path / "cache",
        origin_root=tmp_path / "origin",
        settings=settings,
        public_key_pem=settings.edge_grant_public_key_pem,
    )
    assert report["live_pilot_ready"] is False
    assert report["requires_human_approval"] is True
    assert report["requires_staging_evidence"] is True
    assert report["client_redirect_active"] is False
    assert report["gates"]["live_pilot_ready"] is False
    assert "capacity" in report and "workload" in report
    assert report["metrics_export"]["endpoint_enabled"] is False


def test_flags_off_preserve_central_playback_marker():
    """Phase 5 does not alter central stream modules; gate requires preservation flag."""
    report = evaluate_pilot_gates(
        workload={
            "totals": {
                "requests": 10,
                "hits": 8,
                "misses": 2,
                "fallbacks": 0,
                "auth_fails": 0,
                "hit_ratio": 0.8,
                "origin_bytes": 10,
                "served_bytes": 100,
                "approx_bytes_saved": 90,
                "p95_fill_latency_ms": 1,
                "evicted": 0,
                "partial_files_remaining": 0,
            },
            "cache": {"used_bytes": 1, "high_watermark_bytes": 100},
        },
        central_playback_preserved=True,
    )
    gate = next(g for g in report["gates"] if g["name"] == "central_playback_preserved")
    assert gate["passed"] is True
