#!/usr/bin/env python3
"""Ensure production public key trust anchor and revocation list stay consistent."""

from __future__ import annotations

import hashlib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVOKED = "8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26"
CURRENT = "e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612"


class SigningTrustAnchorTests(unittest.TestCase):
    def test_committed_public_key_fingerprint(self) -> None:
        pub = ROOT / "packaging/keys/release-signing.pub"
        der = subprocess.check_output(
            ["openssl", "pkey", "-pubin", "-in", str(pub), "-outform", "DER"]
        )
        fp = hashlib.sha256(der).hexdigest()
        self.assertEqual(fp, CURRENT)

    def test_install_sh_embeds_current_fingerprint(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn(CURRENT, text)
        self.assertIn(REVOKED, text)  # hard-reject case

    def test_revoked_fingerprint_listed_and_not_current(self) -> None:
        revoked = (ROOT / "packaging/keys/REVOKED_FINGERPRINTS.txt").read_text(encoding="utf-8")
        self.assertIn(REVOKED, revoked)
        self.assertNotEqual(REVOKED, CURRENT)
        pub = (ROOT / "packaging/keys/release-signing.pub").read_text(encoding="utf-8")
        # Public PEM must not still be the old one (fingerprint already asserts).
        self.assertTrue(re.search(r"BEGIN PUBLIC KEY", pub))


if __name__ == "__main__":
    unittest.main()
