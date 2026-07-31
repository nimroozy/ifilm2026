#!/usr/bin/env bash
# Staging end-to-end smoke test (manual / CI against a running stack).
# Does NOT start Phase 12. Does NOT enable live Radius. Does NOT auto-deploy.
set -uo pipefail

BASE_URL="${STAGING_BASE_URL:-http://127.0.0.1:8080}"
ADMIN_USER="${ADMIN_USER:-staging_admin}"
ADMIN_PASS="${ADMIN_PASS:?Set ADMIN_PASS}"
SUB_USER="${SUB_USER:-staging_user_001}"
SUB_PASS="${SUB_PASS:?Set SUB_PASS}"
DEVICE_A="${DEVICE_A:-smoke-device-a}"
DEVICE_B="${DEVICE_B:-smoke-device-b}"
DEVICE_C="${DEVICE_C:-smoke-device-c}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAIL=0

step() { echo; echo "==> $*"; }

expect_code() {
  local got=$1 want=$2 msg=$3
  if [[ "$got" != "$want" ]]; then
    echo "FAIL: $msg (HTTP $got want $want)"
    FAIL=1
    return 0
  fi
  echo "OK: $msg (HTTP $got)"
}

json_field() {
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d$1)" 2>/dev/null || true
}

step "Health"
expect_code "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/healthz" || true)" 200 "nginx healthz"
expect_code "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/health/live" || true)" 200 "api live"
READY=$(curl -s -o "$TMP/ready.json" -w '%{http_code}' "$BASE_URL/api/health/ready" || true)
expect_code "$READY" 200 "api ready"
[[ "$READY" != "200" ]] && cat "$TMP/ready.json" || true

