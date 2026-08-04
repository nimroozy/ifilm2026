#!/usr/bin/env python3
"""Prove manifest/updater reject unsafe or mismatched image digests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging" / "release"))
sys.path.insert(0, str(ROOT / "packaging" / "update-agent"))

from image_refs import ImageRefError, validate_image_digests  # noqa: E402
import agent  # noqa: E402


GOOD_BACKEND = (
    "ghcr.io/nimroozy/ifilm2026/backend-api@"
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)
GOOD_FRONTEND = (
    "ghcr.io/nimroozy/ifilm2026/frontend@"
    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)


class ImageDigestValidationTests(unittest.TestCase):
    def test_rejects_missing_digest(self) -> None:
        with self.assertRaises(ImageRefError):
            validate_image_digests({"backend-api": GOOD_BACKEND}, require_all=True)

    def test_rejects_malformed_digest(self) -> None:
        with self.assertRaises(ImageRefError):
            validate_image_digests(
                {
                    "backend-api": "ghcr.io/nimroozy/ifilm2026/backend-api@sha256:deadbeef",
                    "frontend": GOOD_FRONTEND,
                },
                require_all=True,
            )

    def test_rejects_bare_local_image_id(self) -> None:
        with self.assertRaises(ImageRefError):
            validate_image_digests(
                {
                    "backend-api": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "frontend": GOOD_FRONTEND,
                },
                require_all=True,
            )

    def test_rejects_mutable_only_tags(self) -> None:
        with self.assertRaises(ImageRefError):
            validate_image_digests(
                {
                    "backend-api": "ghcr.io/nimroozy/ifilm2026/backend-api:latest",
                    "frontend": GOOD_FRONTEND,
                },
                require_all=True,
            )
        with self.assertRaises(ImageRefError):
            validate_image_digests(
                {
                    "backend-api": GOOD_BACKEND,
                    "frontend": "ghcr.io/nimroozy/ifilm2026/frontend:main",
                },
                require_all=True,
            )

    def test_accepts_immutable_registry_refs(self) -> None:
        out = validate_image_digests(
            {
                "backend-api": GOOD_BACKEND,
                "frontend": GOOD_FRONTEND,
                "media-processing-worker": GOOD_BACKEND,
            },
            require_all=True,
        )
        self.assertEqual(out["backend-api"], GOOD_BACKEND)
        self.assertEqual(out["frontend"], GOOD_FRONTEND)


class UpdaterDigestBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        agent.IFILM_HOME = base / "opt"
        agent.IFILM_ETC = base / "etc"
        agent.IFILM_VAR = base / "var"
        agent.STATE_DIR = agent.IFILM_VAR / "update-agent"
        agent.LOCK_FILE = agent.STATE_DIR / "update.lock"
        agent.JOBS_DIR = agent.STATE_DIR / "jobs"
        agent.ENV_FILE = agent.IFILM_ETC / "ifilm.env"
        agent.COMPOSE_FILE = (
            agent.IFILM_HOME / "current" / "packaging" / "compose" / "docker-compose.production.yml"
        )
        agent.IFILM_HOME.mkdir(parents=True)
        agent.ENV_FILE.parent.mkdir(parents=True)
        agent.ENV_FILE.write_text("APP_ENV=production\n", encoding="utf-8")
        agent.STATE_DIR.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_updater_refuses_mismatched_downloaded_digest(self) -> None:
        with mock.patch.object(agent, "_run") as run:
            run.return_value = mock.Mock(
                returncode=0,
                stdout=json.dumps(
                    [
                        "ghcr.io/nimroozy/ifilm2026/backend-api@sha256:"
                        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
                    ]
                ),
            )
            with self.assertRaises(agent.AgentError) as ctx:
                agent._verify_pulled_image(GOOD_BACKEND)
            self.assertEqual(ctx.exception.code, "image_digest_mismatch")

    def test_rollback_restores_previous_immutable_digests(self) -> None:
        prev = agent.IFILM_HOME / "releases" / "v0.1.0"
        curr = agent.IFILM_HOME / "releases" / "v0.1.1"
        prev.mkdir(parents=True)
        curr.mkdir(parents=True)
        prev_manifest = {
            "version": "0.1.0",
            "image_digests": {
                "backend-api": GOOD_BACKEND,
                "frontend": GOOD_FRONTEND,
            },
        }
        (prev / "release-manifest.json").write_text(
            json.dumps(prev_manifest), encoding="utf-8"
        )
        other_backend = (
            "ghcr.io/nimroozy/ifilm2026/backend-api@"
            "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
        )
        (curr / "release-manifest.json").write_text(
            json.dumps(
                {
                    "version": "0.1.1",
                    "image_digests": {
                        "backend-api": other_backend,
                        "frontend": GOOD_FRONTEND,
                    },
                }
            ),
            encoding="utf-8",
        )
        current_link = agent.IFILM_HOME / "current"
        current_link.symlink_to(curr)
        (agent.STATE_DIR / "previous_release").write_text(str(prev), encoding="utf-8")
        agent.ENV_FILE.write_text(
            "APP_ENV=production\n"
            "IFILM_IMAGE_BACKEND_API=bad\n"
            "IFILM_IMAGE_FRONTEND=bad\n",
            encoding="utf-8",
        )

        with mock.patch.object(agent, "_compose_pull_and_up") as pull_up, mock.patch.object(
            agent, "_verify_four_way_digests", return_value={"consistent": True}
        ), mock.patch.object(agent, "_wait_healthy"):
            pull_up.return_value = None
            result = agent.rollback_last_update({"job_id": "t1", "reason": "test"})

        self.assertEqual(result["state"], "rolled_back")
        env = agent.ENV_FILE.read_text(encoding="utf-8")
        self.assertIn(f"IFILM_IMAGE_BACKEND_API={GOOD_BACKEND}", env)
        self.assertIn(f"IFILM_IMAGE_FRONTEND={GOOD_FRONTEND}", env)
        self.assertEqual(current_link.resolve(), prev.resolve())


if __name__ == "__main__":
    unittest.main()
