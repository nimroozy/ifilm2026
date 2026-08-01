#!/usr/bin/env python3
"""Fail production release on unapproved CRITICAL/HIGH Trivy findings."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


def _active_ignores(ignore_path: Path) -> set[tuple[str, str]]:
    data = json.loads(ignore_path.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    active: set[tuple[str, str]] = set()
    for entry in data.get("ignores") or []:
        expiry = str(entry.get("expiry") or "")
        if expiry and expiry < today:
            raise SystemExit(f"expired ignore entry present: {entry.get('id')}")
        vuln = str(entry.get("id") or "").strip()
        component = str(entry.get("component") or "").strip()
        if vuln and component:
            active.add((vuln, component))
    return active


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--ignore-file",
        type=Path,
        default=Path(__file__).resolve().parent / "trivy-ignore.json",
    )
    parser.add_argument(
        "--fail-severities",
        default="CRITICAL,HIGH",
        help="Comma-separated severities that fail the gate",
    )
    args = parser.parse_args()

    fail_severities = {s.strip().upper() for s in args.fail_severities.split(",") if s.strip()}
    ignores = _active_ignores(args.ignore_file)
    report = json.loads(args.report.read_text(encoding="utf-8"))

    blockers: list[str] = []
    for result in report.get("Results") or []:
        target = str(result.get("Target") or "")
        for vuln in result.get("Vulnerabilities") or []:
            severity = str(vuln.get("Severity") or "").upper()
            if severity not in fail_severities:
                continue
            vuln_id = str(vuln.get("VulnerabilityID") or "")
            pkg = str(vuln.get("PkgName") or vuln.get("PackageName") or "")
            component = pkg or target
            if (vuln_id, component) in ignores or (vuln_id, target) in ignores:
                continue
            blockers.append(f"{severity} {vuln_id} in {component} ({target})")

    if blockers:
        print("Trivy security gate FAILED:", file=sys.stderr)
        for item in blockers[:50]:
            print(f"  - {item}", file=sys.stderr)
        if len(blockers) > 50:
            print(f"  ... and {len(blockers) - 50} more", file=sys.stderr)
        return 1

    print(
        f"Trivy security gate PASSED (no unapproved {', '.join(sorted(fail_severities))} findings)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
