"""Phase 7 — static hardening / compose contract for branch-cache lab artifact."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROD = ROOT / "packaging/compose/docker-compose.production.yml"
STAGING = ROOT / "deploy/staging/docker-compose.staging.yml"
LAB = ROOT / "packaging/compose/docker-compose.branch-cache.lab.yml"
DOCKERFILE = ROOT / "app/backend/Dockerfile.branch-cache.lab"
ENTRYPOINT = ROOT / "app/backend/docker/entrypoint.branch-cache.sh"
REQS = ROOT / "app/backend/requirements-branch-cache.txt"
INSTALLER = ROOT / "packaging/installer/install_release.sh"
RELEASE_WF = ROOT / ".github/workflows/release.yml"
IMAGE_REFS = ROOT / "packaging/release/image_refs.py"
SECURITY = ROOT / "SECURITY.md"


class BranchCacheLabArtifactTests(unittest.TestCase):
    def test_lab_files_exist(self):
        for path in (LAB, DOCKERFILE, ENTRYPOINT, REQS):
            self.assertTrue(path.is_file(), msg=str(path))

    def test_production_compose_never_references_lab_artifact(self):
        text = PROD.read_text(encoding="utf-8")
        self.assertNotIn("Dockerfile.branch-cache", text)
        self.assertNotIn("docker-compose.branch-cache.lab", text)
        self.assertNotIn("branch-cache-lab", text)
        self.assertIn('ENABLE_BRANCH_CACHE_HTTP_SERVICE: "false"', text)
        self.assertIn('ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT: "false"', text)
        self.assertNotRegex(text, r"(?m)^\s+privileged:\s*true")
        self.assertNotIn("docker.sock", text)
        self.assertNotIn("network_mode: host", text)

    def test_staging_compose_has_no_branch_service(self):
        text = STAGING.read_text(encoding="utf-8")
        self.assertNotIn("branch-cache-lab", text)
        self.assertNotIn("Dockerfile.branch-cache", text)

    def test_lab_compose_hardening_contract(self):
        text = LAB.read_text(encoding="utf-8")
        self.assertIn('network_mode: "none"', text)
        self.assertIn("read_only: true", text)
        self.assertIn("no-new-privileges:true", text)
        self.assertIn("cap_drop:", text)
        self.assertIn("- ALL", text)
        self.assertIn('user: "10001:10001"', text)
        # No published ports mapping (ignore comments).
        code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        code = "\n".join(code_lines)
        self.assertNotRegex(code, r"(?m)^\s+ports:")
        self.assertNotIn("privileged: true", code)
        self.assertNotIn("network_mode: host", code)
        self.assertNotIn("docker.sock", code)
        self.assertIn("BRANCH_CACHE_ENTRY_MODE: validate", text)
        self.assertIn('ENABLE_BRANCH_CACHE_HTTP_HEALTH: "false"', text)
        self.assertIn('ENABLE_BRANCH_CACHE_HTTP_METRICS: "false"', text)
        self.assertIn("branch_cache_data:/var/cache/ifilm-branch", text)
        self.assertIn("tmpfs:", text)
        self.assertIn("ifilm.compose.profile: lab-only", text)

    def test_dockerfile_nonroot_and_no_secrets(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        code = "\n".join(code_lines)
        self.assertIn("USER 10001:10001", text)
        self.assertIn("requirements-branch-cache.txt", text)
        self.assertNotIn("EDGE_GRANT_PRIVATE", code)
        self.assertNotIn("POSTGRES_PASSWORD", code)
        self.assertNotIn("JWT_SECRET=", code)
        self.assertIn("ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT=false", text)
        self.assertIn("BRANCH_CACHE_BIND_HOST=127.0.0.1", text)
        self.assertNotRegex(code, r"(?m)^EXPOSE\b")
        self.assertIn("STOPSIGNAL SIGTERM", text)
        self.assertNotIn("ffmpeg", code.lower())
        self.assertNotIn("gosu", code.lower())

    def test_entrypoint_refuses_public_bind(self):
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", text)
        self.assertIn("refusing public bind", text)
        self.assertIn("--validate-only", text)
        self.assertIn("asgi:create_app", text)

    def test_requirements_exclude_data_stores(self):
        lines = [
            ln.strip().lower()
            for ln in REQS.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        joined = "\n".join(lines)
        for needle in ("psycopg", "asyncpg", "sqlalchemy", "redis", "boto3", "alembic", "arq", "pyrad"):
            self.assertNotIn(needle, joined)

    def test_installer_and_security_flags_default_false(self):
        inst = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT=false", inst)
        sec = SECURITY.read_text(encoding="utf-8")
        self.assertIn("`ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT=false`", sec)

    def test_release_workflow_does_not_publish_branch_image(self):
        text = RELEASE_WF.read_text(encoding="utf-8")
        self.assertNotIn("Dockerfile.branch-cache", text)
        self.assertNotIn("branch-cache-lab", text)
        refs = IMAGE_REFS.read_text(encoding="utf-8")
        self.assertNotIn("branch-cache", refs)

    def test_lab_fixtures_public_key_only(self):
        pem = (ROOT / "packaging/compose/lab-fixtures/public.pem").read_text(encoding="utf-8")
        self.assertIn("BEGIN PUBLIC KEY", pem)
        self.assertNotIn("PRIVATE KEY", pem)
        origin = ROOT / "packaging/compose/lab-fixtures/origin/asset-1/pkg-1/master.m3u8"
        self.assertTrue(origin.is_file())


if __name__ == "__main__":
    unittest.main()
