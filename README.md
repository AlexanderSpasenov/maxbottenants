# maxbottenants

Локальный технический MVP мультиарендного MAX-бота для салонов красоты.

## Статус

Реализованы инкременты 1-10 (скелет, multitenant core, webhook persistence/idempotency, `request_only`, hardening, `online_booking`, MAX adapter readiness, CSV catalog sync, admin/ops hardening). Реальная интеграция с MAX Bot API и E2E на 2 салонах ожидает реальные credentials/contract.

## Стек

- Python 3.12, FastAPI
- PostgreSQL, Alembic
- Redis (зарезервирован в compose; worker сейчас polling-based)
- Docker Compose
- pytest, ruff

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose exec app python scripts/seed_dev.py
```

Проверки:

```bash
curl http://localhost:8000/health
docker compose exec app ruff check .
docker compose exec -T -e TEST_DATABASE_URL=postgresql+psycopg://maxbot:maxbot@postgres:5432/maxbottenants_test app pytest -q
```

## Основные возможности

- **Multitenancy**: все доменные данные с `tenant_id`; tenant isolation проверяется тестами.
- **Webhook MAX**: `POST /webhook/max`, secret-check, persist-before-ack, idempotency по `event_key`, claim/processing/retry-safe worker flow.
- **Dialog flows**: `request_only` и skeleton `online_booking` (слоты, конфликт-проверка, hold/pending confirmation/expiry).
- **Outbox**: дедуп по `tenant_id+dedupe_key`, retry/backoff, `dead` после лимита попыток, admin requeue/stats.
- **Catalog sync**: read-only CSV source, idempotent upsert по `tenant_id+external_key`, `sync_log`, mode `upsert_only|full`.
- **Admin ops**: sync logs, outbox list/requeue, basic stats; защищается `X-Admin-Sync-Secret` при заданном `ADMIN_SYNC_SECRET`.

## Admin endpoints

Все admin endpoints требуют X-Admin-Sync-Secret, если задан ADMIN_SYNC_SECRET.

- POST /admin/sync/{tenant_slug}/csv - body: { "base_dir": "...", "catalog": {...}, "mode": "upsert_only|full" }
- GET /admin/sync/{tenant_slug}/logs?limit=20
- GET /admin/outbox?status=dead&tenant_slug=...&limit=50
- POST /admin/outbox/requeue - body: { "tenant_slug": "...", "limit": 100, "reset_attempts": false }
- POST /admin/cleanup - body: { "dry_run": true } (по умолчанию dry-run; удаляет только старые sent outbox/processed webhooks/sync logs)
- GET /admin/audit?tenant_slug=...&limit=50
- GET /admin/stats?tenant_slug=...

Подробности: docs/ops-runbook.md.
## Важные env

См. `.env.example`. Ключевые:

- `DATABASE_URL_SYNC`, `REDIS_URL`
- `APP_SECRET_KEY` — обязателен для шифрования PII вне dev
- `MAX_WEBHOOK_SECRET`, `MAX_BOT_TOKEN` — для реального MAX
- `ADMIN_SYNC_SECRET` — секрет для admin endpoints
- `OUTBOX_MAX_ATTEMPTS`, `WORKER_BATCH_SIZE`, `WORKER_POLL_INTERVAL_SECONDS`
## Важные env

См. `.env.example`. Ключевые:

- `DATABASE_URL_SYNC`, `REDIS_URL`
- `APP_SECRET_KEY` - обязателен для production; используется для шифрования PII
- `MAX_WEBHOOK_SECRET`, `MAX_BOT_TOKEN` - для реального MAX
- `ADMIN_SYNC_SECRET` - секрет для admin endpoints`r`n- `ADMIN_ALLOWED_IPS` - опциональный CSV allowlist IP для admin endpoints
- `OUTBOX_MAX_ATTEMPTS`, `WORKER_BATCH_SIZE`, `WORKER_POLL_INTERVAL_SECONDS`
- `RETENTION_SENT_OUTBOX_DAYS`, `RETENTION_PROCESSED_WEBHOOK_DAYS`, `RETENTION_SYNC_LOG_DAYS`, `CLEANUP_INTERVAL_SECONDS`

## Ограничения / риски

- Нет реального MAX contract/E2E (нужны token/webhook secret/callback payload/chat addressing/rate limits, temp HTTPS tunnel).
- Tenant isolation на уровне схемы/репозиториев/тестов, не Postgres RLS.
- PII key rotation/retention/deletion policy не финализированы.
- Admin auth — shared secret; есть опциональный IP allowlist и audit log, но для пилота нужен RBAC/SSO/полноценный аудит.
- Google Sheets реальный API не подключен; есть CSV/fixture skeleton.
- Monitoring/alerting/backup/TLS/reverse proxy в прод-инфре не внедрены; есть runbook и шаблоны (`docs/ops-runbook.md`, `scripts/backup_postgres.sh`, `docker-compose.proxy.yml`).

## Структура

- `app/api` - FastAPI endpoints
- `app/models` - SQLAlchemy models
- `app/repositories` - tenant-scoped data access
- `app/services` - dialog/webhook/sync/scheduling/max/admin
- `app/workers` - webhook/outbox/expiry/retention worker
- `app/db/migrations` - Alembic migrations
- `docs` - ops/runbook docs
- `tests` - unit/integration tests