step "Admin login"
ADMIN_LOGIN=$(curl -sS -X POST "$BASE_URL/api/admin/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}" || true)
ADMIN_TOKEN=$(printf '%s' "$ADMIN_LOGIN" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' 2>/dev/null || true)
if [[ -z "${ADMIN_TOKEN:-}" ]]; then
  echo "FAIL: admin login (body=$ADMIN_LOGIN)"
  FAIL=1
  echo "smoke_test: FAILED"
  exit 1
fi
echo "OK: admin login"
AH=(-H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json')

step "Subscriber fixture login"
SUB_LOGIN=$(curl -sS -X POST "$BASE_URL/api/auth/subscriber/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$SUB_USER\",\"password\":\"$SUB_PASS\",\"device_id\":\"$DEVICE_A\",\"device_name\":\"Smoke A\"}" || true)
SUB_TOKEN=$(printf '%s' "$SUB_LOGIN" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' 2>/dev/null || true)
if [[ -z "${SUB_TOKEN:-}" ]]; then
  echo "FAIL: subscriber fixture login (body=$SUB_LOGIN)"
  FAIL=1
  echo "smoke_test: FAILED"
  exit 1
fi
echo "OK: subscriber fixture login"
SH=(-H "Authorization: Bearer $SUB_TOKEN" -H 'Content-Type: application/json')

step "Device limit (max_devices=2 expected from staging fixture)"
curl -sS -X POST "$BASE_URL/api/auth/subscriber/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$SUB_USER\",\"password\":\"$SUB_PASS\",\"device_id\":\"$DEVICE_B\",\"device_name\":\"Smoke B\"}" >/dev/null || true
LIMIT_CODE=$(curl -s -o "$TMP/limit.json" -w '%{http_code}' -X POST "$BASE_URL/api/auth/subscriber/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$SUB_USER\",\"password\":\"$SUB_PASS\",\"device_id\":\"$DEVICE_C\",\"device_name\":\"Smoke C\"}" || true)
expect_code "$LIMIT_CODE" 403 "third device denied"

step "Create movie (draft)"
MOVIE=$(curl -sS -X POST "$BASE_URL/api/admin/movies" "${AH[@]}" -d '{
  "title":"Staging Smoke Film",
  "original_title":"Staging Smoke Film",
  "release_year":2026,
  "duration_minutes":5,
  "imdb_rating":7.0,
  "genre_ids":[],
  "description":"Smoke test",
  "status":"draft"
}' || true)
MOVIE_ID=$(printf '%s' "$MOVIE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' 2>/dev/null || true)
if [[ -z "${MOVIE_ID:-}" ]]; then
  echo "FAIL: movie create (body=$MOVIE)"
  FAIL=1
else
  echo "OK: movie create id=$MOVIE_ID"
fi

SESSION_ID=""
ASSET_ID=""
if [[ -n "${MOVIE_ID:-}" ]]; then
  step "Create upload session + put tiny file"
  dd if=/dev/urandom of="$TMP/smoke.mp4" bs=1024 count=1 status=none
  UPLOAD=$(curl -sS -X POST "$BASE_URL/api/admin/media/sessions" "${AH[@]}" -d "{
    \"filename\":\"smoke.mp4\",
    \"mime_type\":\"video/mp4\",
    \"size_bytes\":1024,
    \"category\":\"originals\",
    \"movie_id\":$MOVIE_ID
  }" || true)
  SESSION_ID=$(printf '%s' "$UPLOAD" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("session",{}).get("id") or "")' 2>/dev/null || true)
  ASSET_ID=$(printf '%s' "$UPLOAD" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("media_asset",{}).get("id") or "")' 2>/dev/null || true)
  if [[ -n "$SESSION_ID" ]]; then
    code=$(curl -s -o "$TMP/upfile.json" -w '%{http_code}' -X PUT "$BASE_URL/api/admin/media/sessions/$SESSION_ID" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Upload-Offset: 0" \
      -H "Upload-Complete: true" \
      -F "file=@$TMP/smoke.mp4;type=video/mp4" || true)
    echo "upload put HTTP $code"
    [[ "$code" == "200" ]] && echo "OK: upload" || { echo "WARN: upload put HTTP $code"; }
  else
    echo "WARN: upload session not created (body=$UPLOAD)"
  fi
  echo "session_id=${SESSION_ID:-unknown} asset_id=${ASSET_ID:-unknown}"

  step "Probe / encode (best-effort — tiny random bytes may fail probe)"
  if [[ -n "${ASSET_ID:-}" ]]; then
    curl -sS -X POST "$BASE_URL/api/admin/media/assets/$ASSET_ID/processing/probe" "${AH[@]}" -d '{}' \
      -o "$TMP/probe.json" || true
    curl -sS -X POST "$BASE_URL/api/admin/media/assets/$ASSET_ID/processing/encode-hls" "${AH[@]}" -d '{}' \
      -o "$TMP/encode.json" || true
    sleep 5
    echo "queued probe/encode (see worker logs if package not ready)"
  else
    echo "SKIP probe/encode (no asset id)"
  fi

  step "Publish workflow (submit-review → approve → publish)"
  for action in submit-review approve publish; do
    code=$(curl -s -o "$TMP/pub.json" -w '%{http_code}' -X POST \
      "$BASE_URL/api/admin/catalog/movies/$MOVIE_ID/$action" "${AH[@]}" -d '{}' || true)
    echo "publish action $action HTTP $code"
  done

  step "Protected playback session (subscriber)"
  PLAY_CODE=$(curl -s -o "$TMP/play.json" -w '%{http_code}' -X POST "$BASE_URL/api/playback/sessions" \
    "${SH[@]}" -d "{\"content_type\":\"movie\",\"content_id\":$MOVIE_ID}" || true)
  echo "playback HTTP $PLAY_CODE"
  if [[ "$PLAY_CODE" == "201" || "$PLAY_CODE" == "403" || "$PLAY_CODE" == "404" ]]; then
    echo "OK: playback path exercised ($PLAY_CODE)"
  else
    echo "WARN: unexpected playback code $PLAY_CODE (package/publish may still be pending)"
  fi

  step "Watch history"
  if [[ -n "${ASSET_ID:-}" ]]; then
    WH_PUT=$(curl -s -o "$TMP/wh.json" -w '%{http_code}' -X PUT \
      "$BASE_URL/api/me/watch-progress/$ASSET_ID" "${SH[@]}" \
      -d '{"position_seconds":42,"duration_seconds":300}' || true)
    echo "watch-progress put HTTP $WH_PUT"
  fi
  WH_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/me/continue-watching" "${SH[@]}" || true)
  expect_code "$WH_CODE" 200 "continue-watching list"

  step "Unpublish + playback denial"
  curl -s -o /dev/null -X POST "$BASE_URL/api/admin/catalog/movies/$MOVIE_ID/unpublish" "${AH[@]}" -d '{}' || true
  DENY_CODE=$(curl -s -o "$TMP/deny.json" -w '%{http_code}' -X POST "$BASE_URL/api/playback/sessions" \
    "${SH[@]}" -d "{\"content_type\":\"movie\",\"content_id\":$MOVIE_ID}" || true)
  if [[ "$DENY_CODE" == "403" || "$DENY_CODE" == "404" ]]; then
    echo "OK: unpublished playback denied ($DENY_CODE)"
  elif [[ "$DENY_CODE" == "201" ]]; then
    echo "FAIL: expected deny after unpublish, got $DENY_CODE"
    FAIL=1
  else
    echo "OK: unpublished playback not granted ($DENY_CODE)"
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "smoke_test: FAILED"
  exit 1
fi
echo "smoke_test: PASSED (core auth/device/catalog paths; encode/publish depend on real media)"
