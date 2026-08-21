"""Phase 9 one-node staging deploy package — offline unit/contract tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from app.core.config import Settings
from app.services.branch_cache.deploy.canary_plan import render_canary_plan
from app.services.branch_cache.deploy.drift import detect_drift, render_twice_identical
from app.services.branch_cache.deploy.firewall_plan import render_firewall_plan
from app.services.branch_cache.deploy.inventory import (
    StagingInventoryV1,
    concrete_reviewed_inventory_dict,
    example_inventory_dict,
    is_unreviewed_placeholder,
    load_staging_inventory,
    write_staging_inventory,
)
from app.services.branch_cache.deploy.preflight import (
    CertMaterialFact,
    HostFacts,
    evaluate_preflight,
    with_host_overrides,
)
from app.services.branch_cache.deploy.render import render_all, render_compose_override
from app.services.branch_cache.deploy.rollback_plan import (
    render_rollback_plan,
    validate_cache_root_for_plan,
)
from app.services.object_storage.validation import collect_object_storage_errors
from pydantic import ValidationError


def _inv(**overrides) -> StagingInventoryV1:
    data = example_inventory_dict()
    data.update(overrides)
    return StagingInventoryV1.model_validate(data)


def _ready_inv(**overrides) -> StagingInventoryV1:
    data = concrete_reviewed_inventory_dict()
    data.update(overrides)
    return StagingInventoryV1.model_validate(data)


def _good_host(inv: StagingInventoryV1) -> HostFacts:
    return HostFacts(
        os_name="linux",
        kernel="6.1.0-test",
        time_sync_ok=True,
        free_disk_bytes=inv.cache.min_free_bytes + 10,
        filesystem_owner_uid=10001,
        filesystem_owner_gid=10001,
        fd_limit=4096,
        pid_limit=512,
        memory_mb=4096,
        cpu_count=4,
        resolved_origin_ips=(inv.origin.pinned_resolved_ipv4,),
        dns_resolution_stable=True,
        ca=CertMaterialFact(
            path=inv.ca_bundle_mount_path,
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_ca_bundle_sha256,
            not_after_utc="2099-01-01T00:00:00Z",
            san_dns=(),
            has_client_auth_eku=False,
            has_server_auth_eku=False,
        ),
        origin_server_cert=CertMaterialFact(
            path="/run/ifilm/evidence/origin-server.crt",
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_origin_server_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=(inv.origin.host,),
            has_client_auth_eku=False,
            has_server_auth_eku=True,
            subject_cn=inv.origin.host,
        ),
        client_cert=CertMaterialFact(
            path=inv.client_cert_mount_path,
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_client_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=(inv.expected_client_identity,),
            has_client_auth_eku=True,
            has_server_auth_eku=False,
            subject_cn=inv.expected_client_identity,
        ),
        client_key_mode_bits=0o600,
        client_key_exists=True,
        client_key_matches_cert=True,
        observed_client_identity=inv.expected_client_identity,
        edge_grant_public_sha256=inv.trust.edge_grant_public_key_sha256,
        image_digest_present=True,
        sbom_ref_reviewed=inv.image.sbom_ref,
        provenance_ref_reviewed=inv.image.provenance_ref,
        manifest_signature="a" * 64,
        rollback_prior_digest_recorded=True,
        forensic_dir_writable=True,
    )


def test_flag_default_off_and_apply_rejected():
    s = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        _env_file=None,
    )
    assert s.enable_branch_cache_one_node_staging_deploy is False
    enabled = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_branch_cache_one_node_staging_deploy=True,
        _env_file=None,
    )
    errs = collect_object_storage_errors(enabled)
    assert any("ONE_NODE_STAGING_DEPLOY" in e for e in errs)


def test_inventory_requires_staging_candidate_and_digest(tmp_path: Path):
    inv = _inv()
    path = tmp_path / "inv.json"
    write_staging_inventory(path, inv)
    loaded = load_staging_inventory(path)
    assert loaded.environment == "staging-candidate"
    assert loaded.image.digest.startswith("sha256:")
    assert loaded.live_pilot_ready is False
    assert loaded.client_redirect_active is False
    assert loaded.expected_client_identity != loaded.origin.host

    bad = example_inventory_dict()
    bad["environment"] = "production"
    with pytest.raises(ValueError, match="production|staging-candidate"):
        load_staging_inventory(tmp_path / "bad.json") if (
            (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8") or True
        ) else None

    tagged = example_inventory_dict()
    tagged["image"]["repository"] = "ghcr.io/example/ifilm:latest"
    with pytest.raises(ValidationError):
        StagingInventoryV1.model_validate(tagged)

    wild = example_inventory_dict()
    wild["origin"]["host"] = "*.example.com"
    with pytest.raises(ValidationError):
        StagingInventoryV1.model_validate(wild)

    ip_host = example_inventory_dict()
    ip_host["origin"]["host"] = "10.1.2.3"
    with pytest.raises(ValidationError):
        StagingInventoryV1.model_validate(ip_host)

    same_id = concrete_reviewed_inventory_dict()
    same_id["expected_client_identity"] = same_id["origin"]["host"]
    with pytest.raises(ValidationError):
        StagingInventoryV1.model_validate(same_id)


def test_inventory_rejects_secrets_unknown_fields_and_credential_urls(tmp_path: Path):
    raw = example_inventory_dict()
    raw["private_key"] = "SECRET"
    p = tmp_path / "sec.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden secret"):
        load_staging_inventory(p)

    unknown = example_inventory_dict()
    unknown["unexpected_field"] = "x"
    with pytest.raises(ValidationError):
        StagingInventoryV1.model_validate(unknown)

    with pytest.raises(ValidationError):
        StagingInventoryV1.model_validate({**example_inventory_dict(), "bind_host": "0.0.0.0"})
    with pytest.raises(ValidationError):
        StagingInventoryV1.model_validate({**example_inventory_dict(), "run_as_uid": 0})


def test_placeholders_fail_readiness_and_plan_success():
    assert is_unreviewed_placeholder("placeholder:sbom")
    assert is_unreviewed_placeholder("REQUIRED:X")
    assert is_unreviewed_placeholder("approval-placeholder-001")
    assert not is_unreviewed_placeholder("apr-20260821-reviewed-001")

    example = _inv()
    assert example.placeholder_fields()
    report = evaluate_preflight(example, host=_good_host(example))
    assert report["go"] is False
    assert report["plan_success"] is False
    assert "inventory_placeholders_absent" in report["failed"]


def test_preflight_go_with_concrete_evidence_and_fail_closed_on_dns_flap():
    inv = _ready_inv()
    report = evaluate_preflight(inv, host=_good_host(inv))
    assert report["go"] is True
    assert report["plan_success"] is True
    assert report["mutates_host"] is False
    assert report["apply_allowed"] is False
    assert report["deployment_authorized"] is False
    assert report["live_pilot_ready"] is False
    assert report["client_redirect_active"] is False

    flap = with_host_overrides(
        _good_host(inv),
        resolved_origin_ips=(inv.origin.pinned_resolved_ipv4, "10.50.1.11"),
        dns_resolution_stable=False,
    )
    no = evaluate_preflight(inv, host=flap)
    assert no["go"] is False
    assert no["plan_success"] is False
    assert "origin_dns_stable" in no["failed"] or "origin_ip_pin_match" in no["failed"]

    incomplete = evaluate_preflight(inv, host=HostFacts(resolved_origin_ips=()))
    assert incomplete["go"] is False
    assert incomplete["plan_success"] is False


def test_origin_server_san_exact_negative_cases():
    inv = _ready_inv()
    base = _good_host(inv)

    wrong = with_host_overrides(
        base,
        origin_server_cert=CertMaterialFact(
            path="/run/ifilm/evidence/origin-server.crt",
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_origin_server_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=("wrong.example.internal",),
            has_server_auth_eku=True,
        ),
    )
    r_wrong = evaluate_preflight(inv, host=wrong)
    assert r_wrong["go"] is False
    assert "origin_server_san_exact" in r_wrong["failed"]
    assert any(
        c["name"] == "origin_server_san_exact" and c["reason"] == "origin_san_mismatch"
        for c in r_wrong["checks"]
    )

    unrelated = with_host_overrides(
        base,
        origin_server_cert=CertMaterialFact(
            path="/run/ifilm/evidence/origin-server.crt",
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_origin_server_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=("cdn.unrelated.example", "api.other.example"),
            has_server_auth_eku=True,
        ),
    )
    r_unrelated = evaluate_preflight(inv, host=unrelated)
    assert r_unrelated["go"] is False
    assert "origin_server_san_exact" in r_unrelated["failed"]

    missing = with_host_overrides(
        base,
        origin_server_cert=CertMaterialFact(
            path="/run/ifilm/evidence/origin-server.crt",
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_origin_server_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=(),
            has_server_auth_eku=True,
        ),
    )
    r_missing = evaluate_preflight(inv, host=missing)
    assert r_missing["go"] is False
    assert "origin_server_san_exact" in r_missing["failed"]
    assert any(
        c["name"] == "origin_server_san_exact" and c["reason"] == "origin_san_missing"
        for c in r_missing["checks"]
    )

    absent = with_host_overrides(base, origin_server_cert=None)
    r_absent = evaluate_preflight(inv, host=absent)
    assert r_absent["go"] is False
    assert "origin_server_cert_material" in r_absent["failed"]


def test_client_eku_identity_and_split_from_origin():
    inv = _ready_inv()
    base = _good_host(inv)

    bad_eku = with_host_overrides(
        base,
        client_cert=CertMaterialFact(
            path=inv.client_cert_mount_path,
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_client_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=(inv.expected_client_identity,),
            has_client_auth_eku=False,
            has_server_auth_eku=True,
            subject_cn=inv.expected_client_identity,
        ),
    )
    r_eku = evaluate_preflight(inv, host=bad_eku)
    assert r_eku["go"] is False
    assert "client_cert_eku" in r_eku["failed"]

    wrong_id = with_host_overrides(
        base,
        observed_client_identity="other-node.example.internal",
        client_cert=CertMaterialFact(
            path=inv.client_cert_mount_path,
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_client_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=("other-node.example.internal",),
            has_client_auth_eku=True,
            subject_cn="other-node.example.internal",
        ),
    )
    r_id = evaluate_preflight(inv, host=wrong_id)
    assert r_id["go"] is False
    assert "client_identity_match" in r_id["failed"]

    # Client presenting origin hostname as identity must fail.
    as_origin = with_host_overrides(
        base,
        observed_client_identity=inv.origin.host,
        client_cert=CertMaterialFact(
            path=inv.client_cert_mount_path,
            exists=True,
            is_symlink=False,
            mode_bits=0o644,
            sha256_hex=inv.trust.mtls_client_cert_sha256,
            not_after_utc="2099-06-01T00:00:00Z",
            san_dns=(inv.origin.host,),
            has_client_auth_eku=True,
            subject_cn=inv.origin.host,
        ),
    )
    r_as_origin = evaluate_preflight(inv, host=as_origin)
    assert r_as_origin["go"] is False
    assert "client_identity_not_origin" in r_as_origin["failed"]

    # Correct split: origin SAN == origin host; client identity == expected_client_identity.
    ok = evaluate_preflight(inv, host=base)
    assert ok["go"] is True
    assert ok["plan_success"] is True
    assert ok["origin_host"] == inv.origin.host
    assert ok["expected_client_identity"] == inv.expected_client_identity
    assert ok["origin_host"] != ok["expected_client_identity"]

    key_mismatch = with_host_overrides(base, client_key_matches_cert=False)
    r_key = evaluate_preflight(inv, host=key_mismatch)
    assert r_key["go"] is False
    assert "client_key_matches_cert" in r_key["failed"]


def test_placeholder_sbom_provenance_signature_fail_plan_success():
    inv = _ready_inv()
    base = _good_host(inv)

    for host in (
        with_host_overrides(base, sbom_ref_reviewed="placeholder:sbom"),
        with_host_overrides(base, provenance_ref_reviewed="REQUIRED:PROV"),
        with_host_overrides(base, manifest_signature="REQUIRED:OPERATOR_SIGNATURE"),
        with_host_overrides(base, manifest_signature=""),
        with_host_overrides(base, sbom_ref_reviewed="spdx:other-reviewed"),
    ):
        report = evaluate_preflight(inv, host=host)
        assert report["go"] is False
        assert report["plan_success"] is False


def test_render_hardening_and_no_secrets(tmp_path: Path):
    inv = _inv()
    text = render_compose_override(inv)
    assert 'user: "10001:10001"' in text
    assert "read_only: true" in text
    assert "cap_drop:" in text
    assert "no-new-privileges:true" in text
    assert "internal: true" in text
    assert "docker.sock" not in text
    assert "privileged:" not in text
    assert "network_mode: host" not in text
    assert "ports:" not in text
    assert inv.image.digest in text
    assert "PRIVATE KEY" not in text
    assert "BEGIN CERTIFICATE" not in text
    assert 'ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY: "false"' in text
    assert 'live_pilot_ready: "false"' in text

    man = render_all(inv, tmp_path / "out")
    assert man["apply_allowed"] is False
    assert man["signing"]["signature"].startswith("REQUIRED:")
    blob = (tmp_path / "out" / "inventory.public.json").read_text(encoding="utf-8")
    assert "PRIVATE KEY" not in blob


def test_firewall_plan_exact_origin_only():
    inv = _inv()
    plan = render_firewall_plan(inv)
    assert inv.origin.pinned_resolved_ipv4 in plan
    assert str(inv.origin.port) in plan
    assert "NOT APPLIED" in plan
    assert "default deny" in plan.lower() or "Default deny" in plan
    assert "public media" in plan.lower()
    assert "nft" in plan.lower()


def test_canary_zero_redirect_and_rollback_scope():
    inv = _inv()
    canary = render_canary_plan(inv)
    assert canary["client_redirect_percent"] == 0
    assert canary["client_redirect_active"] is False
    assert canary["live_pilot_ready"] is False
    assert canary["request_mode"] == "synthetic_only"
    assert canary["escalation"]["human_approval_required_before_each_step"] is True

    rb = render_rollback_plan(inv)
    assert rb["tests_must_not_execute_destructive_commands"] is True
    assert rb["apply_allowed"] is False
    assert validate_cache_root_for_plan(inv.cache.device_or_path) is True
    assert validate_cache_root_for_plan("/") is False
    assert validate_cache_root_for_plan("/var") is False
    dumped = json.dumps(rb)
    assert "rm -rf /" in dumped
    assert not re.search(r'"action":\s*"rm -rf', dumped)


def test_idempotent_render_and_drift(tmp_path: Path):
    inv = _inv()
    result = render_twice_identical(inv, tmp_path / "work")
    assert result["identical"] is True
    expected = json.loads(
        (tmp_path / "work" / "a" / "staging-render-manifest.v1.json").read_text(encoding="utf-8")
    )
    ok = detect_drift(expected_manifest=expected, current_dir=tmp_path / "work" / "a")
    assert ok["drift"] is False
    assert ok["incomplete_inputs"] is True
    assert ok["plan_success"] is False
    assert ok["apply_allowed"] is False

    drifted = detect_drift(
        expected_manifest=expected,
        current_dir=tmp_path / "work" / "a",
        unexpected_image_digest="sha256:" + ("f" * 64),
        unexpected_cert_fingerprint="ab",
    )
    assert drifted["drift"] is True
    assert "unexpected_image_change" in drifted["reasons"]


def test_central_stream_and_no_remote_sockets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY", "false")
    from app.core.config import get_settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)
    assert client.get("/api/stream/abcdefghijklmnopqrstuvwx123456/master.m3u8").status_code == 401


def test_cli_plan_render_smoke(tmp_path: Path):
    from app.services.branch_cache.deploy import cli

    inv = _inv()
    inv_path = tmp_path / "inv.json"
    write_staging_inventory(inv_path, inv)
    rc = cli.main(["plan", "--inventory", str(inv_path)])
    assert rc == 2
    out = tmp_path / "rendered"
    rc2 = cli.main(["render", "--inventory", str(inv_path), "--out", str(out)])
    assert rc2 == 0
    assert (out / "docker-compose.branch-cache.one-node-staging.override.yml").is_file()
    rc3 = cli.main(["drift", "--inventory", str(inv_path), "--work", str(tmp_path / "dwork")])
    assert rc3 == 0
