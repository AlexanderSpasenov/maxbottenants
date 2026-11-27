# Pilot Readiness (без MAX E2E)

Этот документ фиксирует, что можно проверить/подготовить до получения реального MAX-контракта и credentials.

## Статус

- **Можно закрыть сейчас (safe):** health/readiness, admin guardrails, backup/restore drill, retention cleanup, proxy/TLS шаблоны, runbook/checklists, audit safety.
- **Внешний блокер (MAX):** `MAX_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, реальные webhook/callback/button payload, chat addressing, rate limits, temp HTTPS tunnel, E2E на 2 тестовых салонах.
- **Требует отдельного решения:** RBAC/SSO, production monitoring/alerting, юридически утверждённая PII policy, key rotation/re-encrypt, Postgres RLS.

## Go/No-Go (safe pre-pilot)

### Go

- `alembic current` на head; `ruff check .` clean; `pytest -q` green на `*_test`.
- `GET /health/live` и `GET /health/ready` возвращают 200.
- `ADMIN_SYNC_SECRET` задан; `ADMIN_ALLOWED_IPS` настроен где возможно; `/admin/*` не открыт публично без proxy/auth.
- `GET /admin/readiness` возвращает `ready=true` для целевого tenant/окружения; содержит `actor` и `rbac` scaffold state.
- Backup создан и restore drill выполнен на `*_test`.
- Retention настроен; `POST /admin/cleanup` с `dry_run=true` проверен; outbox dead-letter мониторится.
- `.env`/secrets вне git; `APP_SECRET_KEY` production-grade.

### No-Go

- Outbox dead-letter растёт или `oldest_dead_at` слишком старый.
- Нет подтверждённого restore drill.
- `APP_SECRET_KEY` default или секреты в git/logs.
- Admin endpoints доступны без секрета/proxy guardrails.
- Любой пункт MAX E2E ещё не подтверждён реальным контрактом.

## RBAC/SSO (design draft, без внедрения)

Текущий MVP: shared secret (`ADMIN_SYNC_SECRET`) + optional IP allowlist. Этого недостаточно для пилота.

Минимальная целевая модель ролей:

| Role | Назначение | Разрешённые действия |
|---|---|---|
| `ops_viewer` | наблюдение | `/admin/stats`, `/admin/readiness`, `/admin/audit`, `/admin/sync/*/logs`, `/admin/outbox` GET |
| `ops_operator` | безопасные ops-действия | всё из `ops_viewer` + `/admin/cleanup` dry-run, `/admin/outbox/requeue` |
| `tenant_admin` | управление tenant-каталогом | sync CSV/catalog для назначенных tenant, просмотр логов/audit tenant |
| `platform_admin` | полный admin | все admin endpoints, включая будущие destructive ops |

План внедрения (без MAX блокера, но требует отдельного инкремента):

1. Ввести auth abstraction: `AdminPrincipal {subject, roles, tenant_scope}`.
2. Сохранить совместимость: shared secret маппится в `platform_admin` до миграции.
3. Добавить RBAC checks per endpoint и audit `actor`.
4. Предпочтительно SSO/OIDC или mTLS+gateway auth перед app; не хранить долгоживущие пароли в app.
5. Добавить тесты на allow/deny matrix и tenant scope.

## PII procedures draft

### Текущее состояние

- PII в `customer_profiles` шифруется `APP_SECRET_KEY`.
- Admin audit не должен содержать секреты/сырой PII payload.
- Нет реализованной key rotation/re-encrypt, нет user deletion/export workflow, нет утверждённого legal процесса.

### До пилота нужно определить

- **Retention:** сроки хранения customer profiles, requests, webhook/outbox/audit/sync logs.
- **Deletion/export:** канал запроса, SLA, роли, подтверждение личности, аудит действий.
- **Key rotation:** процедура генерации нового `APP_SECRET_KEY`, re-encrypt migration, окно совместимости, rollback, хранение ключей в secret manager/KMS.
- **Incident response:** что делать при утечке секрета/БД/лога; revoke/rotate, notify, forensic audit.
- **Ownership:** ответственный за approve/execute PII операций.

### Технический план (отдельный инкремент)

1. Версионировать encrypted fields (`key_id`, `ciphertext`).
2. Добавить batch re-encrypt job с dry-run и progress/audit.
3. Добавить admin/process workflow для export/delete с tenant scope и audit trail.
4. Не удалять связанные бизнес-записи слепо; применять anonymization/tombstone где нужна целостность.

## MAX E2E (внешний блокер)

Нужны: реальные token/secret, контракт webhook/callback/button payload, chat addressing, rate limits, temp HTTPS tunnel, 2 тестовых салона. До этого не заявлять production/pilot E2E готовность.
