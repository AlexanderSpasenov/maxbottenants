#!/usr/bin/env bash
set -euo pipefail

# Safe pilot readiness smoke check. Read-only by default.
# Usage:
#   BASE_URL=http://127.0.0.1:8000 ADMIN_SYNC_SECRET=... TENANT_SLUG=demo ./scripts/pilot_readiness_check.sh
# Options:
#   DRY_RUN_CLEANUP=true|false  (default: true) - POST /admin/cleanup with dry_run=true
#   REQUIRE_READY=true|false    (default: true) - fail if /admin/readiness reports ready=false

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TENANT_SLUG="${TENANT_SLUG:-}"
ADMIN_SYNC_SECRET="${ADMIN_SYNC_SECRET:-}"
DRY_RUN_CLEANUP="${DRY_RUN_CLEANUP:-true}"
REQUIRE_READY="${REQUIRE_READY:-true}"

curl_args=(-fsS)
if [[ -n "$ADMIN_SYNC_SECRET" ]]; then
  curl_args+=(-H "X-Admin-Sync-Secret: $ADMIN_SYNC_SECRET")
fi

echo "== health =="
curl "${curl_args[@]}" "$BASE_URL/health"
echo
curl "${curl_args[@]}" "$BASE_URL/health/ready"
echo

echo "== admin readiness =="
if [[ -n "$TENANT_SLUG" ]]; then
  readiness_url="$BASE_URL/admin/readiness?tenant_slug=$TENANT_SLUG"
else
  readiness_url="$BASE_URL/admin/readiness"
fi
readiness_json="$(curl "${curl_args[@]}" "$readiness_url")"
echo "$readiness_json"
echo
if [[ "$REQUIRE_READY" == "true" ]]; then
  READY_VALUE="$(printf '%s' "$readiness_json" | python -c 'import json,sys; print(str(json.load(sys.stdin).get("ready")).lower())')"
  if [[ "$READY_VALUE" != "true" ]]; then
    echo "Readiness check failed: ready=$READY_VALUE" >&2
    exit 1
  fi
fi

if [[ "$DRY_RUN_CLEANUP" == "true" ]]; then
  echo "== cleanup dry-run =="
  curl "${curl_args[@]}" -X POST "$BASE_URL/admin/cleanup" -H 'Content-Type: application/json' -d '{"dry_run":true}'
  echo
fi

echo "OK"