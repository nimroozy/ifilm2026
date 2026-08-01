#!/usr/bin/env bash
# Full staging E2E smoke test with a real probeable video.
# Fails immediately on unexpected HTTP status or invalid state.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE_URL="${STAGING_BASE_URL:-http://127.0.0.1:8080}"
CREDS_FILE="${STAGING_CREDS_FILE:-$ROOT/deploy/staging/.env.staging.credentials}"
TEST_DIR="${STAGING_TEST_DIR:-$ROOT/deploy/staging/.tmp-smoke}"
VIDEO="${STAGING_TEST_VIDEO:-$TEST_DIR/staging-smoke.mp4}"
PROBE_WAIT_SECONDS="${PROBE_WAIT_SECONDS:-180}"
ENCODE_WAIT_SECONDS="${ENCODE_WAIT_SECONDS:-600}"

if [[ -f "$CREDS_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  source "$CREDS_FILE"
  set +a
fi

ADMIN_USER="${ADMIN_USER:-staging_admin}"
ADMIN_PASS="${ADMIN_PASS:?Set ADMIN_PASS or provide credentials file}"
SUB_USER="${SUB_USER:-staging_user_001}"
SUB_PASS="${SUB_PASS:?Set SUB_PASS or provide credentials file}"
DEVICE_A="${DEVICE_A:-smoke-device-a}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
LAST_BODY="$TMP/last.json"

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }
ok() { echo "OK: $*"; }

req() {
  # req METHOD PATH [curl args...]  -> sets CODE, body in LAST_BODY
  local method=$1 path=$2
  shift 2
  CODE=$(curl -sS -o "$LAST_BODY" -w '%{http_code}' -X "$method" "${BASE_URL}${path}" "$@" || true)
}

expect_code() {
  local want=$1 msg=$2
  [[ "$CODE" == "$want" ]] || fail "$msg (HTTP $CODE want $want) body=$(head -c 400 "$LAST_BODY" 2>/dev/null || true)"
  ok "$msg (HTTP $CODE)"
}

jget() {
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($1)" "$LAST_BODY"
}

wait_job() {
  local job_id=$1 timeout=$2 label=$3
  local deadline=$((SECONDS + timeout)) status
  while (( SECONDS < deadline )); do
    req GET "/api/admin/media/processing/jobs/${job_id}" "${AH[@]}"
    [[ "$CODE" == "200" ]] || fail "poll $label job HTTP $CODE"
    status=$(jget "d.get('status','')")
    echo "  $label job status=$status"
    if [[ "$status" == "completed" ]]; then
      ok "$label completed"
      return 0
    fi
    if [[ "$status" == "failed" || "$status" == "cancelled" ]]; then
      fail "$label ended status=$status body=$(head -c 500 "$LAST_BODY")"
    fi
    sleep 3
  done
  fail "$label timed out after ${timeout}s"
}

wait_active_package() {
  local asset_id=$1 timeout=$2
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    req GET "/api/admin/media/assets/${asset_id}/packages" "${AH[@]}"
    [[ "$CODE" == "200" ]] || fail "list packages HTTP $CODE"
    if PACKAGE_ID=$(python3 - "$LAST_BODY" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
items = data.get("data") if isinstance(data, dict) and "data" in data else data
if not isinstance(items, list):
    items = []
for p in items:
    if p.get("status") == "completed" and p.get("is_active") is True:
        print(p["id"])
        raise SystemExit(0)
raise SystemExit(1)
PY
    ); then
      echo "$PACKAGE_ID"
      return 0
    fi
    sleep 3
  done
  fail "no active completed package within ${timeout}s"
}

step "Ensure real test video"
# Always regenerate so checksum differs across smoke runs (duplicate upload guard).
STAGING_TEST_UNIQUE="$(date -u +%Y%m%d%H%M%S)-$$" \
  "$ROOT/deploy/staging/scripts/generate_test_video.sh" "$VIDEO"
[[ -f "$VIDEO" ]] || fail "missing test video $VIDEO"
SIZE=$(stat -c%s "$VIDEO")
SHA=$(sha256sum "$VIDEO" | awk '{print $1}')
ok "video size=${SIZE} sha256=${SHA}"

step "Health"
req GET /healthz
expect_code 200 "nginx healthz"
req GET /api/health/live
expect_code 200 "api live"
req GET /api/health/ready
expect_code 200 "api ready"

step "Deny public media paths"
for path in /media/ /packages/ /originals/ /media/originals/x /packages/x /originals/x; do
  req GET "$path"
  [[ "$CODE" == "404" || "$CODE" == "403" ]] || fail "public path $path returned $CODE"
done
ok "public media/package/original paths denied"

step "Admin login"
req POST /api/admin/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}"
expect_code 200 "admin login"
ADMIN_TOKEN=$(jget "d['access_token']")
AH=(-H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json')

step "Create genre (publish readiness)"
req POST /api/admin/genres "${AH[@]}" -d '{"name":"Staging Smoke Genre","description":"smoke"}'
if [[ "$CODE" == "201" ]]; then
  GENRE_ID=$(jget "d['id']")
elif [[ "$CODE" == "409" || "$CODE" == "400" ]]; then
  req GET '/api/admin/genres?page_size=50' "${AH[@]}"
  expect_code 200 "list genres"
  GENRE_ID=$(python3 - "$LAST_BODY" <<'PY'
import json, sys
data=json.load(open(sys.argv[1]))
items=data.get("data") or data
for g in items:
    if g.get("name")=="Staging Smoke Genre":
        print(g["id"]); raise SystemExit
raise SystemExit("genre not found")
PY
)
else
  fail "genre create HTTP $CODE body=$(head -c 300 "$LAST_BODY")"
fi
ok "genre_id=$GENRE_ID"

step "Create movie (draft) with publish metadata"
SMOKE_SUFFIX="$(date -u +%Y%m%d%H%M%S)-$$"
req POST /api/admin/movies "${AH[@]}" -d "{
  \"title\": \"Staging Smoke Film ${SMOKE_SUFFIX}\",
  \"original_title\": \"Staging Smoke Film ${SMOKE_SUFFIX}\",
  \"slug\": \"staging-smoke-film-${SMOKE_SUFFIX}\",
  \"description\": \"Staging smoke synopsis for publication readiness.\",
  \"short_description\": \"Smoke synopsis\",
  \"release_year\": 2026,
  \"duration_minutes\": 1,
  \"poster_url\": \"https://example.invalid/staging-poster.jpg\",
  \"backdrop_url\": \"https://example.invalid/staging-backdrop.jpg\",
  \"genre_ids\": [$GENRE_ID],
  \"status\": \"draft\"
}"
expect_code 201 "movie create"
MOVIE_ID=$(jget "d['id']")
ok "movie_id=$MOVIE_ID"

