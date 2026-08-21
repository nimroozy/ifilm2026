"""Phase 9 plan/render CLI — read-only by default; no remote execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.services.branch_cache.deploy.drift import detect_drift, render_twice_identical
from app.services.branch_cache.deploy.inventory import load_staging_inventory
from app.services.branch_cache.deploy.preflight import (
    HostFacts,
    evaluate_preflight,
    write_preflight_report,
)
from app.services.branch_cache.deploy.render import render_all


def _cmd_plan(args: argparse.Namespace) -> int:
    inventory = load_staging_inventory(Path(args.inventory))
    # Default host facts are incomplete → fail closed unless --host-facts provided.
    if args.host_facts:
        raw = json.loads(Path(args.host_facts).read_text(encoding="utf-8"))
        host = HostFacts(**raw)
    else:
        host = HostFacts(
            resolved_origin_ips=(),
            ca=None,
            client_cert=None,
            client_key_exists=False,
            image_digest_present=False,
            sbom_ref_present=False,
            provenance_ref_present=False,
            rollback_prior_digest_recorded=False,
        )
    report = evaluate_preflight(inventory, host=host)
    if args.out:
        write_preflight_report(Path(args.out), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    # Plan CLI exits 0 when report is produced; go/no-go is in the document.
    # Refuse success classification when incomplete unless explicitly rendered.
    return 0 if report.get("go") else 2


def _cmd_render(args: argparse.Namespace) -> int:
    inventory = load_staging_inventory(Path(args.inventory))
    out = Path(args.out)
    manifest = render_all(inventory, out)
    print(
        json.dumps({"rendered": str(out), "manifest_sha256": manifest["manifest_sha256"]}, indent=2)
    )
    return 0


def _cmd_drift(args: argparse.Namespace) -> int:
    inventory = load_staging_inventory(Path(args.inventory))
    tmp = Path(args.work)
    result = render_twice_identical(inventory, tmp)
    expected = json.loads(
        (tmp / "a" / "staging-render-manifest.v1.json").read_text(encoding="utf-8")
    )
    drift = detect_drift(expected_manifest=expected, current_dir=tmp / "a")
    print(json.dumps({"idempotent": result, "drift": drift}, indent=2, sort_keys=True))
    return 0 if result["identical"] and not drift["drift"] else 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.services.branch_cache.deploy.cli",
        description="Phase 9 one-node staging plan/render (no remote apply).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan", help="Read-only preflight/plan (default dry-run).")
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--host-facts", default="")
    plan.add_argument("--out", default="")
    plan.set_defaults(func=_cmd_plan)

    rend = sub.add_parser("render", help="Render deterministic staging artifacts.")
    rend.add_argument("--inventory", required=True)
    rend.add_argument("--out", required=True)
    rend.set_defaults(func=_cmd_render)

    drift = sub.add_parser("drift", help="Idempotent double-render + drift check.")
    drift.add_argument("--inventory", required=True)
    drift.add_argument("--work", required=True)
    drift.set_defaults(func=_cmd_drift)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
