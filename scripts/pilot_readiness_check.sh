#!/usr/bin/env bash
set -euo pipefail

# Safe pilot readiness smoke check. Does not modify data except optional dry-run cleanup request.
# Usage:
#   BASE_URL=http://127.0.0.1:8000 ADMIN_SYNC_SECRET=... TENANT_SLUG=demo ./scripts/pilot_readiness_check.sh

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TENANT_SLUG="${TENANT_SLUG:-}"
ADMIN_SYNC_SECRET="${ADMIN_SYNC_SECRET:-}"

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
  curl "${curl_args[@]}" "$BASE_URL/admin/readiness?tenant_slug=$TENANT_SLUG"
else
  curl "${curl_args[@]}" "$BASE_URL/admin/readiness"
fi
echo

echo "== cleanup dry-run =="
curl "${curl_args[@]}" -X POST "$BASE_URL/admin/cleanup" -H 'Content-Type: application/json' -d '{"dry_run":true}'
echo