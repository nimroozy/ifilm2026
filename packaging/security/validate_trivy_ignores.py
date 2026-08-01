#!/usr/bin/env python3
"""Validate packaging/security/trivy-ignore.json; fail on expired/malformed entries."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REQUIRED_FIELDS = ("id", "component", "justification", "owner", "expiry")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).resolve().parent / "trivy-ignore.json",
    )
    args = parser.parse_args()
    data = json.loads(args.file.read_text(encoding="utf-8"))
    if int(data.get("version") or 0) < 1:
        print("trivy-ignore.json: missing/invalid version", file=sys.stderr)
        return 2
    today = date.today().isoformat()
    errors: list[str] = []
    for idx, entry in enumerate(data.get("ignores") or []):
        for field in REQUIRED_FIELDS:
            if not str(entry.get(field) or "").strip():
                errors.append(f"ignores[{idx}]: missing {field}")
        expiry = str(entry.get("expiry") or "")
        if expiry and expiry < today:
            errors.append(
                f"ignores[{idx}]: expired ignore {entry.get('id')} (expiry={expiry})"
            )
    if errors:
        print("trivy ignore validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"trivy-ignore.json ok ({len(data.get('ignores') or [])} active ignores)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
