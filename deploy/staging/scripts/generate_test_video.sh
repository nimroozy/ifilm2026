#!/usr/bin/env bash
# Generate a small legal H.264/AAC test video for staging smoke (never commit).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT_DIR="${STAGING_TEST_DIR:-$ROOT/deploy/staging/.tmp-smoke}"
OUT_FILE="${1:-$OUT_DIR/staging-smoke.mp4}"
# >= 45s so Continue Watching min threshold (30s) can be exercised.
DURATION="${STAGING_TEST_DURATION:-45}"

mkdir -p "$OUT_DIR"
rm -f "$OUT_FILE"
UNIQUE_TAG="${STAGING_TEST_UNIQUE:-$(date -u +%Y%m%d%H%M%S)-$$}"

# Unique drawtext so each generation has a distinct checksum (duplicate-upload guard).
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc=size=640x360:rate=25" \
  -f lavfi -i "sine=frequency=1000:sample_rate=48000" \
  -t "$DURATION" \
  -vf "drawtext=text='ifilm-staging-${UNIQUE_TAG}':x=10:y=10:fontsize=18:fontcolor=white" \
  -c:v libx264 -pix_fmt yuv420p -profile:v baseline -level 3.0 \
  -c:a aac -b:a 128k \
  -shortest \
  "$OUT_FILE"

PROBE_FILE="$OUT_DIR/ffprobe.json"
ffprobe -v error -show_streams -show_format -of json "$OUT_FILE" >"$PROBE_FILE"
SHA="$(sha256sum "$OUT_FILE" | awk '{print $1}')"
echo "$SHA" >"$OUT_DIR/staging-smoke.sha256"

python3 - "$OUT_FILE" "$PROBE_FILE" "$SHA" <<'PY'
import json
import sys
from pathlib import Path

out_file, probe_file, sha = sys.argv[1], sys.argv[2], sys.argv[3]
probe = json.loads(Path(probe_file).read_text())
streams = probe.get("streams") or []
video = next((s for s in streams if s.get("codec_type") == "video"), None)
audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
assert video is not None, "missing video stream"
assert audio is not None, "missing audio stream"
assert video.get("codec_name") == "h264", video
assert audio.get("codec_name") == "aac", audio
assert int(video.get("width") or 0) == 640
assert int(video.get("height") or 0) == 360
duration = float((probe.get("format") or {}).get("duration") or 0)
assert 40.0 <= duration <= 90.0, duration
print(
    f"OK video=h264 640x360 audio=aac duration={duration:.2f}s "
    f"file={out_file} sha256={sha}"
)
PY

echo "OUT_FILE=$OUT_FILE"
echo "SHA256=$SHA"
echo "PROBE=$PROBE_FILE"
