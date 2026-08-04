#!/usr/bin/env python3
"""Recovery matrix A–G for transactional updater (disposable host simulation).

These tests exercise the agent state machine without requiring a live GHCR pull.
They are the automated stand-in for disposable Ubuntu 24.04 physical proofs of:
  A stable→stable, B RC→stable, C health failure, D compose conflict,
  E API restart / stale job, F interrupted env write, G rollback consistency.
"""

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

STABLE_BE = (
    "ghcr.io/nimroozy/ifilm2026/backend-api@"
    "sha256:1111111111111111111111111111111111111111111111111111111111111111"
)
STABLE_FE = (
    "ghcr.io/nimroozy/ifilm2026/frontend@"
    "sha256:2222222222222222222222222222222222222222222222222222222222222222"
)
RC_BE = (
    "ghcr.io/nimroozy/ifilm2026/backend-api@"
    "sha256:3333333333333333333333333333333333333333333333333333333333333333"
)
RC_FE = (
    "ghcr.io/nimroozy/ifilm2026/frontend@"
    "sha256:4444444444444444444444444444444444444444444444444444444444444444"
)
NEXT_BE = (
    "ghcr.io/nimroozy/ifilm2026/backend-api@"
    "sha256:5555555555555555555555555555555555555555555555555555555555555555"
)
NEXT_FE = (
    "ghcr.io/nimroozy/ifilm2026/frontend@"
    "sha256:6666666666666666666666666666666666666666666666666666666666666666"
)


def _man(version: str, be: str, fe: str, channel: str = "stable") -> dict:
    return {
        "version": version,
        "commit_sha": "abc",
        "channel": channel,
        "migration_head": "014_tmdb_demo_metadata",
        "image_digests": {"backend-api": be, "frontend": fe},
    }


