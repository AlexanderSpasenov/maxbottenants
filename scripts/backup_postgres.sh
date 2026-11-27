#!/usr/bin/env bash
set -euo pipefail

# Safe PostgreSQL backup for maxbottenants.
# Usage: ./scripts/backup_postgres.sh [output_dir]
# Requires: docker compose, running postgres service.

OUT_DIR="${1:-./backups}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"
FILE="$OUT_DIR/maxbottenants_${TS}.sql.gz"

echo "Creating backup: $FILE"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-maxbot}" -d "${POSTGRES_DB:-maxbottenants}" | gzip > "$FILE"
echo "Backup created: $FILE"
