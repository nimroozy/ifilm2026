#!/usr/bin/env python3
"""Unit tests for transactional update-agent handlers (no Docker required)."""

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

BACKEND_A = (
    "ghcr.io/nimroozy/ifilm2026/backend-api@"
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)
FRONTEND_A = (
    "ghcr.io/nimroozy/ifilm2026/frontend@"
    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)
BACKEND_B = (
    "ghcr.io/nimroozy/ifilm2026/backend-api@"
    "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
)
FRONTEND_B = (
    "ghcr.io/nimroozy/ifilm2026/frontend@"
    "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
)


def _manifest(version: str, backend: str, frontend: str) -> dict:
    return {
        "version": version,
        "commit_sha": "deadbeef",
        "channel": "stable",
        "migration_head": "014_tmdb_demo_metadata",
        "image_digests": {"backend-api": backend, "frontend": frontend},
        "artifacts": [{"name": f"ifilm-{version}.tar.gz", "sha256": "0" * 64}],
    }


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
        agent.COMPOSE_FILE = (
            agent.IFILM_HOME / "current" / "packaging" / "compose" / "docker-compose.production.yml"
        )
        agent.ENV_FILE = agent.IFILM_ETC / "ifilm.env"
        agent.PUBLIC_KEY = agent.IFILM_HOME / "current" / "packaging" / "keys" / "release-signing.pub"
        agent.SHARED_SECRET = "unit-secret"
        agent.IFILM_HOME.mkdir(parents=True)
        (agent.IFILM_HOME / "current").mkdir(parents=True)
        agent.COMPOSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        agent.COMPOSE_FILE.write_text("name: ifilm\n", encoding="utf-8")
        agent.ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        agent.ENV_FILE.write_text(
            "APP_ENV=production\n"
            "UPDATE_CHANNEL=stable\n"
            f"IFILM_IMAGE_BACKEND_API={BACKEND_A}\n"
            f"IFILM_IMAGE_FRONTEND={FRONTEND_A}\n"
            "JWT_SECRET=keep-me\n",
            encoding="utf-8",
        )
        os.chmod(agent.ENV_FILE, 0o600)
        agent.PUBLIC_KEY.parent.mkdir(parents=True, exist_ok=True)
        agent.PUBLIC_KEY.write_text("dummy\n", encoding="utf-8")
        (agent.IFILM_HOME / "current" / "release-manifest.json").write_text(
            json.dumps(_manifest("1.2.0", BACKEND_A, FRONTEND_A)),
            encoding="utf-8",
        )
        # Point current at a real release dir via symlink for rollback tests.
        v120 = agent.IFILM_HOME / "releases" / "v1.2.0"
        v120.mkdir(parents=True)
        (v120 / "packaging" / "compose").mkdir(parents=True)
        (v120 / "packaging" / "compose" / "docker-compose.production.yml").write_text(
            "name: ifilm\n", encoding="utf-8"
        )
        (v120 / "release-manifest.json").write_text(
            json.dumps(_manifest("1.2.0", BACKEND_A, FRONTEND_A)),
            encoding="utf-8",
        )
        current = agent.IFILM_HOME / "current"
        if current.exists() or current.is_symlink():
            if current.is_dir() and not current.is_symlink():
                import shutil

                shutil.rmtree(current)
            else:
                current.unlink()
        current.symlink_to(v120)
        agent.COMPOSE_FILE = (
            agent.IFILM_HOME / "current" / "packaging" / "compose" / "docker-compose.production.yml"
        )
        agent.PUBLIC_KEY = agent.IFILM_HOME / "current" / "packaging" / "keys" / "release-signing.pub"
        agent.PUBLIC_KEY.parent.mkdir(parents=True, exist_ok=True)
        agent.PUBLIC_KEY.write_text("dummy\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_current_version(self) -> None:
        result = agent.get_current_version({})
        self.assertEqual(result["version"], "1.2.0")

    def test_secret_required(self) -> None:
        with self.assertRaises(agent.AgentError):
            agent._require_secret({})

    def test_invalid_command_rejected(self) -> None:
        self.assertNotIn("shell", agent.ALLOWED_COMMANDS)
        self.assertIn("verify_installation", agent.ALLOWED_COMMANDS)

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

    def test_atomic_env_write_preserves_secrets(self) -> None:
        agent._upsert_env_vars(
            {
                "IFILM_IMAGE_BACKEND_API": BACKEND_B,
                "IFILM_IMAGE_FRONTEND": FRONTEND_B,
            }
        )
        text = agent.ENV_FILE.read_text(encoding="utf-8")
        self.assertIn(f"IFILM_IMAGE_BACKEND_API={BACKEND_B}", text)
        self.assertIn(f"IFILM_IMAGE_FRONTEND={FRONTEND_B}", text)
        self.assertIn("JWT_SECRET=keep-me", text)
        self.assertEqual(oct(agent.ENV_FILE.stat().st_mode & 0o777), "0o600")

    def test_interrupted_env_write_leaves_valid_file(self) -> None:
        """F: Interrupted write must not leave a partial env file."""
        original = agent.ENV_FILE.read_text(encoding="utf-8")

        def boom(*_a, **_k):
            raise OSError("simulated crash before replace")

        with mock.patch("os.replace", side_effect=boom):
            with self.assertRaises(OSError):
                agent._upsert_env_vars({"IFILM_IMAGE_BACKEND_API": BACKEND_B})
        # Original file remains intact and valid.
        self.assertEqual(agent.ENV_FILE.read_text(encoding="utf-8"), original)
        self.assertIn("JWT_SECRET=keep-me", original)
        self.assertIn(BACKEND_A, original)

    def test_removes_media_categories_hotfix_override_on_activate(self) -> None:
        compose_dir = agent.IFILM_HOME / "current" / "packaging" / "compose"
        compose_dir.mkdir(parents=True, exist_ok=True)
        compose = compose_dir / "docker-compose.production.yml"
        compose.write_text("services: {}\n", encoding="utf-8")
        override = compose_dir / agent.MEDIA_CATEGORIES_HOTFIX_OVERRIDE
        override.write_text("services: {}\n", encoding="utf-8")
        agent._remove_media_categories_hotfix_override(compose)
        self.assertFalse(override.exists())

    def test_compose_pull_and_up_uses_stable_project(self) -> None:
        def fake_run(argv, *, timeout=600, env=None):  # noqa: ARG001
            if argv[:2] == ["docker", "pull"]:
                return mock.Mock(returncode=0, stdout="pulled\n", stderr="")
            if argv[:3] == ["docker", "image", "inspect"]:
                ref = argv[-1]
                digest = ref.split("@", 1)[1]
                repo = ref.split("@", 1)[0]
                return mock.Mock(
                    returncode=0,
                    stdout=json.dumps([f"{repo}@{digest}"]),
                    stderr="",
                )
            if argv[:2] == ["docker", "compose"]:
                self.assertIn("-p", argv)
                self.assertEqual(argv[argv.index("-p") + 1], "ifilm")
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")
            if argv[:2] == ["docker", "ps"]:
                return mock.Mock(returncode=0, stdout="ifilm-backend-api-1\nifilm-frontend-1\n", stderr="")
            return mock.Mock(returncode=1, stdout="", stderr="unexpected")

        with mock.patch.object(agent, "_run", side_effect=fake_run):
            agent._compose_pull_and_up()

    def test_rc_digests_replaced_by_stable(self) -> None:
        """B: RC → stable update clears RC digests from env."""
        agent.ENV_FILE.write_text(
            "UPDATE_CHANNEL=beta\n"
            f"IFILM_IMAGE_BACKEND_API={BACKEND_A}\n"
            f"IFILM_IMAGE_FRONTEND={FRONTEND_A}\n"
            "JWT_SECRET=keep-me\n",
            encoding="utf-8",
        )
        os.chmod(agent.ENV_FILE, 0o600)
        manifest = _manifest("1.2.0", BACKEND_B, FRONTEND_B)
        agent._apply_image_digests(manifest)
        agent._upsert_env("UPDATE_CHANNEL", "stable")
        text = agent.ENV_FILE.read_text(encoding="utf-8")
        self.assertIn(BACKEND_B, text)
        self.assertNotIn(BACKEND_A.split("@")[1], text.split("IFILM_IMAGE_BACKEND_API=")[1].splitlines()[0])
        self.assertEqual(agent._read_env_value("UPDATE_CHANNEL"), "stable")
        self.assertIn("JWT_SECRET=keep-me", text)

    def test_atomic_symlink_switch(self) -> None:
        dest = agent.IFILM_HOME / "releases" / "v1.2.1"
        dest.mkdir(parents=True)
        (dest / "release-manifest.json").write_text("{}", encoding="utf-8")
        agent._switch_current(dest)
        self.assertEqual((agent.IFILM_HOME / "current").resolve(), dest.resolve())

    def test_rollback_restores_env_and_symlink(self) -> None:
        """C/G: rollback restores previous env + symlink."""
        prev = (agent.IFILM_HOME / "current").resolve()
        agent.STATE_DIR.mkdir(parents=True, exist_ok=True)
        agent._previous_release_file().write_text(str(prev), encoding="utf-8")
        agent._previous_env_file().write_text(
            json.dumps(
                {
                    "IFILM_IMAGE_BACKEND_API": BACKEND_A,
                    "IFILM_IMAGE_FRONTEND": FRONTEND_A,
                    "UPDATE_CHANNEL": "stable",
                }
            ),
            encoding="utf-8",
        )
        # Mutate to candidate digests + wrong symlink.
        candidate = agent.IFILM_HOME / "releases" / "v1.2.0-rc.1"
        candidate.mkdir(parents=True)
        (candidate / "packaging" / "compose").mkdir(parents=True)
        (candidate / "packaging" / "compose" / "docker-compose.production.yml").write_text(
            "name: ifilm\n", encoding="utf-8"
        )
        (candidate / "release-manifest.json").write_text(
            json.dumps(_manifest("1.2.0-rc.1", BACKEND_B, FRONTEND_B)),
            encoding="utf-8",
        )
        agent._switch_current(candidate)
        agent._upsert_env_vars(
            {
                "IFILM_IMAGE_BACKEND_API": BACKEND_B,
                "IFILM_IMAGE_FRONTEND": FRONTEND_B,
                "UPDATE_CHANNEL": "beta",
            }
        )

        with mock.patch.object(agent, "_compose_pull_and_up"), mock.patch.object(
            agent, "_verify_four_way_digests", return_value={"consistent": True}
        ), mock.patch.object(agent, "_wait_healthy"):
            result = agent.rollback_last_update({"job_id": "rb1", "reason": "test"})

        self.assertEqual(result["state"], "rolled_back")
        self.assertEqual((agent.IFILM_HOME / "current").resolve(), prev.resolve())
        self.assertEqual(agent._read_env_value("IFILM_IMAGE_BACKEND_API"), BACKEND_A)
        self.assertEqual(agent._read_env_value("UPDATE_CHANNEL"), "stable")

    def test_compose_conflict_scoped_cleanup(self) -> None:
        """D: conflict handling only removes ifilm project containers."""
        removed: list[str] = []

        def fake_run(argv, *, timeout=600, env=None):  # noqa: ARG001
            if argv[:2] == ["docker", "pull"]:
                return mock.Mock(returncode=0, stdout="", stderr="")
            if argv[:3] == ["docker", "image", "inspect"]:
                ref = argv[-1]
                digest = ref.split("@", 1)[1]
                repo = ref.split("@", 1)[0]
                return mock.Mock(returncode=0, stdout=json.dumps([f"{repo}@{digest}"]), stderr="")
            if argv[:2] == ["docker", "compose"] and "up" in argv and "backend-api" in argv:
                # First up fails with name conflict; second succeeds.
                if not getattr(fake_run, "failed_once", False):
                    fake_run.failed_once = True
                    return mock.Mock(returncode=1, stdout="", stderr="Conflict. The container name is already in use")
                return mock.Mock(returncode=0, stdout="up\n", stderr="")
            if argv[:2] == ["docker", "compose"]:
                return mock.Mock(returncode=0, stdout="", stderr="")
            if argv[:2] == ["docker", "ps"]:
                return mock.Mock(
                    returncode=0,
                    stdout="ifilm-backend-api-1\nunrelated-nginx\n",
                    stderr="",
                )
            if argv[:3] == ["docker", "rm", "-f"]:
                removed.append(argv[3])
                return mock.Mock(returncode=0, stdout="", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        fake_run.failed_once = False
        with mock.patch.object(agent, "_run", side_effect=fake_run):
            agent._compose_pull_and_up()
        self.assertTrue(all(name.startswith("ifilm-") for name in removed))
        self.assertNotIn("unrelated-nginx", removed)

    def test_stale_active_target_not_cleared_by_other_job(self) -> None:
        """E: stale job cannot clear a newer active target."""
        agent.STATE_DIR.mkdir(parents=True, exist_ok=True)
        agent._write_active_target("job-new", "1.2.1", "/opt/ifilm/releases/v1.2.1")
        agent._clear_active_target("job-old")
        self.assertTrue(agent._active_target_file().is_file())
        data = json.loads(agent._active_target_file().read_text(encoding="utf-8"))
        self.assertEqual(data["job_id"], "job-new")

    def test_verify_installation_reports_mismatch(self) -> None:
        with mock.patch.object(agent, "_compose_config_images", return_value={
            "backend-api": BACKEND_A,
            "frontend": FRONTEND_A,
        }), mock.patch.object(agent, "_running_service_digests", return_value={
            "backend-api": BACKEND_B.split("@", 1)[1],
            "frontend": FRONTEND_B.split("@", 1)[1],
        }), mock.patch.object(agent, "_migration_head", return_value="014_tmdb_demo_metadata"), mock.patch.object(
            agent, "_run", return_value=mock.Mock(returncode=0, stdout="ok", stderr="")
        ), mock.patch.object(agent, "_assert_no_duplicate_managed_containers"):
            result = agent.verify_installation({})
        self.assertFalse(result["ok"])
        self.assertTrue(result["digest_mismatch"])


if __name__ == "__main__":
    unittest.main()
