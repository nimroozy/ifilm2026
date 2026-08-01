"""Validate and normalize immutable GHCR image references for releases."""

from __future__ import annotations

import re
from typing import Any

REPO_PREFIX = "ghcr.io/nimroozy/ifilm2026"
REQUIRED_IMAGES = ("backend-api", "frontend")
# Workers reuse backend-api; they are not a distinct registry image.
WORKER_ALIASES = frozenset({"media-processing-worker", "publishing-worker", "backend"})
DIGEST_REF_RE = re.compile(
    rf"^{re.escape(REPO_PREFIX)}/(?P<name>backend-api|frontend)@sha256:(?P<digest>[a-f0-9]{{64}})$"
)
SHA256_ONLY_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
MUTABLE_TAG_RE = re.compile(r":(latest|main|master|staging|dev|edge)(?:@|$)")


class ImageRefError(ValueError):
    """Raised when an image digest reference is missing or unsafe."""


def is_immutable_registry_ref(ref: str) -> bool:
    return bool(DIGEST_REF_RE.match((ref or "").strip()))


def normalize_image_ref(name: str, value: str) -> str:
    """Accept full registry digest refs; reject mutable tags and local-only IDs."""
    ref = (value or "").strip()
    if not ref:
        raise ImageRefError(f"missing image digest for {name}")
    if MUTABLE_TAG_RE.search(ref) and "@sha256:" not in ref:
        raise ImageRefError(f"mutable-only tag rejected for {name}: {ref}")
    if is_immutable_registry_ref(ref):
        matched = DIGEST_REF_RE.match(ref)
        assert matched is not None
        if matched.group("name") != name:
            raise ImageRefError(f"image name mismatch for {name}: {ref}")
        return ref
    # Reject bare docker image IDs / RepoDigests without repository path.
    if SHA256_ONLY_RE.match(ref):
        raise ImageRefError(
            f"local or bare digest rejected for {name}; require full "
            f"{REPO_PREFIX}/{name}@sha256:... reference"
        )
    if "@sha256:" in ref and not ref.startswith(f"{REPO_PREFIX}/"):
        raise ImageRefError(f"non-GHCR digest reference rejected for {name}: {ref}")
    if ":" in ref and "@sha256:" not in ref:
        raise ImageRefError(f"mutable tag without digest rejected for {name}: {ref}")
    raise ImageRefError(f"malformed image digest for {name}: {ref}")


def validate_image_digests(
    digests: dict[str, Any] | None, *, require_all: bool = True
) -> dict[str, str]:
    """Validate manifest image_digests map; return normalized refs."""
    data = digests or {}
    if not isinstance(data, dict):
        raise ImageRefError("image_digests must be an object")
    out: dict[str, str] = {}
    for name in REQUIRED_IMAGES:
        if name not in data or not data[name]:
            if require_all:
                raise ImageRefError(f"missing required image digest: {name}")
            continue
        out[name] = normalize_image_ref(name, str(data[name]))
    for name, value in data.items():
        if name in REQUIRED_IMAGES:
            continue
        if name in WORKER_ALIASES:
            # Workers must resolve to the backend-api immutable digest.
            out[name] = normalize_image_ref("backend-api", str(value))
            continue
        raise ImageRefError(f"unexpected image digest key: {name}")
    return out


def env_vars_from_digests(digests: dict[str, str]) -> dict[str, str]:
    validated = validate_image_digests(digests, require_all=True)
    return {
        "IFILM_IMAGE_BACKEND_API": validated["backend-api"],
        "IFILM_IMAGE_FRONTEND": validated["frontend"],
    }
