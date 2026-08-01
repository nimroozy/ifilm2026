#!/usr/bin/env python3
"""Unit tests for update-agent handlers (no Docker)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging" / "update-agent"))

import agent  # noqa: E402


class UpdateAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        agent.IFILM_HOME = base / "opt"
        agent.IFILM_ETC = base / "etc"
        agent.IFILM_VAR = base / "var"
        agent.STATE_DIR = agent.IFILM_VAR / "update-agent"
        agent.LOCK_FILE = agent.STATE_DIR / "update.lock"
        agent.JOBS_DIR = agent.STATE_DIR / "jobs"
        agent.COMPOSE_FILE = agent.IFILM_HOME / "current" / "packaging" / "compose" / "docker-compose.production.yml"
        agent.ENV_FILE = agent.IFILM_ETC / "ifilm.env"
        agent.PUBLIC_KEY = agent.IFILM_HOME / "current" / "packaging" / "keys" / "release-signing.pub"
        agent.SHARED_SECRET = "unit-secret"
        agent.IFILM_HOME.mkdir(parents=True)
        (agent.IFILM_HOME / "current").mkdir(parents=True)
        agent.COMPOSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        agent.COMPOSE_FILE.write_text("name: ifilm\n", encoding="utf-8")
        agent.ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        agent.ENV_FILE.write_text("APP_ENV=production\n", encoding="utf-8")
        os.chmod(agent.ENV_FILE, 0o600)
        agent.PUBLIC_KEY.parent.mkdir(parents=True, exist_ok=True)
        agent.PUBLIC_KEY.write_text("dummy\n", encoding="utf-8")
        (agent.IFILM_HOME / "current" / "release-manifest.json").write_text(
            json.dumps(
                {
                    "version": "0.1.0-test",
                    "commit_sha": "aaa",
                    "channel": "stable",
                    "migration_head": "011_system_updates",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_current_version(self) -> None:
        result = agent.get_current_version({})
        self.assertEqual(result["version"], "0.1.0-test")

    def test_secret_required(self) -> None:
        with self.assertRaises(agent.AgentError):
            agent._require_secret({})

    def test_invalid_command_rejected(self) -> None:
        self.assertNotIn("shell", agent.ALLOWED_COMMANDS)
        self.assertNotIn("exec", agent.ALLOWED_COMMANDS)

    def test_check_excludes_prerelease_on_stable(self) -> None:
        releases = [
            {
                "draft": False,
                "prerelease": True,
                "tag_name": "v0.2.0-beta",
                "published_at": "2026-08-02T00:00:00Z",
                "body": "beta",
                "assets": [],
            },
            {
                "draft": False,
                "prerelease": False,
                "tag_name": "v0.1.1-test",
                "published_at": "2026-08-01T00:00:00Z",
                "body": "stable",
                "assets": [
                    {
                        "name": "release-manifest.json",
                        "browser_download_url": "https://github.com/nimroozy/ifilm2026/releases/download/v0.1.1-test/release-manifest.json",
                    },
                    {
                        "name": "release-manifest.json.sig",
                        "browser_download_url": "https://github.com/nimroozy/ifilm2026/releases/download/v0.1.1-test/release-manifest.json.sig",
                    },
                    {
                        "name": "ifilm-0.1.1-test.tar.gz",
                        "browser_download_url": "https://github.com/nimroozy/ifilm2026/releases/download/v0.1.1-test/ifilm-0.1.1-test.tar.gz",
                    },
                ],
            },
        ]

        class Resp:
            def read(self) -> bytes:
                return json.dumps(releases).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch("urllib.request.urlopen", return_value=Resp()):
            result = agent.check_latest_release({"channel": "stable"})
        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest"]["version"], "0.1.1-test")
        self.assertFalse(result["latest"]["prerelease"])

    def test_preflight_lock(self) -> None:
        agent.STATE_DIR.mkdir(parents=True, exist_ok=True)
        agent.LOCK_FILE.write_text("{}", encoding="utf-8")
        with mock.patch.object(agent, "_run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="10\n", stderr="")
            result = agent.run_preflight({})
        self.assertFalse(result["ok"])
        names = {c["name"]: c["passed"] for c in result["checks"]}
        self.assertFalse(names["lock_free"])


if __name__ == "__main__":
    unittest.main()
