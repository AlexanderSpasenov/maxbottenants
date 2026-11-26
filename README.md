# maxbottenants

Локальный технический прототип мультитенантной платформы записи для салонов через один общий MAX-бот.

## Статус

**Фаза 1 / Инкремент 1**: MVP-каркас.

Реализовано в этом инкременте:
- структура репозитория;
- Docker Compose для `app`, `postgres`, `redis`, `worker`;
- FastAPI + health endpoints;
- SQLAlchemy + Alembic каркас;
- базовая конфигурация через env;
- pytest smoke-тесты;
- заготовки под MAX mock/real client, Google Sheets source stub, workers.

Пока не реализовано:
- реальная интеграция MAX Bot API (нет токена/бота);
- бизнес-сценарий `request_only` end-to-end;
- Google Sheets sync;
- `online_booking`.

## Стек

- Python 3.12+
- FastAPI
- PostgreSQL 16
- Redis 7
- SQLAlchemy 2.x
- Alembic
- HTTPX
- Docker Compose
- pytest, ruff

## Быстрый старт

1. Скопировать env:
   ```bash
   cp .env.example .env
   ```
   На Windows PowerShell:
   ```powershell
   Copy-Item .env.example .env
   ```

2. Запустить стек:
   ```bash
   docker compose up --build
   ```

3. Проверить health:
   - `GET http://localhost:8000/health/live`
   - `GET http://localhost:8000/health/ready`

> По умолчанию `docker-compose.yml` публикует порты `8000/5432/6379` только на `127.0.0.1` для безопасного локального запуска. Для внешнего доступа используйте reverse proxy/firewall и осознанно меняйте бинды.

## Локальная разработка без MAX токена

Реальный MAX бот пока не требуется. Для локальной разработки используются:
- `app/integrations/max/mock_client.py` — mock отправки сообщений;
- `app/integrations/max/fixtures/` — примеры входящих событий;
- `scripts/replay_webhook.py` — заготовка для replay webhook payload.

Webhook endpoint `/webhook/max` сохранён как каркас и будет доработан в инкременте идемпотентности/обработки событий.

## Миграции

Применить миграции:
```bash
docker compose exec app alembic upgrade head
```

Создать новую миграцию:
```bash
docker compose exec app alembic revision --autogenerate -m "message"
```

## Тесты и линт

```bash
docker compose exec app pytest
docker compose exec app ruff check .
```

Локально (если зависимости установлены):
```bash
pytest
ruff check .
```

## Структура

См. `app/`:
- `api/` — HTTP endpoints;
- `core/` — config/logging/security;
- `db/` — SQLAlchemy session, Alembic;
- `models/`, `schemas/`, `repositories/`, `services/` — доменная модель и логика;
- `integrations/max/` — абстракция MAX API (mock/real);
- `integrations/sheets/` — заготовка под Google Sheets source;
- `workers/` — фоновые воркеры.

## Правила разработки

1. Каждый законченный этап — отдельный атомарный коммит.
2. Секреты только в env/secret manager, не в Git.
3. Любые изменения схемы БД — через Alembic.
4. Не переходить к следующему инкременту без проверки критериев приёмки.
5. После задачи фиксировать: что сделано, изменённые файлы, как проверить, риски/ограничения.

## Следующий инкремент

**Инкремент 2**: мультитенантная модель данных, миграции core-таблиц, seed двух тестовых салонов, тесты изоляции tenant.
