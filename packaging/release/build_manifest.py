#!/usr/bin/env python3
"""Build release-manifest.json for a versioned iFilm release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from image_refs import ImageRefError, validate_image_digests  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--migration-head", default="012_system_update_notes")
    parser.add_argument("--minimum-version", default="0.1.0")
    parser.add_argument("--rollback-supported", action="store_true", default=True)
    parser.add_argument("--database-backup-required", action="store_true", default=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--image-digest",
        action="append",
        default=[],
        help="name=ghcr.io/nimroozy/ifilm2026/<name>@sha256:...",
    )
    parser.add_argument(
        "--require-registry-digests",
        action="store_true",
        help="Require immutable GHCR digests for backend-api and frontend",
    )
    args = parser.parse_args()

    digests: dict[str, str] = {}
    for item in args.image_digest:
        if "=" not in item:
            print(f"invalid --image-digest (expected name=ref): {item}", file=sys.stderr)
            return 2
        key, value = item.split("=", 1)
        digests[key.strip()] = value.strip()

    try:
        digests = validate_image_digests(
            digests, require_all=bool(args.require_registry_digests)
        )
    except ImageRefError as exc:
        print(f"image digest validation failed: {exc}", file=sys.stderr)
        return 2

    archive = args.archive
    if not archive.is_file():
        print(f"archive not found: {archive}", file=sys.stderr)
        return 2

    manifest = {
        "version": args.version.lstrip("v"),
        "channel": args.channel,
        "commit_sha": git_sha(),
        "published_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "minimum_version": args.minimum_version.lstrip("v"),
        "migration_head": args.migration_head,
        "database_backup_required": bool(args.database_backup_required),
        "rollback_supported": bool(args.rollback_supported),
        "rollback_compatibility": "application_only",
        "artifacts": [
            {
                "name": archive.name,
                "sha256": sha256_file(archive),
                "size_bytes": archive.stat().st_size,
            }
        ],
        "image_digests": digests,
        "checksum": sha256_file(archive),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
