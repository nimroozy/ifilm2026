"""Phase 8 — static contract for mTLS staging-candidate packaging."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / "packaging/compose/docker-compose.production.yml"
STAGING_DEPLOY = ROOT / "deploy/staging/docker-compose.staging.yml"
CANDIDATE = ROOT / "packaging/compose/docker-compose.branch-cache.staging-candidate.yml"
ENROLLMENT = ROOT / "packaging/compose/staging-candidate-fixtures/enrollment.v1.json"
INSTALLER = ROOT / "packaging/installer/install_release.sh"
SECURITY = ROOT / "SECURITY.md"
RELEASE_WF = ROOT / ".github/workflows/release.yml"
CERTS = ROOT / "packaging/compose/staging-candidate-fixtures/certs"


class BranchCacheStagingCandidateTests(unittest.TestCase):
    def test_files_exist(self):
        self.assertTrue(CANDIDATE.is_file())
        self.assertTrue(ENROLLMENT.is_file())

    def test_production_never_references_staging_candidate(self):
        text = PROD.read_text(encoding="utf-8")
        self.assertNotIn("staging-candidate", text)
        self.assertNotIn("Dockerfile.branch-cache", text)
        self.assertIn('ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE: "false"', text)
        self.assertNotRegex(text, r"(?m)^\s+privileged:\s*true")
        self.assertNotIn("docker.sock", text)

    def test_deploy_staging_compose_unrelated(self):
        text = STAGING_DEPLOY.read_text(encoding="utf-8")
        self.assertNotIn("branch-cache-staging-candidate", text)
        self.assertNotIn("MTLS_STAGING_CANDIDATE", text)

    def test_candidate_compose_hardening(self):
        text = CANDIDATE.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
        self.assertIn("internal: true", code)
        self.assertIn("read_only: true", code)
        self.assertIn("no-new-privileges:true", code)
        self.assertIn("cap_drop:", code)
        self.assertIn('user: "10001:10001"', code)
        self.assertNotRegex(code, r"(?m)^\s+ports:")
        self.assertNotIn("privileged: true", code)
        self.assertNotIn("network_mode: host", code)
        self.assertNotIn("docker.sock", code)
        self.assertIn('live_pilot_ready: "false"', text)
        self.assertIn('client_redirect_active: "false"', text)
        self.assertIn('ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE: "false"', text)
        self.assertIn("/run/ifilm/certs:ro", text)

    def test_enrollment_manifest_has_no_secrets(self):
        raw = json.loads(ENROLLMENT.read_text(encoding="utf-8"))
        blob = json.dumps(raw)
        self.assertNotIn("PRIVATE KEY", blob)
        self.assertNotIn("BEGIN CERTIFICATE", blob)
        self.assertFalse(raw.get("live_pilot_ready"))
        self.assertFalse(raw.get("client_redirect_active"))
        self.assertEqual(raw["schema_version"], "ifilm.branch_node.enrollment.v1")
        self.assertEqual(len(raw["origin_allowlist"]), 1)

    def test_cert_fixtures_are_placeholders_only(self):
        for name in CERTS.iterdir():
            if name.suffix == ".key" or name.name.endswith(".key"):
                self.fail(f"private key file must not be committed: {name}")
            if name.suffix in {".crt", ".pem"} and "placeholder" not in name.name:
                text = name.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("PRIVATE KEY", text)
                # edge-grant public pem is allowed
                if "PRIVATE" in text:
                    self.fail(name)

    def test_installer_and_security_flag_false(self):
        self.assertIn(
            "ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE=false",
            INSTALLER.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "`ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE=false`",
            SECURITY.read_text(encoding="utf-8"),
        )

    def test_release_does_not_publish_candidate(self):
        text = RELEASE_WF.read_text(encoding="utf-8")
        self.assertNotIn("staging-candidate", text)
        self.assertNotIn("mtls", text.lower())


if __name__ == "__main__":
    unittest.main()
