import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.models.webhook import WebhookEvent
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.webhooks.processor import WebhookEventProcessor

pytestmark = pytest.mark.integration


def _client_with_db(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_webhook_persists_event(db_session):
    client = _client_with_db(db_session)
    payload = {
        "update_type": "message_created",
        "timestamp": 1764028800000,
        "message": {
            "mid": "mid-persist-1",
            "chat_id": 100001,
            "sender": {"user_id": 200001},
            "body": {"text": "/start"},
        },
    }
    resp = client.post("/webhook/max", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["duplicate"] is False
    assert body["event_key"] == "max:message_created:mid-persist-1"

    repo = WebhookEventRepository(db_session)
    event = repo.get_by_event_key("max:message_created:mid-persist-1")
    assert event is not None
    assert event.event_type == "message_created"
    assert event.status == "received"
    assert event.payload["message"]["mid"] == "mid-persist-1"


def test_webhook_redelivery_is_deduped(db_session):
    client = _client_with_db(db_session)
    payload = {
        "update_type": "message_created",
        "message": {"mid": "mid-dup-1", "chat_id": 1, "body": {"text": "hi"}},
    }

    r1 = client.post("/webhook/max", json=payload)
    r2 = client.post("/webhook/max", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True
    assert r1.json()["event_key"] == r2.json()["event_key"]

    events = db_session.query(WebhookEvent).filter_by(event_key=r1.json()["event_key"]).all()
    assert len(events) == 1


def test_worker_processes_pending_event(db_session, monkeypatch):
    # Create event directly via repo
    repo = WebhookEventRepository(db_session)
    payload = {"update_type": "message_created", "message": {"mid": "mid-work-1"}}
    event, created = repo.create_received(
        event_key="max:message_created:mid-work-1",
        event_type="message_created",
        payload=payload,
    )
    db_session.commit()
    assert created
    assert event.status == "received"

    # claim as worker would do
    claimed = repo.claim_pending(limit=10)
    assert len(claimed) == 1
    claimed_event = claimed[0]
    assert claimed_event.status == "processing"
    assert claimed_event.attempts == 1

    processor = WebhookEventProcessor(db_session)
    processor.process(claimed_event)
    db_session.refresh(claimed_event)
    assert claimed_event.status == "processed"
    assert claimed_event.processed_at is not None
    assert claimed_event.attempts == 1


def test_replay_fixture_is_idempotent(db_session):
    client = _client_with_db(db_session)
    fixture_path = Path("app/integrations/max/fixtures/message_created.json")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    r1 = client.post("/webhook/max", json=payload)
    r2 = client.post("/webhook/max", json=payload)
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True

    key = r1.json()["event_key"]
    events = db_session.query(WebhookEvent).filter_by(event_key=key).all()
    assert len(events) == 1
