# Ops Runbook (MVP)

## Назначение

Минимальный runbook для пилотного запуска без реального MAX-контракта/E2E. Покрывает безопасные ops-действия, retention, backup/TLS/reverse-proxy checklist и ограничения.

## Admin endpoints

> Дополнительно: можно задать ADMIN_ALLOWED_IPS (comma-separated). Пустое значение = без IP-ограничения.

Все admin endpoints требуют X-Admin-Sync-Secret, если задан ADMIN_SYNC_SECRET.

- POST /admin/sync/{tenant_slug}/csv — синхронизация каталога из CSV/inline catalog. Body: { "base_dir": "...", "catalog": {...}, "mode": "upsert_only|full" }. По умолчанию upsert_only.
- GET /admin/sync/{tenant_slug}/logs?limit=20 — логи sync.
- GET /admin/outbox?status=dead&tenant_slug=...&limit=50 — outbox по статусу.
- POST /admin/outbox/requeue — body: { "tenant_slug": "...", "limit": 100, "reset_attempts": false }. Ре-анимирует dead в pending.
- POST /admin/cleanup — body: { "dry_run": true } по умолчанию. Удаляет только старые sent outbox, processed webhook_events, старые sync_log. Не трогает pending/failed/sending/dead.
- GET /admin/audit?tenant_slug=...&limit=50 — audit log admin-действий. Секреты не логируются.
- GET /admin/stats?tenant_slug=... — агрегированные outbox/webhook/sync stats, включая oldest_dead_at.

## Retention / cleanup

Env:

- RETENTION_SENT_OUTBOX_DAYS=30
- RETENTION_PROCESSED_WEBHOOK_DAYS=30
- RETENTION_SYNC_LOG_DAYS=90
- CLEANUP_INTERVAL_SECONDS=3600

Worker периодически запускает cleanup (dry_run=false) с этими настройками. Для ручной проверки используйте POST /admin/cleanup с dry_run=true.

## Backup / restore

Скрипты (safe defaults):

- `scripts/backup_postgres.sh [output_dir]` — `pg_dump | gzip` из docker compose postgres.
- `scripts/restore_postgres_to_test.sh <backup.sql.gz> [test_db_name]` — восстановление **только** в БД, имя которой содержит `test`; отказывается работать с non-test именем.

Checklist перед пилотом:

- Включить регулярный backup (cron/systemd timer) + хранение вне app-контейнера.
- Проверять restore drill на `*_test`/staging, не на production.
- Бэкапить `.env`/secrets через secret manager или защищённое хранилище, не в git.
- Учитывать, что PII в `customer_profiles` зашифрована `APP_SECRET_KEY`; потеря ключа делает PII нечитаемой.
## TLS / reverse proxy

Шаблоны: `docker-compose.proxy.yml` + `deploy/nginx/maxbottenants.conf.example`.

- Публиковать app только через reverse proxy (nginx/caddy/traefik) с TLS.
- Наружу открывать только 80/443; app/postgres/redis оставить на internal/private интерфейсах.
- Для MAX webhook нужен публичный HTTPS URL; до реального контракта использовать временный tunnel только для теста.
- Ограничить размер body, rate limit, IP allowlist/Basic auth для admin endpoints на proxy-уровне до внедрения RBAC.
- Перед включением профиля proxy проверить cert paths, server_name, allow/deny для `/admin/`.
## PII policy draft (ограничения MVP)

- PII (customer_profiles) шифруется на уровне приложения через APP_SECRET_KEY.
- Ключевая ротация, retention/deletion по запросу пользователя, legal/compliance процесс — **не реализованы** в MVP, требуется отдельное решение до пилота.
- Не логировать payload с PII/секретами; admin audit хранит только безопасный summary.

## MAX E2E checklist (когда появятся credentials)

- Получить MAX_BOT_TOKEN, MAX_WEBHOOK_SECRET, реальный формат webhook/callback/button payload.
- Настроить временный HTTPS tunnel и webhook URL.
- Прогнать E2E на 2 тестовых салонах: /start по deep link, request_only создание заявки, owner confirm/reject, online_booking hold/confirm/expiry, callback buttons.
- Сверить chat/user addressing и rate limits с реальным контрактом; обновить normalizer/adapter и тесты.

## Ограничения

- Admin auth — shared secret, не RBAC. Опциональный `ADMIN_ALLOWED_IPS` снижает риск, но не заменяет RBAC/SSO.
- Tenant isolation enforced в коде/схеме/тестах, не Postgres RLS.
- Метрики/алертинг — только базовые stats/logs; Prometheus/Grafana/alerting не настроены.
- Retention cleanup удаляет данные без архивирования; перед включением в пилоте согласовать сроки.
