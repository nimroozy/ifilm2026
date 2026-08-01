#!/usr/bin/env python3
"""Sign release-manifest.json with an Ed25519 private key (PEM)."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--signature-out", required=True, type=Path)
    parser.add_argument(
        "--key-file",
        type=Path,
        default=None,
        help="PEM private key path (or set IFILM_RELEASE_SIGNING_KEY env with PEM body)",
    )
    args = parser.parse_args()

    key_path = args.key_file
    tmp: tempfile.TemporaryDirectory[str] | None = None
    if key_path is None:
        pem = os.environ.get("IFILM_RELEASE_SIGNING_KEY", "")
        if not pem.strip():
            raise SystemExit("IFILM_RELEASE_SIGNING_KEY or --key-file required")
        tmp = tempfile.TemporaryDirectory(prefix="ifilm-sign-")
        key_path = Path(tmp.name) / "key.pem"
        key_path.write_text(pem if "BEGIN" in pem else pem, encoding="utf-8")
        os.chmod(key_path, 0o600)

    try:
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(key_path),
                "-rawin",
                "-in",
                str(args.manifest),
                "-out",
                str(args.signature_out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        # Some openssl builds need without -rawin for Ed25519
        if result.returncode != 0:
            result = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(key_path),
                    "-in",
                    str(args.manifest),
                    "-out",
                    str(args.signature_out),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            raise SystemExit(result.stderr or "openssl sign failed")
        print(args.signature_out)
        return 0
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
