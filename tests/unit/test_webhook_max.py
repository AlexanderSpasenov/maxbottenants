from types import SimpleNamespace
from unittest.mock import MagicMock

from app.db.session import get_db


def _override_db(app, *, created=True):
    fake_event = SimpleNamespace(id="evt-1")

    class FakeRepo:
        def __init__(self, db):
            pass

        def create_received(self, *, event_key, event_type, payload):
            return fake_event, created

    import app.api.webhook_max as webhook_module

    original_repo = webhook_module.WebhookEventRepository
    webhook_module.WebhookEventRepository = FakeRepo

    def fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_get_db
    return original_repo


def _cleanup(app, original_repo):
    import app.api.webhook_max as webhook_module

    webhook_module.WebhookEventRepository = original_repo
    app.dependency_overrides.clear()


def test_webhook_max_accepts_payload_without_secret(client):
    app = client.app
    original = _override_db(app, created=True)
    try:
        response = client.post(
            "/webhook/max",
            json={"update_type": "message_created", "timestamp": 1764028800000},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["duplicate"] is False
        assert "event_key" in body
    finally:
        _cleanup(app, original)


def test_webhook_max_duplicate_returns_duplicate_flag(client):
    app = client.app
    original = _override_db(app, created=False)
    try:
        response = client.post(
            "/webhook/max",
            json={"update_type": "message_created", "timestamp": 1764028800000},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["duplicate"] is True
    finally:
        _cleanup(app, original)


def test_webhook_max_rejects_invalid_secret(client, monkeypatch):
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", "expected-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/webhook/max",
            json={"update_type": "message_created"},
            headers={"X-Max-Bot-Api-Secret": "wrong"},
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()
