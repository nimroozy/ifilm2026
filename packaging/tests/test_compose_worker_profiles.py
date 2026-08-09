"""Compose worker profile safety (Train T0).

Canonical workers are always-on (explicit role labels).
Legacy ARQ worker must never appear in production/staging config and must be
profile-gated on local compose.

Run: python3 packaging/tests/test_compose_worker_profiles.py -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROD = ROOT / "packaging/compose/docker-compose.production.yml"
STAGING = ROOT / "deploy/staging/docker-compose.staging.yml"
LOCAL = ROOT / "docker-compose.yml"


def _service_block(text: str, service: str) -> str | None:
    pattern = re.compile(
        rf"(?m)^  {re.escape(service)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        re.S,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


def _has_arq_command(service_body: str) -> bool:
    return bool(re.search(r"\barq\b", service_body))


class ComposeWorkerProfileTests(unittest.TestCase):
    def test_production_has_canonical_workers_no_legacy_arq(self):
        text = PROD.read_text(encoding="utf-8")
        mp = _service_block(text, "media-processing-worker")
        pub = _service_block(text, "publishing-worker")
        self.assertIsNotNone(mp)
        self.assertIsNotNone(pub)
        assert mp is not None and pub is not None
        self.assertIn("ifilm.pipeline.role=canonical", mp.replace(" ", ""))
        self.assertIn("ifilm.pipeline.role=canonical", pub.replace(" ", ""))
        # No profiles on canonical workers — always-on for installer `up -d`.
        self.assertNotRegex(mp, r"(?m)^\s+profiles:")
        self.assertNotRegex(pub, r"(?m)^\s+profiles:")
        self.assertIsNone(_service_block(text, "worker"))
        self.assertNotIn("arq app.workers", text)
        self.assertIn('ENABLE_ENCODING: "false"', text)

    def test_staging_matches_production_worker_set(self):
        text = STAGING.read_text(encoding="utf-8")
        mp = _service_block(text, "media-processing-worker")
        pub = _service_block(text, "publishing-worker")
        self.assertIsNotNone(mp)
        self.assertIsNotNone(pub)
        assert mp is not None and pub is not None
        self.assertIn("ifilm.pipeline.role=canonical", mp.replace(" ", ""))
        self.assertIn("ifilm.pipeline.role=canonical", pub.replace(" ", ""))
        self.assertIsNone(_service_block(text, "worker"))
        self.assertNotIn("arq app.workers", text)
        self.assertIn('ENABLE_ENCODING: "false"', text)

    def test_local_legacy_worker_requires_profile(self):
        text = LOCAL.read_text(encoding="utf-8")
        worker = _service_block(text, "worker")
        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertTrue(_has_arq_command(worker))
        self.assertRegex(worker, r'profiles:\s*\[\s*"legacy-arq"\s*\]')
        self.assertIn("ifilm.pipeline.role=legacy", worker.replace(" ", "").replace('"', ""))

        mp = _service_block(text, "media-processing-worker")
        pub = _service_block(text, "publishing-worker")
        self.assertIsNotNone(mp)
        self.assertIsNotNone(pub)
        assert mp is not None and pub is not None
        self.assertIn("ifilm.pipeline.role=canonical", mp.replace(" ", ""))
        self.assertIn("ifilm.pipeline.role=canonical", pub.replace(" ", ""))
        # Dev remains usable: canonical workers stay always-on (no profile).
        self.assertNotRegex(mp, r"(?m)^\s+profiles:")
        self.assertNotRegex(pub, r"(?m)^\s+profiles:")

    def test_docker_compose_config_excludes_legacy_by_default(self):
        """If docker is available, `compose config` must not enable legacy worker."""
        if shutil.which("docker") is None:
            self.skipTest("docker not available")
        env = os.environ.copy()
        env.update(
            {
                "POSTGRES_DB": "ifilm",
                "POSTGRES_USER": "ifilm",
                "POSTGRES_PASSWORD": "x",
                "REDIS_PASSWORD": "x",
                "JWT_SECRET": "x" * 32,
                "PLAYBACK_TOKEN_SECRET": "x" * 32,
                "IFILM_IMAGE_BACKEND_API": (
                    "ghcr.io/nimroozy/ifilm2026/backend-api@"
                    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                ),
                "IFILM_IMAGE_FRONTEND": (
                    "ghcr.io/nimroozy/ifilm2026/frontend@"
                    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                ),
            }
        )
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
            env_file = fh.name
        env["IFILM_ENV_FILE"] = env_file
        try:
            prod = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(PROD),
                    "config",
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(ROOT),
            )
            self.assertEqual(prod.returncode, 0, prod.stderr)
            prod_cfg = json.loads(prod.stdout)
            services = prod_cfg.get("services") or {}
            self.assertIn("media-processing-worker", services)
            self.assertIn("publishing-worker", services)
            self.assertNotIn("worker", services)
            for name, svc in services.items():
                cmd = svc.get("command") or []
                if isinstance(cmd, str):
                    cmd_s = cmd
                else:
                    cmd_s = " ".join(str(c) for c in cmd)
                self.assertNotIn("arq", cmd_s, f"production service {name} runs arq")

            local = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(LOCAL),
                    "config",
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**env, "POSTGRES_PASSWORD": "x", "JWT_SECRET": "x" * 32},
                cwd=str(ROOT),
            )
            self.assertEqual(local.returncode, 0, local.stderr)
            local_cfg = json.loads(local.stdout)
            local_services = local_cfg.get("services") or {}
            self.assertNotIn(
                "worker",
                local_services,
                "legacy ARQ worker must not appear without --profile legacy-arq",
            )
            self.assertIn("media-processing-worker", local_services)
            self.assertIn("publishing-worker", local_services)

            # Accidental enable check: with profile, worker appears (proves gate works).
            legacy = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--profile",
                    "legacy-arq",
                    "-f",
                    str(LOCAL),
                    "config",
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**env, "POSTGRES_PASSWORD": "x", "JWT_SECRET": "x" * 32},
                cwd=str(ROOT),
            )
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            legacy_services = json.loads(legacy.stdout).get("services") or {}
            self.assertIn("worker", legacy_services)
        finally:
            Path(env_file).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
