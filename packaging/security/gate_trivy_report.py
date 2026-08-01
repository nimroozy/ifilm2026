#!/usr/bin/env python3
"""Fail production release on unapproved CRITICAL / actionable HIGH Trivy findings."""

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
        "--fail-critical",
        action="store_true",
        default=True,
        help="Fail on unapproved CRITICAL findings (default: true)",
    )
    parser.add_argument(
        "--fail-actionable-high",
        action="store_true",
        default=True,
        help="Fail on HIGH findings that have a FixedVersion (default: true)",
    )
    args = parser.parse_args()

    ignores = _active_ignores(args.ignore_file)
    report = json.loads(args.report.read_text(encoding="utf-8"))

    blockers: list[str] = []
    reported_unfixed_high = 0
    for result in report.get("Results") or []:
        target = str(result.get("Target") or "")
        for vuln in result.get("Vulnerabilities") or []:
            severity = str(vuln.get("Severity") or "").upper()
            vuln_id = str(vuln.get("VulnerabilityID") or "")
            pkg = str(vuln.get("PkgName") or vuln.get("PackageName") or "")
            component = pkg or target
            fixed = str(vuln.get("FixedVersion") or "").strip()
            if (vuln_id, component) in ignores or (vuln_id, target) in ignores:
                continue
            if severity == "CRITICAL" and args.fail_critical:
                blockers.append(
                    f"CRITICAL {vuln_id} in {component} ({target})"
                    + (f" fixed:{fixed}" if fixed else " [no FixedVersion]")
                )
                continue
            if severity == "HIGH" and args.fail_actionable_high:
                if fixed:
                    blockers.append(
                        f"HIGH {vuln_id} in {component} ({target}) fixed:{fixed}"
                    )
                else:
                    reported_unfixed_high += 1

    if blockers:
        print("Trivy security gate FAILED:", file=sys.stderr)
        for item in blockers[:50]:
            print(f"  - {item}", file=sys.stderr)
        if len(blockers) > 50:
            print(f"  ... and {len(blockers) - 50} more", file=sys.stderr)
        return 1

    print(
        "Trivy security gate PASSED "
        f"(unapproved CRITICAL=0; actionable HIGH=0; "
        f"monitored unfixed HIGH={reported_unfixed_high})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
