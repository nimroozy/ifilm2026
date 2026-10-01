"""ENABLE_ARTWORK_CDN_SYNC must be operator-configurable via Compose env.

Production previously hard-coded ENABLE_ARTWORK_CDN_SYNC: "false", which made
Admin artwork CDN impossible even when R2 credentials and public base were OK.

Installer-generated env must still default the flag to false (never auto-enable).
Sibling CDN/R2 kill-switches remain hard-coded off in production Compose.

Run: python3 packaging/tests/test_artwork_cdn_host_env.py -v
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
INSTALLER = ROOT / "packaging/installer/install_release.sh"

_INTERP = re.compile(
    r"ENABLE_ARTWORK_CDN_SYNC:\s*\$\{ENABLE_ARTWORK_CDN_SYNC:-false\}"
)
_HARD_FALSE = re.compile(r'ENABLE_ARTWORK_CDN_SYNC:\s*"false"')


def _backend_env_block(compose_text: str) -> str:
    """Return the production backend-api `&api_env` environment mapping body."""
    api = re.search(
        r"(?m)^  backend-api:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        compose_text,
        re.S,
    )
    assert api is not None, "backend-api service missing"
    env = re.search(
        r"(?m)^\s+environment:\s*&api_env\n((?:\s{6}.+\n)+)",
        api.group(1),
    )
    assert env is not None, "backend-api environment &api_env missing"
    return env.group(1)


class ArtworkCdnHostEnvTests(unittest.TestCase):
    def test_production_interpolates_artwork_cdn_flag(self):
        text = PROD.read_text(encoding="utf-8")
        block = _backend_env_block(text)
        self.assertRegex(block, _INTERP)
        self.assertIsNone(_HARD_FALSE.search(block))
        # Sibling kill-switches stay hard-coded off (not operator-interpolated).
        self.assertIn('ENABLE_CDN_SYNC: "false"', block)
        self.assertIn('ENABLE_OBJECT_STORAGE: "false"', block)
        self.assertIn('ENABLE_R2_HOT_TIER: "false"', block)
        self.assertNotIn("ENABLE_CDN_EDGE_ROUTING", text)

    def test_staging_and_local_interpolate_artwork_cdn_flag(self):
        for path in (STAGING, LOCAL):
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, _INTERP, msg=str(path))
            self.assertIsNone(_HARD_FALSE.search(text), msg=str(path))

    def test_installer_generated_env_defaults_artwork_cdn_off(self):
        text = INSTALLER.read_text(encoding="utf-8")
        # Literal assignment in generated env template — not ${...} expansion.
        self.assertRegex(text, r"(?m)^ENABLE_ARTWORK_CDN_SYNC=false$")
        self.assertRegex(text, r"(?m)^ENABLE_CDN_SYNC=false$")
        self.assertRegex(text, r"(?m)^ENABLE_OBJECT_STORAGE=false$")
        self.assertRegex(text, r"(?m)^ENABLE_R2_HOT_TIER=false$")

    def test_compose_config_passes_true_and_defaults_false(self):
        if shutil.which("docker") is None:
            self.skipTest("docker not available")

        base_env = {
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

        def _config(*, artwork: str | None) -> dict:
            env = os.environ.copy()
            env.update(base_env)
            env.pop("ENABLE_ARTWORK_CDN_SYNC", None)
            if artwork is not None:
                env["ENABLE_ARTWORK_CDN_SYNC"] = artwork
            with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
                env_file = fh.name
            env["IFILM_ENV_FILE"] = env_file
            try:
                proc = subprocess.run(
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
                self.assertEqual(proc.returncode, 0, proc.stderr)
                return json.loads(proc.stdout)
            finally:
                Path(env_file).unlink(missing_ok=True)

        unset_env = (_config(artwork=None).get("services") or {}).get(
            "backend-api", {}
        ).get("environment") or {}
        self.assertEqual(str(unset_env.get("ENABLE_ARTWORK_CDN_SYNC")).lower(), "false")

        false_env = (_config(artwork="false").get("services") or {}).get(
            "backend-api", {}
        ).get("environment") or {}
        self.assertEqual(str(false_env.get("ENABLE_ARTWORK_CDN_SYNC")).lower(), "false")

        true_env = (_config(artwork="true").get("services") or {}).get(
            "backend-api", {}
        ).get("environment") or {}
        self.assertEqual(str(true_env.get("ENABLE_ARTWORK_CDN_SYNC")).lower(), "true")
        # Sibling flags remain hard false even when artwork host capability is on.
        self.assertEqual(str(true_env.get("ENABLE_CDN_SYNC")).lower(), "false")
        self.assertEqual(str(true_env.get("ENABLE_OBJECT_STORAGE")).lower(), "false")
        self.assertEqual(str(true_env.get("ENABLE_R2_HOT_TIER")).lower(), "false")


if __name__ == "__main__":
    unittest.main()