class RecoveryMatrixTests(unittest.TestCase):
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
        agent.IFILM_HOME.mkdir(parents=True)
        agent.ENV_FILE.parent.mkdir(parents=True)
        agent.STATE_DIR.mkdir(parents=True)
        agent.ENV_FILE.write_text(
            "APP_ENV=production\nUPDATE_CHANNEL=stable\n"
            f"IFILM_IMAGE_BACKEND_API={STABLE_BE}\nIFILM_IMAGE_FRONTEND={STABLE_FE}\n"
            "JWT_SECRET=preserve\nPOSTGRES_PASSWORD=preserve\n",
            encoding="utf-8",
        )
        os.chmod(agent.ENV_FILE, 0o600)
        rel = agent.IFILM_HOME / "releases" / "v1.2.0"
        rel.mkdir(parents=True)
        (rel / "packaging" / "compose").mkdir(parents=True)
        (rel / "packaging" / "compose" / "docker-compose.production.yml").write_text(
            "name: ifilm\n", encoding="utf-8"
        )
        (rel / "release-manifest.json").write_text(
            json.dumps(_man("1.2.0", STABLE_BE, STABLE_FE)), encoding="utf-8"
        )
        (agent.IFILM_HOME / "current").symlink_to(rel)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_A_stable_to_stable_env_and_symlink(self) -> None:
        dest = agent.IFILM_HOME / "releases" / "v1.2.1"
        dest.mkdir(parents=True)
        (dest / "packaging" / "compose").mkdir(parents=True)
        (dest / "packaging" / "compose" / "docker-compose.production.yml").write_text(
            "name: ifilm\n", encoding="utf-8"
        )
        (dest / "release-manifest.json").write_text(
            json.dumps(_man("1.2.1", NEXT_BE, NEXT_FE)), encoding="utf-8"
        )
        agent._apply_image_digests(_man("1.2.1", NEXT_BE, NEXT_FE))
        agent._switch_current(dest)
        agent._upsert_env("UPDATE_CHANNEL", "stable")
        self.assertEqual(agent._read_env_value("IFILM_IMAGE_BACKEND_API"), NEXT_BE)
        self.assertEqual((agent.IFILM_HOME / "current").resolve(), dest.resolve())
        self.assertIn("JWT_SECRET=preserve", agent.ENV_FILE.read_text(encoding="utf-8"))
        self.assertEqual(agent._read_env_value("UPDATE_CHANNEL"), "stable")

    def test_B_rc_to_stable_clears_candidate_digests(self) -> None:
        agent._upsert_env_vars(
            {
                "IFILM_IMAGE_BACKEND_API": RC_BE,
                "IFILM_IMAGE_FRONTEND": RC_FE,
                "UPDATE_CHANNEL": "beta",
            }
        )
        agent._apply_image_digests(_man("1.2.0", STABLE_BE, STABLE_FE))
        channel = agent._resolve_channel_after(
            {"restore_channel": "stable"}, "beta", _man("1.2.0", STABLE_BE, STABLE_FE)
        )
        agent._upsert_env("UPDATE_CHANNEL", channel)
        text = agent.ENV_FILE.read_text(encoding="utf-8")
        self.assertIn(STABLE_BE, text)
        self.assertNotIn(RC_BE, text)
        self.assertEqual(agent._read_env_value("UPDATE_CHANNEL"), "stable")

    def test_C_health_failure_restores_previous(self) -> None:
        prev = (agent.IFILM_HOME / "current").resolve()
        snap = agent._snapshot_env_image_state()
        # Simulate failed candidate mutation
        agent._upsert_env_vars(
            {"IFILM_IMAGE_BACKEND_API": RC_BE, "IFILM_IMAGE_FRONTEND": RC_FE, "UPDATE_CHANNEL": "beta"}
        )
        cand = agent.IFILM_HOME / "releases" / "v1.2.0-rc.1"
        cand.mkdir(parents=True)
        (cand / "packaging" / "compose").mkdir(parents=True)
        (cand / "packaging" / "compose" / "docker-compose.production.yml").write_text(
            "name: ifilm\n", encoding="utf-8"
        )
        (cand / "release-manifest.json").write_text(
            json.dumps(_man("1.2.0-rc.1", RC_BE, RC_FE, "beta")), encoding="utf-8"
        )
        agent._switch_current(cand)
        with mock.patch.object(agent, "_compose_pull_and_up"), mock.patch.object(
            agent, "_verify_four_way_digests", return_value={"consistent": True}
        ), mock.patch.object(agent, "_wait_healthy"):
            result = agent._perform_rollback_to(
                prev, job_id="health-fail", reason="health_check_failed", previous_env=snap
            )
        self.assertEqual(result["state"], "rolled_back")
        self.assertEqual((agent.IFILM_HOME / "current").resolve(), prev.resolve())
        self.assertEqual(agent._read_env_value("IFILM_IMAGE_BACKEND_API"), STABLE_BE)
        self.assertEqual(agent._read_env_value("UPDATE_CHANNEL"), "stable")

    def test_D_compose_project_name_stable(self) -> None:
        cmd = agent._compose_cmd(agent._compose_file_for(), "up", "-d")
        self.assertEqual(cmd[cmd.index("-p") + 1], "ifilm")

    def test_E_stale_job_cannot_clear_newer_target(self) -> None:
        agent._write_active_target("new", "1.2.1", str(agent.IFILM_HOME / "releases" / "v1.2.1"))
        agent._clear_active_target("stale-old")
        data = json.loads(agent._active_target_file().read_text(encoding="utf-8"))
        self.assertEqual(data["job_id"], "new")

    def test_F_interrupted_atomic_env_write(self) -> None:
        before = agent.ENV_FILE.read_text(encoding="utf-8")
        with mock.patch("os.replace", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                agent._upsert_env_vars({"IFILM_IMAGE_BACKEND_API": NEXT_BE})
        self.assertEqual(agent.ENV_FILE.read_text(encoding="utf-8"), before)

    def test_G_rollback_four_way_target(self) -> None:
        prev = (agent.IFILM_HOME / "current").resolve()
        agent._previous_release_file().write_text(str(prev), encoding="utf-8")
        agent._previous_env_file().write_text(json.dumps(agent._snapshot_env_image_state()), encoding="utf-8")
        with mock.patch.object(agent, "_compose_pull_and_up") as up, mock.patch.object(
            agent, "_verify_four_way_digests", return_value={"backend-api": "x", "frontend": "y", "consistent": True}
        ) as verify, mock.patch.object(agent, "_wait_healthy"):
            result = agent.rollback_last_update({"job_id": "g1", "reason": "admin"})
        self.assertEqual(result["state"], "rolled_back")
        up.assert_called()
        verify.assert_called()
        self.assertEqual(agent._read_env_value("IFILM_IMAGE_BACKEND_API"), STABLE_BE)


if __name__ == "__main__":
    unittest.main()
