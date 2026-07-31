#!/usr/bin/env bash
# Full staging E2E smoke test with a real probeable video.
# Fails immediately on unexpected HTTP status or invalid state.
# Does NOT enable live Radius. Does NOT start Phase 12.
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
ADMIN_PASS="${ADMIN_PASS:?Set ADMIN_PASS or provide $CREDS_FILE}"
SUB_USER="${SUB_USER:-staging_user_001}"
SUB_PASS="${SUB_PASS:?Set SUB_PASS or provide $CREDS_FILE}"
DEVICE_A="${DEVICE_A:-smoke-device-a}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }
ok() { echo "OK: $*"; }

http_json() {
  # usage: http_json METHOD URL [curl args...] -> writes body to $TMP/last.json, echoes code
  local method=$1 url=$2
  shift 2
  local code
  code=$(curl -sS -o "$TMP/last.json" -w '%{http_code}' -X "$method" "$url" "$@" || true)
  echo "$code"
}

expect() {
  local got=$1 want=$2 msg=$3
  [[ "$got" == "$want" ]] || fail "$msg (HTTP $got want $want) body=$(head -c 400 "$TMP/last.json" 2>/dev/null || true)"
  ok "$msg (HTTP $got)"
}

json() {
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$TMP/last.json"
}

wait_job() {
  local job_id=$1 timeout=$2 label=$3
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    local code status
    code=$(http_json GET "$BASE_URL/api/admin/media/processing/jobs/$job_id" "${AH[@]}")
    [[ "$code" == "200" ]] || fail "poll $label job HTTP $code"
    status=$(json "d.get('status','')")
    echo "  $label job status=$status"
    if [[ "$status" == "completed" ]]; then
      ok "$label completed"
      return 0
    fi
    if [[ "$status" == "failed" || "$status" == "cancelled" ]]; then
      fail "$label ended status=$status body=$(head -c 500 "$TMP/last.json")"
    fi
    sleep 3
  done
  fail "$label timed out after ${timeout}s"
}

wait_active_package() {
  local asset_id=$1 timeout=$2
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    local code
    code=$(http_json GET "$BASE_URL/api/admin/media/assets/$asset_id/packages" "${AH[@]}")
    [[ "$code" == "200" ]] || fail "list packages HTTP $code"
    python3 - "$TMP/last.json" <<'PY' && return 0
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
    sleep 3
  done
  fail "no active completed package within ${timeout}s"
}

step "Ensure real test video"
if [[ ! -f "$VIDEO" ]]; then
  "$ROOT/deploy/staging/scripts/generate_test_video.sh" "$VIDEO"
fi
[[ -f "$VIDEO" ]] || fail "missing test video $VIDEO"
SIZE=$(stat -c%s "$VIDEO")
SHA=$(sha256sum "$VIDEO" | awk '{print $1}')
ok "video size=${SIZE} sha256=${SHA}"

step "Health"
expect "$(http_json GET "$BASE_URL/healthz")" 200 "nginx healthz"
expect "$(http_json GET "$BASE_URL/api/health/live")" 200 "api live"
expect "$(http_json GET "$BASE_URL/api/health/ready")" 200 "api ready"

step "Deny public media paths"
for path in /media/ /packages/ /originals/ /media/originals/x /packages/x /originals/x; do
  code=$(http_json GET "$BASE_URL$path")
  [[ "$code" == "404" || "$code" == "403" ]] || fail "public path $path returned $code"
done
ok "public media/package/original paths denied"