step "Upload session + complete real video"
req POST /api/admin/media/sessions "${AH[@]}" -d "{
  \"filename\": \"staging-smoke.mp4\",
  \"mime_type\": \"video/mp4\",
  \"size_bytes\": $SIZE,
  \"category\": \"originals\",
  \"movie_id\": $MOVIE_ID
}"
expect_code 201 "upload session create"
SESSION_ID=$(jget "d['session']['id']")
ASSET_ID=$(jget "d['media_asset']['id']")
ok "session=$SESSION_ID asset=$ASSET_ID"

CODE=$(curl -sS -o "$LAST_BODY" -w '%{http_code}' -X PUT \
  "${BASE_URL}/api/admin/media/sessions/${SESSION_ID}" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Upload-Offset: 0" \
  -H "Upload-Complete: true" \
  -F "file=@${VIDEO};type=video/mp4")
expect_code 200 "upload complete"
[[ "$(jget "d.get('status','')")" == "completed" ]] || fail "upload status not completed"

step "Probe media"
req POST "/api/admin/media/assets/${ASSET_ID}/processing/probe" "${AH[@]}" -d '{}'
[[ "$CODE" == "201" || "$CODE" == "200" ]] || fail "probe queue HTTP $CODE"
PROBE_JOB=$(jget "d['job']['id']")
wait_job "$PROBE_JOB" "$PROBE_WAIT_SECONDS" "probe"

step "Encode HLS"
req POST "/api/admin/media/assets/${ASSET_ID}/processing/encode-hls" "${AH[@]}" -d '{}'
[[ "$CODE" == "201" || "$CODE" == "200" ]] || fail "encode queue HTTP $CODE body=$(head -c 400 "$LAST_BODY")"
ENCODE_JOB=$(jget "d['job']['id']")
wait_job "$ENCODE_JOB" "$ENCODE_WAIT_SECONDS" "encode"

PACKAGE_ID=$(wait_active_package "$ASSET_ID" 60)
ok "active package=$PACKAGE_ID"
req GET "/api/admin/media/packages/${PACKAGE_ID}" "${AH[@]}"
expect_code 200 "package detail"
python3 - "$LAST_BODY" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
rends=d.get("renditions") or []
labels=[r.get("label") for r in rends if r.get("status")=="completed"]
print("rendition_labels=", labels)
assert labels, "no completed renditions"
assert any(l in labels for l in ("240p","360p")), labels
PY

step "Publication readiness + workflow"
req GET "/api/admin/catalog/movie/${MOVIE_ID}/publication-readiness" "${AH[@]}"
expect_code 200 "readiness"
python3 - "$LAST_BODY" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
assert d.get("ready") is True, d
print("OK: publication ready")
PY
req POST "/api/admin/catalog/movie/${MOVIE_ID}/submit-review" "${AH[@]}" -d '{}'
expect_code 200 "submit-review"
req POST "/api/admin/catalog/movie/${MOVIE_ID}/approve" "${AH[@]}" -d '{}'
expect_code 200 "approve"
req POST "/api/admin/catalog/movie/${MOVIE_ID}/publish" "${AH[@]}" -d '{}'
expect_code 200 "publish"

step "Fixture subscriber login + entitlement"
req POST /api/auth/subscriber/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"$SUB_USER\",\"password\":\"$SUB_PASS\",\"device_id\":\"$DEVICE_A\",\"device_name\":\"Smoke A\"}"
expect_code 200 "subscriber login"
SUB_TOKEN=$(jget "d['access_token']")
SH=(-H "Authorization: Bearer $SUB_TOKEN" -H 'Content-Type: application/json')
req GET /api/me/entitlement "${SH[@]}"
expect_code 200 "entitlement"
python3 - "$LAST_BODY" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
assert d.get("allowed") is True, d
print("OK: entitlement active")
PY
req GET /api/me/devices "${SH[@]}"
expect_code 200 "devices list"

step "Protected playback session + playlists + segment Range"
req POST /api/playback/sessions "${SH[@]}" -d "{\"media_asset_id\":\"$ASSET_ID\"}"
expect_code 201 "playback session"
PLAY_TOKEN=$(jget "d['playback_token']")
MASTER_URL=$(jget "d['master_playlist_url']")
if [[ "$MASTER_URL" != http* ]]; then
  MASTER_URL="${BASE_URL}${MASTER_URL}"
fi
CODE=$(curl -sS -o "$TMP/master.m3u8" -w '%{http_code}' "$MASTER_URL")
expect_code 200 "master playlist"
grep -q '#EXTM3U' "$TMP/master.m3u8" || fail "master playlist missing EXTM3U"
VARIANT_PATH=$(python3 - "$TMP/master.m3u8" <<'PY'
from pathlib import Path
import sys
lines=Path(sys.argv[1]).read_text().splitlines()
for i,line in enumerate(lines):
    if line.startswith("#EXT-X-STREAM-INF"):
        for nxt in lines[i+1:]:
            if nxt and not nxt.startswith("#"):
                print(nxt.strip()); raise SystemExit
raise SystemExit("no variant in master")
PY
)
if [[ "$VARIANT_PATH" == http* ]]; then
  VARIANT_URL="$VARIANT_PATH"
elif [[ "$VARIANT_PATH" == /* ]]; then
  VARIANT_URL="${BASE_URL}${VARIANT_PATH}"
else
  VARIANT_URL="$(dirname "$MASTER_URL")/${VARIANT_PATH}"
fi
CODE=$(curl -sS -o "$TMP/index.m3u8" -w '%{http_code}' "$VARIANT_URL")
expect_code 200 "variant playlist"
SEGMENT_NAME=$(python3 - "$TMP/index.m3u8" <<'PY'
from pathlib import Path
import sys
for line in Path(sys.argv[1]).read_text().splitlines():
    if line and not line.startswith("#") and line.endswith(".ts"):
        print(line.strip()); raise SystemExit
raise SystemExit("no segment")
PY
)
if [[ "$SEGMENT_NAME" == http* ]]; then
  SEG_URL="$SEGMENT_NAME"
elif [[ "$SEGMENT_NAME" == /* ]]; then
  SEG_URL="${BASE_URL}${SEGMENT_NAME}"
else
  SEG_URL="$(dirname "$VARIANT_URL")/${SEGMENT_NAME}"
fi
CODE=$(curl -sS -o "$TMP/seg.ts" -w '%{http_code}' "$SEG_URL")
expect_code 200 "full segment"
[[ -s "$TMP/seg.ts" ]] || fail "empty segment"
CODE=$(curl -sS -o "$TMP/seg.part" -w '%{http_code}' -H 'Range: bytes=0-1023' "$SEG_URL")
expect_code 206 "segment byte range"
ok "protected playback playlists + segment + 206"

step "Watch progress / Continue Watching / complete / history"
# Position must be >= WATCH_PROGRESS_MIN_SECONDS (30) and < media duration (~45s).
req PUT "/api/me/watch-progress/${ASSET_ID}" "${SH[@]}" \
  -d '{"position_seconds":35,"duration_seconds":45}'
expect_code 200 "save progress"
req GET /api/me/continue-watching "${SH[@]}"
expect_code 200 "continue watching"
python3 - "$LAST_BODY" "$ASSET_ID" <<'PY'
import json, sys
items=json.load(open(sys.argv[1]))
asset=sys.argv[2]
assert any(i.get("media_asset_id")==asset for i in items), items
print("OK: asset in continue watching")
PY
req GET "/api/me/watch-progress/${ASSET_ID}" "${SH[@]}"
expect_code 200 "get progress"
POS=$(jget "d.get('position_seconds')")
python3 -c "assert float('$POS')>=30, '$POS'"
ok "resume position=$POS"
req POST "/api/me/watch-progress/${ASSET_ID}/complete" "${SH[@]}" \
  -d '{"position_seconds":45,"duration_seconds":45}'
expect_code 200 "complete content"
req GET /api/me/continue-watching "${SH[@]}"
expect_code 200 "continue after complete"
python3 - "$LAST_BODY" "$ASSET_ID" <<'PY'
import json, sys
items=json.load(open(sys.argv[1]))
asset=sys.argv[2]
assert not any(i.get("media_asset_id")==asset for i in items), items
print("OK: removed from continue watching")
PY
req GET /api/me/watch-history "${SH[@]}"
expect_code 200 "history"
python3 - "$LAST_BODY" "$ASSET_ID" <<'PY'
import json, sys
payload=json.load(open(sys.argv[1]))
items=payload.get("data") or payload
asset=sys.argv[2]
assert any(i.get("media_asset_id")==asset for i in items), items
print("OK: retained in history")
PY

step "Unpublish + deny playback + history tombstone"
req POST "/api/admin/catalog/movie/${MOVIE_ID}/unpublish" "${AH[@]}" -d '{}'
expect_code 200 "unpublish"
req POST /api/playback/sessions "${SH[@]}" -d "{\"media_asset_id\":\"$ASSET_ID\"}"
[[ "$CODE" == "403" || "$CODE" == "404" || "$CODE" == "409" ]] || fail "expected playback deny after unpublish, got $CODE"
ok "playback denied after unpublish ($CODE)"
req GET /api/me/watch-history "${SH[@]}"
expect_code 200 "history after unpublish"
python3 - "$LAST_BODY" "$ASSET_ID" <<'PY'
import json, sys
payload=json.load(open(sys.argv[1]))
items=payload.get("data") or payload
asset=sys.argv[2]
row=next(i for i in items if i.get("media_asset_id")==asset)
assert row.get("available") is False, row
assert row.get("title") == "Unavailable", row
assert row.get("player_path") in ("", None), row
print("OK: history tombstone unavailable")
PY

step "Anonymous direct package/original/media paths fail"
for path in /media/ /packages/ /originals/; do
  req GET "$path"
  [[ "$CODE" == "404" || "$CODE" == "403" ]] || fail "anon $path -> $CODE"
done
ok "anonymous media trees denied"

echo
echo "smoke_test: PASSED"
echo "movie_id=$MOVIE_ID asset_id=$ASSET_ID package_id=$PACKAGE_ID"
