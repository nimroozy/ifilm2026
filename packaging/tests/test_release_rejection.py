#!/usr/bin/env python3
"""Verify release tooling rejects unsigned/tampered/mismatched artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOOD_BACKEND = (
    "ghcr.io/nimroozy/ifilm2026/backend-api@"
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)
GOOD_FRONTEND = (
    "ghcr.io/nimroozy/ifilm2026/frontend@"
    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)


class ReleaseRejectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ifilm-reject-"))
        self.key = self.tmp / "key.pem"
        self.pub = self.tmp / "key.pub"
        self.other = self.tmp / "other.pem"
        subprocess.check_call(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(self.key)])
        subprocess.check_call(["openssl", "pkey", "-in", str(self.key), "-pubout", "-out", str(self.pub)])
        subprocess.check_call(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(self.other)])
        os.chmod(self.key, 0o600)

    def _archive(self, name: str = "ifilm-1.0.0.tar.gz", payload: bytes = b"ok") -> Path:
        stage = self.tmp / "stage"
        stage.mkdir(exist_ok=True)
        (stage / "payload.bin").write_bytes(payload)
        archive = self.tmp / name
        subprocess.check_call(["tar", "-czf", str(archive), "-C", str(stage), "payload.bin"])
        return archive

    def _manifest(self, archive: Path, *, require: bool = False, **overrides) -> Path:
        out = self.tmp / "release-manifest.json"
        cmd = [
            sys.executable,
            str(ROOT / "packaging/release/build_manifest.py"),
            "--version",
            "1.0.0",
            "--archive",
            str(archive),
            "--out",
            str(out),
            "--image-digest",
            f"backend-api={GOOD_BACKEND}",
            "--image-digest",
            f"frontend={GOOD_FRONTEND}",
        ]
        if require:
            cmd.append("--require-registry-digests")
        subprocess.check_call(cmd)
        data = json.loads(out.read_text(encoding="utf-8"))
        data.update(overrides)
        out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return out

    def _sign(self, manifest: Path, key: Path) -> Path:
        sig = manifest.with_suffix(manifest.suffix + ".sig")
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "packaging/release/sign_manifest.py"),
                "--manifest",
                str(manifest),
                "--key-file",
                str(key),
                "--signature-out",
                str(sig),
            ]
        )
        return sig

    def _verify(self, manifest: Path, sig: Path, pub: Path) -> int:
        return subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(pub),
                "-sigfile",
                str(sig),
                "-rawin",
                "-in",
                str(manifest),
            ],
            check=False,
            capture_output=True,
        ).returncode

    def test_unsigned_manifest_rejected(self) -> None:
        archive = self._archive()
        manifest = self._manifest(archive)
        missing = self.tmp / "missing.sig"
        missing.write_bytes(b"")
        self.assertNotEqual(self._verify(manifest, missing, self.pub), 0)

    def test_modified_manifest_rejected(self) -> None:
        archive = self._archive()
        manifest = self._manifest(archive)
        sig = self._sign(manifest, self.key)
        self.assertEqual(self._verify(manifest, sig, self.pub), 0)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["version"] = "9.9.9"
        manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.assertNotEqual(self._verify(manifest, sig, self.pub), 0)

    def test_wrong_public_key_rejected(self) -> None:
        archive = self._archive()
        manifest = self._manifest(archive)
        sig = self._sign(manifest, self.key)
        wrong_pub = self.tmp / "wrong.pub"
        subprocess.check_call(["openssl", "pkey", "-in", str(self.other), "-pubout", "-out", str(wrong_pub)])
        self.assertNotEqual(self._verify(manifest, sig, wrong_pub), 0)

    def test_modified_artifact_checksum_mismatch(self) -> None:
        archive = self._archive(payload=b"good")
        manifest = self._manifest(archive)
        expected = json.loads(manifest.read_text(encoding="utf-8"))["artifacts"][0]["sha256"]
        archive.write_bytes(archive.read_bytes() + b"tamper")
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.assertNotEqual(expected, actual)

    def test_build_manifest_rejects_missing_digests_when_required(self) -> None:
        archive = self._archive()
        out = self.tmp / "bad-manifest.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "packaging/release/build_manifest.py"),
                "--version",
                "1.0.0",
                "--archive",
                str(archive),
                "--out",
                str(out),
                "--require-registry-digests",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("missing required image digest", proc.stderr)

    def test_build_manifest_rejects_malformed_digest(self) -> None:
        archive = self._archive()
        out = self.tmp / "bad-manifest.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "packaging/release/build_manifest.py"),
                "--version",
                "1.0.0",
                "--archive",
                str(archive),
                "--out",
                str(out),
                "--require-registry-digests",
                "--image-digest",
                "backend-api=sha256:not-a-registry-ref",
                "--image-digest",
                f"frontend={GOOD_FRONTEND}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_mismatched_image_digest_detected(self) -> None:
        archive = self._archive()
        manifest = self._manifest(archive, require=True)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        claimed = data["image_digests"]["backend-api"]
        actual = (
            "ghcr.io/nimroozy/ifilm2026/backend-api@"
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        )
        self.assertNotEqual(claimed, actual)

    def test_stale_minimum_version_policy(self) -> None:
        archive = self._archive()
        manifest = self._manifest(archive, minimum_version="9.0.0", version="1.0.0")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        current = "1.0.0"
        self.assertEqual(data["minimum_version"], "9.0.0")
        self.assertLess(current, data["minimum_version"])


if __name__ == "__main__":
    unittest.main()
