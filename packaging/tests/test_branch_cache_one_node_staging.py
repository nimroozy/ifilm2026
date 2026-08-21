"""Phase 9 — static contract for one-node staging deploy package."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / "packaging/compose/docker-compose.production.yml"
STAGING_DEPLOY = ROOT / "deploy/staging/docker-compose.staging.yml"
PHASE8 = ROOT / "packaging/compose/docker-compose.branch-cache.staging-candidate.yml"
FIXTURE = ROOT / "packaging/compose/one-node-staging-fixtures/inventory.v1.example.json"
INSTALLER = ROOT / "packaging/installer/install_release.sh"
SECURITY = ROOT / "SECURITY.md"
RELEASE_WF = ROOT / ".github/workflows/release.yml"
PHASE9_DOC = ROOT / "docs/media/HYBRID_CDN_PHASE9.md"
RUNBOOK = ROOT / "docs/media/HYBRID_CDN_ONE_NODE_STAGING_RUNBOOK.md"
DEPLOY_PKG = ROOT / "app/backend/app/services/branch_cache/deploy"


class BranchCacheOneNodeStagingTests(unittest.TestCase):
    def test_files_exist(self):
        self.assertTrue(FIXTURE.is_file())
        self.assertTrue(PHASE9_DOC.is_file())
        self.assertTrue(RUNBOOK.is_file())
        self.assertTrue((DEPLOY_PKG / "inventory.py").is_file())
        self.assertTrue((DEPLOY_PKG / "preflight.py").is_file())
        self.assertTrue((DEPLOY_PKG / "render.py").is_file())
        self.assertTrue((DEPLOY_PKG / "cli.py").is_file())

    def test_production_never_references_one_node_staging(self):
        text = PROD.read_text(encoding="utf-8")
        self.assertNotIn("one-node-staging", text)
        self.assertNotIn("Dockerfile.branch-cache", text)
        self.assertIn('ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY: "false"', text)
        self.assertIn('ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE: "false"', text)
        self.assertNotIn("docker.sock", text)
        self.assertNotRegex(text, r"(?m)^\s+privileged:\s*true")

    def test_deploy_staging_and_phase8_untouched_by_phase9_apply(self):
        text = STAGING_DEPLOY.read_text(encoding="utf-8")
        self.assertNotIn("ONE_NODE_STAGING_DEPLOY", text)
        self.assertNotIn("one-node-staging", text)
        p8 = PHASE8.read_text(encoding="utf-8")
        self.assertIn("staging-candidate", p8)
        self.assertNotIn("ONE_NODE_STAGING_DEPLOY", p8)

    def test_inventory_fixture_no_secrets_immutable_digest(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        blob = json.dumps(raw)
        self.assertNotIn("PRIVATE KEY", blob)
        self.assertNotIn("BEGIN CERTIFICATE", blob)
        self.assertEqual(raw["schema_version"], "ifilm.branch_node.staging_inventory.v1")
        self.assertEqual(raw["environment"], "staging-candidate")
        self.assertTrue(raw["image"]["digest"].startswith("sha256:"))
        self.assertNotIn(":", raw["image"]["repository"].split("/")[-1])
        self.assertFalse(raw["live_pilot_ready"])
        self.assertFalse(raw["client_redirect_active"])
        self.assertEqual(raw["bind_host"], "127.0.0.1")
        self.assertEqual(raw["run_as_uid"], 10001)

    def test_installer_security_flags_false(self):
        self.assertIn(
            "ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY=false",
            INSTALLER.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "`ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY=false`",
            SECURITY.read_text(encoding="utf-8"),
        )

    def test_release_does_not_publish_one_node_staging(self):
        text = RELEASE_WF.read_text(encoding="utf-8")
        self.assertNotIn("one-node-staging", text)
        self.assertNotIn("ONE_NODE_STAGING", text)

    def test_docs_dependency_order(self):
        text = PHASE9_DOC.read_text(encoding="utf-8")
        self.assertIn("#81", text)
        self.assertIn("#88", text)
        self.assertIn("Phase 9", text)
        self.assertIn("plan/render", text.lower())
        self.assertIn("live_pilot_ready", text)
        rb = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("go / no-go", rb.lower())
        self.assertIn("remaining", rb.lower())


if __name__ == "__main__":
    unittest.main()
