#!/usr/bin/env bash
# Build, sign, and publish a disposable test GitHub prerelease.
# Private key path via IFILM_RELEASE_SIGNING_KEY_FILE (never echoed).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:?version required e.g. 0.1.0-test}"
TAG="v${VERSION}"
CHANNEL="${IFILM_RELEASE_CHANNEL:-staging}"
KEY_FILE="${IFILM_RELEASE_SIGNING_KEY_FILE:?IFILM_RELEASE_SIGNING_KEY_FILE required}"
[[ -f "$KEY_FILE" ]] || { echo "missing key file" >&2; exit 1; }
DIST="$(mktemp -d /tmp/ifilm-relbuild-XXXXXX)"
trap 'rm -rf "$DIST"' EXIT

STAGE="$DIST/stage/ifilm"
mkdir -p "$STAGE"
rsync -a \
  --exclude .git \
  --exclude node_modules \
  --exclude '**/__pycache__' \
  --exclude '**/.venv' \
  --exclude 'app/frontend/dist' \
  --exclude 'deploy/staging/.env.staging' \
  --exclude 'deploy/staging/.env.staging.credentials' \
  --exclude 'deploy/staging/backups' \
  "$ROOT/" "$STAGE/"

# Embed release identity into package
printf '%s\n' "$VERSION" >"$STAGE/packaging/VERSION"
printf '%s\n' "$(git -C "$ROOT" rev-parse HEAD)" >"$STAGE/packaging/COMMIT_SHA"

ARCHIVE="$DIST/ifilm-${VERSION}.tar.gz"
# Flat archive root (packaging/, app/, install.sh, ...) so /opt/ifilm/current/packaging works.
tar -C "$STAGE" -czf "$ARCHIVE" .

# Optional local image build for digest pinning (best effort)
BACKEND_DIGEST=""
if docker build -f "$ROOT/app/backend/Dockerfile.staging" -t "ghcr.io/nimroozy/ifilm2026/backend-api:${VERSION}" "$ROOT/app/backend" >/tmp/ifilm-docker-build.log 2>&1; then
  BACKEND_DIGEST="$(docker image inspect --format='{{.Id}}' "ghcr.io/nimroozy/ifilm2026/backend-api:${VERSION}" | sed 's/^sha256:/sha256:/')"
fi

ARGS=(
  --version "$VERSION"
  --channel "$CHANNEL"
  --archive "$ARCHIVE"
  --migration-head "$(cd "$ROOT/app/backend" && alembic heads 2>/dev/null | awk '{print $1}' | head -1)"
  --minimum-version "0.1.0"
  --database-backup-required
  --rollback-supported
  --out "$DIST/release-manifest.json"
)
if [[ -n "$BACKEND_DIGEST" ]]; then
  ARGS+=(--image-digest "backend-api=${BACKEND_DIGEST}")
fi
python3 "$ROOT/packaging/release/build_manifest.py" "${ARGS[@]}"
# Annotate rollback classification for test releases
python3 - <<PY
import json
from pathlib import Path
p = Path("$DIST/release-manifest.json")
data = json.loads(p.read_text())
data["rollback_compatibility"] = "application_only"
data["estimated_downtime_seconds"] = 120
p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY

python3 "$ROOT/packaging/release/sign_manifest.py" \
  --manifest "$DIST/release-manifest.json" \
  --key-file "$KEY_FILE" \
  --signature-out "$DIST/release-manifest.json.sig"

(
  cd "$DIST"
  sha256sum "ifilm-${VERSION}.tar.gz" release-manifest.json > SHA256SUMS
)

NOTES_FILE="$DIST/notes.md"
cat >"$NOTES_FILE" <<EOF
## ${TAG}

Disposable verification prerelease for installer/self-update.

- channel: ${CHANNEL}
- commit: $(git -C "$ROOT" rev-parse HEAD)
- migration head: see release-manifest.json
- rollback: application_only (DB restore not automatic)

Do not use in production.
EOF

# Delete existing release/tag if present (disposable re-publish)
gh release delete "$TAG" --yes 2>/dev/null || true
git -C "$ROOT" push origin ":refs/tags/${TAG}" 2>/dev/null || true
git -C "$ROOT" tag -f "$TAG" HEAD
git -C "$ROOT" push origin "$TAG"

gh release create "$TAG" \
  --prerelease \
  --title "$TAG" \
  --notes-file "$NOTES_FILE" \
  "$DIST/ifilm-${VERSION}.tar.gz" \
  "$DIST/release-manifest.json" \
  "$DIST/release-manifest.json.sig" \
  "$DIST/SHA256SUMS"

echo "PUBLISHED ${TAG}"
gh release view "$TAG" --json url,tagName,isPrerelease,assets --jq '{url,tagName,isPrerelease,assets:[.assets[].name]}'