step "Admin login"
expect "$(http_json POST "$BASE_URL/api/admin/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")" 200 "admin login"
ADMIN_TOKEN=$(json "d['access_token']")
AH=(-H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json')

step "Create genre (publish readiness)"
GENRE_CODE=$(http_json POST "$BASE_URL/api/admin/genres" "${AH[@]}" \
  -d '{"name":"Staging Smoke Genre","description":"smoke"}')
if [[ "$GENRE_CODE" == "201" ]]; then
  GENRE_ID=$(json "d['id']")
elif [[ "$GENRE_CODE" == "409" || "$GENRE_CODE" == "400" ]]; then
  expect "$(http_json GET "$BASE_URL/api/admin/genres?page_size=50" "${AH[@]}")" 200 "list genres"
  GENRE_ID=$(python3 - <<'PY'
import json
data=json.load(open("'"$TMP"'/last.json"))
items=data.get("data") or data
for g in items:
    if g.get("name")=="Staging Smoke Genre":
        print(g["id"]); break
else:
    raise SystemExit("genre not found")
PY
)
else
  fail "genre create HTTP $GENRE_CODE"
fi
ok "genre_id=$GENRE_ID"

step "Create movie (draft) with publish metadata"
expect "$(http_json POST "$BASE_URL/api/admin/movies" "${AH[@]}" -d "{
  \"title\": \"Staging Smoke Film\",
  \"original_title\": \"Staging Smoke Film\",
  \"description\": \"Staging smoke synopsis for publication readiness.\",
  \"short_description\": \"Smoke synopsis\",
  \"release_year\": 2026,
  \"duration_minutes\": 1,
  \"poster_url\": \"https://example.invalid/staging-poster.jpg\",
  \"backdrop_url\": \"https://example.invalid/staging-backdrop.jpg\",
  \"genre_ids\": [$GENRE_ID],
  \"status\": \"draft\"
}")" 201 "movie create"
MOVIE_ID=$(json "d['id']")
ok "movie_id=$MOVIE_ID"

step "Upload session + complete real video"
expect "$(http_json POST "$BASE_URL/api/admin/media/sessions" "${AH[@]}" -d "{
  \"filename\": \"staging-smoke.mp4\",
  \"mime_type\": \"video/mp4\",
  \"size_bytes\": $SIZE,
  \"category\": \"originals\",
  \"movie_id\": $MOVIE_ID
}")" 201 "upload session create"
SESSION_ID=$(json "d['session']['id']")
ASSET_ID=$(json "d['media_asset']['id']")
ok "session=$SESSION_ID asset=$ASSET_ID"

UP_CODE=$(curl -sS -o "$TMP/last.json" -w '%{http_code}' -X PUT \
  "$BASE_URL/api/admin/media/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Upload-Offset: 0" \
  -H "Upload-Complete: true" \
  -F "file=@${VIDEO};type=video/mp4")
expect "$UP_CODE" 200 "upload complete"
UPLOAD_STATUS=$(json "d.get('status','')")
[[ "$UPLOAD_STATUS" == "completed" ]] || fail "upload status=$UPLOAD_STATUS"

step "Probe media"
PROBE_CODE=$(http_json POST "$BASE_URL/api/admin/media/assets/$ASSET_ID/processing/probe" "${AH[@]}" -d '{}')
[[ "$PROBE_CODE" == "201" || "$PROBE_CODE" == "200" ]] || fail "probe queue HTTP $PROBE_CODE"
PROBE_JOB=$(json "d['job']['id']")
wait_job "$PROBE_JOB" "$PROBE_WAIT_SECONDS" "probe"

step "Encode HLS"
ENC_CODE=$(http_json POST "$BASE_URL/api/admin/media/assets/$ASSET_ID/processing/encode-hls" "${AH[@]}" -d '{}')
[[ "$ENC_CODE" == "201" || "$ENC_CODE" == "200" ]] || fail "encode queue HTTP $ENC_CODE body=$(head -c 400 "$TMP/last.json")"
ENCODE_JOB=$(json "d['job']['id']")
wait_job "$ENCODE_JOB" "$ENCODE_WAIT_SECONDS" "encode"

PACKAGE_ID=$(wait_active_package "$ASSET_ID" 60)
ok "active package=$PACKAGE_ID"
expect "$(http_json GET "$BASE_URL/api/admin/media/packages/$PACKAGE_ID" "${AH[@]}")" 200 "package detail"
RENDITIONS=$(json "d.get('rendition_count') or len(d.get('renditions') or [])")
echo "rendition_count=$RENDITIONS"
python3 - <<PY
import json
d=json.load(open("$TMP/last.json"))
rends=d.get("renditions") or []
labels=[r.get("label") for r in rends if r.get("status")=="completed"]
print("rendition_labels=", labels)
assert labels, "no completed renditions"
assert any(l in labels for l in ("240p","360p")), labels
PY

step "Publication readiness + workflow"
expect "$(http_json GET "$BASE_URL/api/admin/catalog/movies/$MOVIE_ID/publication-readiness" "${AH[@]}")" 200 "readiness"
python3 - <<PY
import json
d=json.load(open("$TMP/last.json"))
assert d.get("ready") is True, d
print("OK: publication ready")
PY
expect "$(http_json POST "$BASE_URL/api/admin/catalog/movies/$MOVIE_ID/submit-review" "${AH[@]}" -d '{}')" 200 "submit-review"
expect "$(http_json POST "$BASE_URL/api/admin/catalog/movies/$MOVIE_ID/approve" "${AH[@]}" -d '{}')" 200 "approve"
expect "$(http_json POST "$BASE_URL/api/admin/catalog/movies/$MOVIE_ID/publish" "${AH[@]}" -d '{}')" 200 "publish"

step "Fixture subscriber login + entitlement"
expect "$(http_json POST "$BASE_URL/api/auth/subscriber/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$SUB_USER\",\"password\":\"$SUB_PASS\",\"device_id\":\"$DEVICE_A\",\"device_name\":\"Smoke A\"}")" 200 "subscriber login"
SUB_TOKEN=$(json "d['access_token']")
SH=(-H "Authorization: Bearer $SUB_TOKEN" -H 'Content-Type: application/json')
expect "$(http_json GET "$BASE_URL/api/me/entitlement" "${SH[@]}")" 200 "entitlement"
python3 - <<PY
import json
d=json.load(open("$TMP/last.json"))
assert d.get("allowed") is True, d
print("OK: entitlement active")
PY
expect "$(http_json GET "$BASE_URL/api/me/devices" "${SH[@]}")" 200 "devices list"

