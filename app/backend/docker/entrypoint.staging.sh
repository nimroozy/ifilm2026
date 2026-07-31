#!/bin/sh
# Staging entrypoint: fix named-volume ownership, then drop to non-root.
set -eu

mkdir -p \
  /data/media/originals \
  /data/media/temp \
  /data/media/packages \
  /data/media/trailers \
  /data/media/subtitles \
  /data/media/posters \
  /data/media/backdrops \
  /data/artwork

# Named volumes are root-owned by default. RO mounts may fail chown — ignore.
chown -R ifilm:ifilm /data/media /data/artwork 2>/dev/null || true

exec gosu ifilm "$@"
