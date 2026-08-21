"""Deterministic render of staging-only deploy artifacts (Phase 9).

Plan/render only — never applies to a host, never embeds secrets.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.branch_cache.deploy.inventory import StagingInventoryV1

COMPOSE_OVERRIDE_NAME = "docker-compose.branch-cache.one-node-staging.override.yml"
SYSTEMD_DROPIN_NAME = "ifilm-branch-cache-staging.service.d/10-staging-candidate.conf"
MANIFEST_NAME = "staging-render-manifest.v1.json"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_compose_override(inventory: StagingInventoryV1) -> str:
    """Hardened compose override — placeholders only, private/internal bind."""
    img = inventory.image.pinned_ref
    lines = [
        "# GENERATED — Phase 9 one-node staging deploy candidate (plan/render only).",
        "# DO NOT apply without human review. Never merge into production compose.",
        "# Secrets/certs are mount-path references only; PEMs are never embedded.",
        f"# inventory_node_id={inventory.node_id}",
        f"# image_digest={inventory.image.digest}",
        "",
        "name: ifilm-branch-cache-one-node-staging",
        "",
        "services:",
        "  branch-cache-one-node-staging:",
        f"    image: {img}",
        f'    user: "{inventory.run_as_uid}:{inventory.run_as_gid}"',
        "    read_only: true",
        "    expose: []",
        "    networks:",
        "      - branch_staging_internal",
        "    security_opt:",
        "      - no-new-privileges:true",
        "    cap_drop:",
        "      - ALL",
        "    environment:",
        "      APP_ENV: development",
        '      ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT: "true"',
        '      ENABLE_BRANCH_CACHE_HTTP_SERVICE: "true"',
        '      ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE: "false"',
        '      ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY: "false"',
        '      ENABLE_BRANCH_CACHE_HTTP_HEALTH: "false"',
        '      ENABLE_BRANCH_CACHE_HTTP_METRICS: "false"',
        '      ENABLE_BRANCH_CACHE_HTTP_LAB_HTTPS_ADAPTER: "false"',
        "      BRANCH_CACHE_ENTRY_MODE: validate",
        f"      BRANCH_CACHE_NODE_ID: {inventory.node_id}",
        f"      BRANCH_CACHE_SITE_ID: {inventory.site_id}",
        f"      BRANCH_CACHE_CACHE_ROOT: {inventory.cache.mount_path}",
        f'      BRANCH_CACHE_BIND_HOST: "{inventory.bind_host}"',
        f"      BRANCH_CACHE_MTLS_CA_BUNDLE: {inventory.ca_bundle_mount_path}",
        f"      BRANCH_CACHE_MTLS_CLIENT_CERT: {inventory.client_cert_mount_path}",
        f"      BRANCH_CACHE_MTLS_CLIENT_KEY: {inventory.client_key_mount_path}",
        f"      EDGE_GRANT_PUBLIC_KEY_FILE: {inventory.edge_grant_public_key_mount_path}",
        "    volumes:",
        "      - type: bind",
        f"        source: {inventory.cache.device_or_path}",
        f"        target: {inventory.cache.mount_path}",
        "      - type: bind",
        "        source: REQUIRED:CERTS_HOST_DIR",
        "        target: /run/ifilm/certs",
        "        read_only: true",
        "    tmpfs:",
        "      - /tmp:size=64m,mode=1777",
        "    deploy:",
        "      resources:",
        "        limits:",
        f'          cpus: "{inventory.capacity.cpus}"',
        f"          memory: {inventory.capacity.memory_mb}M",
        f"          pids: {inventory.capacity.pids}",
        "    ulimits:",
        "      nofile:",
        f"        soft: {inventory.capacity.nofile_soft}",
        f"        hard: {inventory.capacity.nofile_hard}",
        '    restart: "no"',
        "    labels:",
        "      ifilm.compose.profile: one-node-staging-candidate-only",
        '      ifilm.branch_cache.phase: "9"',
        "      ifilm.branch_cache.activation: never-default",
        '      ifilm.branch_cache.live_pilot_ready: "false"',
        '      ifilm.branch_cache.client_redirect_active: "false"',
        "      ifilm.branch_cache.graceful_drain: required",
        "",
        "networks:",
        "  branch_staging_internal:",
        "    internal: true",
        "    name: ifilm-branch-one-node-staging-net",
        "",
    ]
    return "\n".join(lines)


def render_systemd_dropin(inventory: StagingInventoryV1) -> str:
    """Optional systemd drop-in — consistent hardening; not applied by tools."""
    return "\n".join(
        [
            "# GENERATED — Phase 9 staging-candidate drop-in (render only).",
            "# Do not enable in production. No ExecStart remote apply from this package.",
            "[Service]",
            f"User={inventory.run_as_uid}",
            f"Group={inventory.run_as_gid}",
            "NoNewPrivileges=yes",
            "ProtectSystem=strict",
            "ProtectHome=yes",
            "PrivateTmp=yes",
            "CapabilityBoundingSet=",
            "AmbientCapabilities=",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            f"ReadWritePaths={inventory.cache.mount_path}",
            "ReadOnlyPaths=/run/ifilm/certs",
            "Environment=ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY=false",
            "Environment=ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE=false",
            "",
        ]
    )


def build_render_manifest(
    inventory: StagingInventoryV1,
    *,
    compose_text: str,
    systemd_text: str,
    firewall_text: str,
    canary_text: str,
    rollback_text: str,
) -> dict[str, Any]:
    artifacts = {
        COMPOSE_OVERRIDE_NAME: _sha256_text(compose_text),
        SYSTEMD_DROPIN_NAME: _sha256_text(systemd_text),
        "firewall-egress.plan.md": _sha256_text(firewall_text),
        "canary-shadow.plan.json": _sha256_text(canary_text),
        "rollback.plan.json": _sha256_text(rollback_text),
    }
    payload = {
        "schema_version": "ifilm.branch_node.staging_render_manifest.v1",
        "node_id": inventory.node_id,
        "environment": inventory.environment,
        "image_digest": inventory.image.digest,
        "origin_host": inventory.origin.host,
        "origin_pinned_ip": inventory.origin.pinned_resolved_ipv4,
        "artifact_sha256": artifacts,
        "signing": {
            "status": "placeholder",
            "algorithm": "ed25519",
            "signature": "REQUIRED:OPERATOR_SIGNATURE_OVER_CANONICAL_JSON",
            "public_key_fingerprint_sha256": "e" * 64,
        },
        "live_pilot_ready": False,
        "client_redirect_active": False,
        "apply_allowed": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["manifest_sha256"] = _sha256_text(canonical)
    return payload


def render_all(inventory: StagingInventoryV1, out_dir: Path) -> dict[str, Any]:
    from app.services.branch_cache.deploy.canary_plan import render_canary_plan
    from app.services.branch_cache.deploy.firewall_plan import render_firewall_plan
    from app.services.branch_cache.deploy.rollback_plan import render_rollback_plan

    compose = render_compose_override(inventory)
    systemd = render_systemd_dropin(inventory)
    firewall = render_firewall_plan(inventory)
    canary = json.dumps(render_canary_plan(inventory), indent=2, sort_keys=True) + "\n"
    rollback = json.dumps(render_rollback_plan(inventory), indent=2, sort_keys=True) + "\n"
    manifest = build_render_manifest(
        inventory,
        compose_text=compose,
        systemd_text=systemd,
        firewall_text=firewall,
        canary_text=canary,
        rollback_text=rollback,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / COMPOSE_OVERRIDE_NAME).write_text(compose, encoding="utf-8")
    dropin_path = out_dir / SYSTEMD_DROPIN_NAME
    dropin_path.parent.mkdir(parents=True, exist_ok=True)
    dropin_path.write_text(systemd, encoding="utf-8")
    (out_dir / "firewall-egress.plan.md").write_text(firewall, encoding="utf-8")
    (out_dir / "canary-shadow.plan.json").write_text(canary, encoding="utf-8")
    (out_dir / "rollback.plan.json").write_text(rollback, encoding="utf-8")
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "inventory.public.json").write_text(
        json.dumps(inventory.to_public_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