step "Protected playback session + playlists + segment Range"
expect "$(http_json POST "$BASE_URL/api/playback/sessions" "${SH[@]}" \
  -d "{\"media_asset_id\":\"$ASSET_ID\"}")" 201 "playback session"
PLAY_TOKEN=$(json "d['playback_token']")
MASTER_URL=$(json "d['master_playlist_url']")
# master_playlist_url may be path-only
if [[ "$MASTER_URL" != http* ]]; then
  MASTER_URL="$BASE_URL$MASTER_URL"
fi
MASTER_CODE=$(curl -sS -o "$TMP/master.m3u8" -w '%{http_code}' "$MASTER_URL")
expect "$MASTER_CODE" 200 "master playlist"
grep -q '#EXTM3U' "$TMP/master.m3u8" || fail "master playlist missing EXTM3U"
VARIANT_PATH=$(python3 - <<'PY'
from pathlib import Path
lines=Path("'"$TMP"'/master.m3u8").read_text().splitlines()
for i,line in enumerate(lines):
    if line.startswith("#EXT-X-STREAM-INF"):
        # next non-empty non-comment
        for nxt in lines[i+1:]:
            if nxt and not nxt.startswith("#"):
                print(nxt.strip()); raise SystemExit
raise SystemExit("no variant in master")
PY
)
if [[ "$VARIANT_PATH" == http* ]]; then
  VARIANT_URL="$VARIANT_PATH"
