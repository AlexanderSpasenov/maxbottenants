# MAX Contract Capture Kit (подготовка к вечеру)

Цель: быстро и безопасно зафиксировать реальный контракт MAX, когда появятся данные по боту, без угадывания поведения.

## Что прислать/зафиксировать (без коммита секретов)

- `MAX_BOT_TOKEN` — **не коммитить**, передать через секретный канал/.env на сервере.
- `MAX_WEBHOOK_SECRET` — **не коммитить**.
- Публичный webhook URL / tunnel URL (временный HTTPS).
- Реальные примеры payload (JSON), по 1-2 на тип:
  - inbound message (`/start`, обычный текст, deep-link payload/start params если есть)
  - callback/button click
  - command/menu event
  - delivery/status/update event (если есть)
  - любой webhook verification/challenge event (если есть)
- Для каждого payload: HTTP method, path, headers (секреты маскировать), raw body, ожидаемое поведение бота.
- Контракт ответа MAX Bot API: endpoint, auth header, chat/user addressing fields, ограничения по rate limit, формат кнопок/callback data.
- Данные 2 тестовых салонов: `tenant_slug`, название, owner chat/user id, тестовый пользователь.

## Куда складывать в репо

- Маскированные fixtures: `tests/fixtures/max/*.json` (без токенов/секретов/реальных PII).
- Сырые чувствительные дампы: **не в git**; локально/в secret storage.
- Итог адаптации: обновить normalizer/adapter + integration tests.

## Чеклист интеграции после получения данных

1. Добавить реальные masked fixtures в `tests/fixtures/max/`.
2. Написать/обновить integration tests для webhook/callback/button flow на 2 тестовых салонах.
3. Уточнить `app/services/max/*` normalizer/adapter под реальный контракт.
4. Проверить signature/secret verification по реальному формату.
5. Прогнать E2E: `/start`, request_only, owner confirm/reject, online_booking hold/confirm/expiry, callbacks.
6. Проверить idempotency/redelivery на реальных повторных доставках.

## Правила безопасности

- Никогда не коммитить токены, webhook secrets, реальные номера телефонов, имена клиентов.
- Перед коммитом fixtures маскировать `token`, `secret`, `phone`, `email`, `name`, `address`.
- Реальные E2E прогоны — только на тестовых салонах.
