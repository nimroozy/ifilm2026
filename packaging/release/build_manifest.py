#!/usr/bin/env python3
"""Build release-manifest.json for a versioned iFilm release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


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
    parser.add_argument("--image-digest", action="append", default=[], help="name=digest")
    args = parser.parse_args()

    digests = {}
    for item in args.image_digest:
        if "=" in item:
            k, v = item.split("=", 1)
            digests[k] = v

    archive = args.archive
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
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