elif [[ "$VARIANT_PATH" == /* ]]; then
  VARIANT_URL="$BASE_URL$VARIANT_PATH"
else
  # relative to master URL directory
  VARIANT_URL="$(dirname "$MASTER_URL")/$VARIANT_PATH"
fi
VARIANT_CODE=$(curl -sS -o "$TMP/index.m3u8" -w '%{http_code}' "$VARIANT_URL")
expect "$VARIANT_CODE" 200 "variant playlist"
SEGMENT_NAME=$(python3 - <<'PY'
from pathlib import Path
for line in Path("'"$TMP"'/index.m3u8").read_text().splitlines():
    if line and not line.startswith("#") and line.endswith(".ts"):
        print(line.strip()); raise SystemExit
raise SystemExit("no segment")
PY
)
if [[ "$SEGMENT_NAME" == http* ]]; then
  SEG_URL="$SEGMENT_NAME"
elif [[ "$SEGMENT_NAME" == /* ]]; then
  SEG_URL="$BASE_URL$SEGMENT_NAME"
else
  SEG_URL="$(dirname "$VARIANT_URL")/$SEGMENT_NAME"
fi
SEG_CODE=$(curl -sS -o "$TMP/seg.ts" -w '%{http_code}' "$SEG_URL")
expect "$SEG_CODE" 200 "full segment"
[[ -s "$TMP/seg.ts" ]] || fail "empty segment"
RANGE_CODE=$(curl -sS -o "$TMP/seg.part" -w '%{http_code}' -H 'Range: bytes=0-1023' "$SEG_URL")
expect "$RANGE_CODE" 206 "segment byte range"
ok "protected playback playlists + segment + 206"

step "Watch progress / Continue Watching / complete / history"
expect "$(http_json PUT "$BASE_URL/api/me/watch-progress/$ASSET_ID" "${SH[@]}" \
  -d '{"position_seconds":45,"duration_seconds":120}')" 200 "save progress"
expect "$(http_json GET "$BASE_URL/api/me/continue-watching" "${SH[@]}")" 200 "continue watching"
python3 - <<PY
import json
items=json.load(open("$TMP/last.json"))
assert any(i.get("media_asset_id")=="$ASSET_ID" for i in items), items
print("OK: asset in continue watching")
PY
expect "$(http_json GET "$BASE_URL/api/me/watch-progress/$ASSET_ID" "${SH[@]}")" 200 "get progress"
POS=$(json "d.get('position_seconds')")
python3 -c "assert float('$POS')>=45, '$POS'"
ok "resume position=$POS"
expect "$(http_json POST "$BASE_URL/api/me/watch-progress/$ASSET_ID/complete" "${SH[@]}" \
  -d '{"position_seconds":120,"duration_seconds":120}')" 200 "complete content"
expect "$(http_json GET "$BASE_URL/api/me/continue-watching" "${SH[@]}")" 200 "continue after complete"
python3 - <<PY
import json
items=json.load(open("$TMP/last.json"))
assert not any(i.get("media_asset_id")=="$ASSET_ID" for i in items), items
print("OK: removed from continue watching")
PY
expect "$(http_json GET "$BASE_URL/api/me/watch-history" "${SH[@]}")" 200 "history"
python3 - <<PY
import json
payload=json.load(open("$TMP/last.json"))
items=payload.get("data") or payload
assert any(i.get("media_asset_id")=="$ASSET_ID" for i in items), items
print("OK: retained in history")
PY

step "Unpublish + deny playback + history tombstone"
expect "$(http_json POST "$BASE_URL/api/admin/catalog/movies/$MOVIE_ID/unpublish" "${AH[@]}" -d '{}')" 200 "unpublish"
DENY=$(http_json POST "$BASE_URL/api/playback/sessions" "${SH[@]}" \
  -d "{\"media_asset_id\":\"$ASSET_ID\"}")
[[ "$DENY" == "403" || "$DENY" == "404" || "$DENY" == "409" ]] || fail "expected playback deny after unpublish, got $DENY"
ok "playback denied after unpublish ($DENY)"
expect "$(http_json GET "$BASE_URL/api/me/watch-history" "${SH[@]}")" 200 "history after unpublish"
python3 - <<PY
import json
payload=json.load(open("$TMP/last.json"))
items=payload.get("data") or payload
row=next(i for i in items if i.get("media_asset_id")=="$ASSET_ID")
assert row.get("available") is False, row
assert row.get("title") == "Unavailable", row
assert row.get("player_path") in ("", None), row
print("OK: history tombstone unavailable")
PY

step "Anonymous direct package/original/media paths fail"
for path in /media/ /packages/ /originals/; do
  code=$(http_json GET "$BASE_URL$path")
  [[ "$code" == "404" || "$code" == "403" ]] || fail "anon $path -> $code"
done
ok "anonymous media trees denied"

echo
echo "smoke_test: PASSED"
echo "movie_id=$MOVIE_ID asset_id=$ASSET_ID package_id=$PACKAGE_ID"
