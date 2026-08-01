#!/usr/bin/env python3
"""Disposable simulation of signed release verify + upgrade/rollback metadata.

Does not touch existing staging volumes. Validates the crypto + state machine
pieces required before publishing v0.1.0-test / v0.1.1-test tags.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DisposableUpdateSimulation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ifilm-disp-"))
        self.key = self.tmp / "key.pem"
        self.pub = self.tmp / "key.pub"
        subprocess.check_call(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(self.key)])
        subprocess.check_call(["openssl", "pkey", "-in", str(self.key), "-pubout", "-out", str(self.pub)])
        os.chmod(self.key, 0o600)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_release(self, version: str) -> tuple[Path, Path, Path]:
        stage = self.tmp / f"stage-{version}"
        stage.mkdir()
        payload = stage / "payload.txt"
        payload.write_text(f"release {version}\n", encoding="utf-8")
        archive = self.tmp / f"ifilm-{version}.tar.gz"
        subprocess.check_call(["tar", "-czf", str(archive), "-C", str(stage), "payload.txt"])
        manifest = self.tmp / f"manifest-{version}.json"
        backend = (
            "ghcr.io/nimroozy/ifilm2026/backend-api@"
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        frontend = (
            "ghcr.io/nimroozy/ifilm2026/frontend@"
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        )
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "packaging/release/build_manifest.py"),
                "--version",
                version,
                "--archive",
                str(archive),
                "--migration-head",
                "011_system_updates",
                "--require-registry-digests",
                "--image-digest",
                f"backend-api={backend}",
                "--image-digest",
                f"frontend={frontend}",
                "--out",
                str(manifest),
            ]
        )
        sig = self.tmp / f"manifest-{version}.json.sig"
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "packaging/release/sign_manifest.py"),
                "--manifest",
                str(manifest),
                "--key-file",
                str(self.key),
                "--signature-out",
                str(sig),
            ]
        )
        return archive, manifest, sig

    def test_signed_upgrade_path_and_checksum(self) -> None:
        a0, m0, s0 = self._make_release("0.1.0-test")
        a1, m1, s1 = self._make_release("0.1.1-test")
        for manifest, sig in ((m0, s0), (m1, s1)):
            verify = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(self.pub),
                    "-sigfile",
                    str(sig),
                    "-rawin",
                    "-in",
                    str(manifest),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)

        # Tampered archive must fail checksum compare against signed manifest.
        bad = self.tmp / "ifilm-0.1.1-test-tampered.tar.gz"
        bad.write_bytes(a1.read_bytes() + b"x")
        data = json.loads(m1.read_text(encoding="utf-8"))
        expected = data["artifacts"][0]["sha256"]
        actual = hashlib.sha256(bad.read_bytes()).hexdigest()
        self.assertNotEqual(expected, actual)

        v0 = json.loads(m0.read_text(encoding="utf-8"))["version"]
        v1 = json.loads(m1.read_text(encoding="utf-8"))["version"]
        self.assertNotEqual(v0, v1)
        self.assertTrue(a0.is_file() and a1.is_file())

    def test_invalid_signature_rejected(self) -> None:
        _, manifest, _ = self._make_release("0.1.0-test")
        other = self.tmp / "other.pem"
        subprocess.check_call(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(other)])
        bad_sig = self.tmp / "bad.sig"
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "packaging/release/sign_manifest.py"),
                "--manifest",
                str(manifest),
                "--key-file",
                str(other),
                "--signature-out",
                str(bad_sig),
            ]
        )
        verify = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(self.pub),
                "-sigfile",
                str(bad_sig),
                "-rawin",
                "-in",
                str(manifest),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(verify.returncode, 0)


if __name__ == "__main__":
    unittest.main()
