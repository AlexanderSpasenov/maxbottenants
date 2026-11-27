#!/usr/bin/env bash
set -euo pipefail

# Restore a backup into a TEST database only. Never targets production DB name.
# Usage: ./scripts/restore_postgres_to_test.sh <backup.sql.gz> [test_db_name]
# Requires TEST db name to contain "test".

BACKUP="${1:-}"
TEST_DB="${2:-maxbottenants_test}"
if [[ -z "$BACKUP" ]]; then
  echo "Usage: $0 <backup.sql.gz> [test_db_name]" >&2
  exit 2
fi
if [[ "$TEST_DB" != *test* ]]; then
  echo "Refusing: test db name must contain 'test'" >&2
  exit 2
fi
if [[ ! -f "$BACKUP" ]]; then
  echo "Backup file not found: $BACKUP" >&2
  exit 2
fi

echo "Restoring $BACKUP into $TEST_DB (destructive for test DB)"
docker compose exec -T postgres psql -U "${POSTGRES_USER:-maxbot}" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$TEST_DB\";"
docker compose exec -T postgres psql -U "${POSTGRES_USER:-maxbot}" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$TEST_DB\";"
gunzip -c "$BACKUP" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-maxbot}" -d "$TEST_DB" -v ON_ERROR_STOP=1
echo "Restore completed into $TEST_DB"
