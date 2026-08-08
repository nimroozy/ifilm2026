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


def _volume_targets(service_body: str) -> set[str]:
    targets: set[str] = set()
    in_volumes = False
    for line in service_body.splitlines():
        if re.match(r"^    volumes:\s*$", line):
            in_volumes = True
            continue
        if in_volumes:
            if re.match(r"^    [A-Za-z0-9_-]+:", line):
                break
            # Short syntax: source:target[:mode]
            m = re.search(r":(/data/media/[A-Za-z0-9_-]+)(?::|$)", line)
            if m:
                targets.add(m.group(1))
                continue
            # Long syntax: target: /data/media/...
            m = re.search(r"^\s+target:\s*(/data/media/[A-Za-z0-9_-]+)\s*$", line)
            if m:
                targets.add(m.group(1))
    return targets


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

    def test_backend_api_still_mounts_upload_categories_for_writes(self) -> None:
        prod = ROOT / "packaging/compose/docker-compose.production.yml"
        staging = ROOT / "deploy/staging/docker-compose.staging.yml"
        for compose, service in ((prod, "backend-api"), (staging, "backend-api")):
            with self.subTest(compose=compose.name):
                body = _service_block(compose.read_text(), service)
                targets = _volume_targets(body)
                for category in UPLOAD_CATEGORIES:
                    self.assertIn(
                        f"/data/media/{category}",
                        targets,
                        f"{compose.name} {service} missing {category}",
                    )


if __name__ == "__main__":
    unittest.main()
