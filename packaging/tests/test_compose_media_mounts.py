"""Compose contract: media-processing-worker must see API upload categories.

Run: python3 packaging/tests/test_compose_media_mounts.py -v

Does not require PyYAML — parses service volume lines under the worker/API blocks.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

UPLOAD_CATEGORIES = ("originals", "trailers", "subtitles", "posters", "backdrops")

COMPOSE_FILES = (
    ROOT / "packaging/compose/docker-compose.production.yml",
    ROOT / "deploy/staging/docker-compose.staging.yml",
    ROOT / "docker-compose.yml",
)

# service name for the HTTP API in each compose file
API_SERVICE_BY_COMPOSE = {
    "docker-compose.production.yml": "backend-api",
    "docker-compose.staging.yml": "backend-api",
    "docker-compose.yml": "api",
}


def _service_block(text: str, service: str) -> str:
    """Return the indented body of `service:` until the next top-level service key."""
    pattern = re.compile(
        rf"(?m)^  {re.escape(service)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        re.S,
    )
    match = pattern.search(text)
    if not match:
        raise AssertionError(f"service {service!r} not found")
    return match.group(1)


def _volume_entries(service_body: str) -> list[tuple[str, str | None]]:
    """Return (target, mode) for /data/media/* volume mounts."""
    entries: list[tuple[str, str | None]] = []
    in_volumes = False
    pending_target: str | None = None
    for line in service_body.splitlines():
        if re.match(r"^    volumes:\s*$", line):
            in_volumes = True
            continue
        if in_volumes:
            if re.match(r"^    [A-Za-z0-9_-]+:", line):
                break
            m = re.search(r":(/data/media/[A-Za-z0-9_-]+)(?::([A-Za-z]+))?$", line.strip())
            if m and not line.strip().startswith("target:"):
                entries.append((m.group(1), m.group(2)))
                continue
            m = re.search(r"^\s+target:\s*(/data/media/[A-Za-z0-9_-]+)\s*$", line)
            if m:
                pending_target = m.group(1)
                continue
            if pending_target and re.search(r"^\s+read_only:\s*true\s*$", line):
                entries.append((pending_target, "ro"))
                pending_target = None
                continue
            if pending_target and re.match(r"^\s+\w+:", line):
                # long-syntax entry without read_only
                if "read_only" not in line:
                    entries.append((pending_target, None))
                pending_target = None
    if pending_target:
        entries.append((pending_target, None))
    return entries


def _volume_targets(service_body: str) -> set[str]:
    return {target for target, _mode in _volume_entries(service_body)}


def _volume_modes(service_body: str) -> dict[str, str | None]:
    modes: dict[str, str | None] = {}
    for target, mode in _volume_entries(service_body):
        modes[target] = mode
    return modes


class ComposeMediaMountTests(unittest.TestCase):
    def test_media_processing_worker_mounts_all_upload_categories(self) -> None:
        for compose in COMPOSE_FILES:
            with self.subTest(compose=str(compose.relative_to(ROOT))):
                self.assertTrue(compose.is_file(), compose)
                body = _service_block(compose.read_text(), "media-processing-worker")
                worker_targets = _volume_targets(body)
                for category in UPLOAD_CATEGORIES:
                    expected = f"/data/media/{category}"
                    self.assertIn(
                        expected,
                        worker_targets,
                        f"{compose.relative_to(ROOT)}: media-processing-worker missing "
                        f"mount {expected}. Have: {sorted(worker_targets)}",
                    )

    def test_worker_source_categories_are_read_only(self) -> None:
        for compose in COMPOSE_FILES:
            with self.subTest(compose=str(compose.relative_to(ROOT))):
                body = _service_block(compose.read_text(), "media-processing-worker")
                modes = _volume_modes(body)
                for category in UPLOAD_CATEGORIES:
                    target = f"/data/media/{category}"
                    self.assertEqual(
                        modes.get(target),
                        "ro",
                        f"{compose.relative_to(ROOT)}: worker {target} must be :ro "
                        f"(got {modes.get(target)!r})",
                    )

    def test_api_and_worker_share_same_upload_targets(self) -> None:
        for compose in COMPOSE_FILES:
            with self.subTest(compose=str(compose.relative_to(ROOT))):
                text = compose.read_text()
                api_service = API_SERVICE_BY_COMPOSE[compose.name]
                api_targets = _volume_targets(_service_block(text, api_service))
                worker_targets = _volume_targets(
                    _service_block(text, "media-processing-worker")
                )
                for category in UPLOAD_CATEGORIES:
                    expected = f"/data/media/{category}"
                    self.assertIn(expected, api_targets, f"{compose.name} API missing {expected}")
                    self.assertIn(
                        expected, worker_targets, f"{compose.name} worker missing {expected}"
                    )

    def test_media_processing_worker_healthcheck_covers_mounts(self) -> None:
        for compose in COMPOSE_FILES:
            with self.subTest(compose=str(compose.relative_to(ROOT))):
                text = compose.read_text()
                body = _service_block(text, "media-processing-worker")
                self.assertIn(
                    "healthcheck:",
                    body,
                    f"{compose.relative_to(ROOT)}: media-processing-worker missing healthcheck",
                )
                self.assertIn(
                    "--healthcheck",
                    body,
                    f"{compose.relative_to(ROOT)}: healthcheck must run "
                    "python -m app.workers.media_processing --healthcheck",
                )
                # Must override backend-api image HEALTHCHECK (curl :8000).
                self.assertNotIn(
                    "curl",
                    body.lower(),
                    f"{compose.relative_to(ROOT)}: worker healthcheck must not curl API :8000",
                )
                self.assertIn("app.workers.media_processing", body)

    def test_release_compose_tree_has_no_media_categories_hotfix_override(self) -> None:
        override = ROOT / "packaging/compose/docker-compose.media-categories.override.yml"
        self.assertFalse(
            override.exists(),
            "signed releases must not ship docker-compose.media-categories.override.yml; "
            "installer/update-agent use production.yml only and delete leftovers on activate",
        )

    def test_backend_api_still_mounts_upload_categories_for_writes(self) -> None:
        for compose in COMPOSE_FILES:
            with self.subTest(compose=str(compose.relative_to(ROOT))):
                api_service = API_SERVICE_BY_COMPOSE[compose.name]
                body = _service_block(compose.read_text(), api_service)
                targets = _volume_targets(body)
                for category in UPLOAD_CATEGORIES:
                    self.assertIn(
                        f"/data/media/{category}",
                        targets,
                        f"{compose.name} {api_service} missing {category}",
                    )


if __name__ == "__main__":
    unittest.main()
