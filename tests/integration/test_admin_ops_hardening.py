import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.admin_audit_log import AdminAuditLog
from app.models.outbox import OutboxMessage
from app.models.sync_log import SyncLog
from app.models.tenant import Tenant
from app.models.webhook import WebhookEvent

pytestmark = pytest.mark.integration


def _client_with_db(db_session, monkeypatch, secret: str = "test-admin-secret"):
    monkeypatch.setenv("ADMIN_SYNC_SECRET", secret)
    get_settings.cache_clear()
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), {"X-Admin-Sync-Secret": secret}


def test_admin_audit_log_for_sync_and_requeue(db_session, monkeypatch):
    tenant = Tenant(slug="audit-a", display_name="Audit A", status="active")
    db_session.add(tenant)
    db_session.commit()

    client, headers = _client_with_db(db_session, monkeypatch)

    r = client.post(
        "/admin/sync/audit-a/csv",
        json={"catalog": {"services": [], "masters": [], "service_masters": []}},
        headers=headers,
    )
    assert r.status_code == 200

    r = client.post(
        "/admin/outbox/requeue",
        json={"tenant_slug": "audit-a", "limit": 10, "reset_attempts": True},
        headers=headers,
    )
    assert r.status_code == 200

    logs = db_session.query(AdminAuditLog).order_by(AdminAuditLog.created_at.asc()).all()
    actions = [l.action for l in logs]
    assert "sync.csv" in actions
    assert "outbox.requeue" in actions
    for log_row in logs:
        assert log_row.status in {"ok", "failed"}
        # secret must never be stored
        dumped = str(log_row.request_summary or "") + str(log_row.error or "")
        assert "test-admin-secret" not in dumped

    r = client.get("/admin/audit?tenant_slug=audit-a&limit=50", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_slug"] == "audit-a"
    assert any(a["action"] == "sync.csv" for a in body["audit"])
    assert any(a["action"] == "outbox.requeue" for a in body["audit"])

    get_settings.cache_clear()


def test_retention_cleanup_dry_run_and_actual(db_session, monkeypatch):
    tenant = Tenant(slug="ret-a", display_name="Ret A", status="active")
    db_session.add(tenant)
    db_session.flush()

    now = datetime.now(UTC)
    old = now - timedelta(days=120)
    recent = now - timedelta(days=1)

    old_sent = OutboxMessage(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        chat_id=1,
        payload={"text": "old"},
        status="sent",
        attempts=1,
        sent_at=old,
        next_attempt_at=old,
        scheduled_at=old,
    )
    recent_sent = OutboxMessage(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        chat_id=1,
        payload={"text": "recent"},
        status="sent",
        attempts=1,
        sent_at=recent,
        next_attempt_at=recent,
        scheduled_at=recent,
    )
    dead = OutboxMessage(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        chat_id=1,
        payload={"text": "dead"},
        status="dead",
        attempts=5,
        sent_at=old,
        next_attempt_at=old,
        scheduled_at=old,
    )
    db_session.add_all([old_sent, recent_sent, dead])

    db_session.add(
        WebhookEvent(
            id=uuid.uuid4(),
            event_key="old-processed",
            event_type="message_created",
            payload={},
            status="processed",
            attempts=1,
            received_at=old,
            processed_at=old,
        )
    )
    db_session.add(
        WebhookEvent(
            id=uuid.uuid4(),
            event_key="recent-processed",
            event_type="message_created",
            payload={},
            status="processed",
            attempts=1,
            received_at=recent,
            processed_at=recent,
        )
    )
    db_session.add(
        WebhookEvent(
            id=uuid.uuid4(),
            event_key="failed-old",
            event_type="message_created",
            payload={},
            status="failed",
            attempts=1,
            received_at=old,
            processed_at=None,
        )
    )

    db_session.add(
        SyncLog(
            tenant_id=tenant.id,
            started_at=old,
            finished_at=old,
            status="ok",
            created_at=old,
        )
    )
    db_session.add(
        SyncLog(
            tenant_id=tenant.id,
            started_at=recent,
            finished_at=recent,
            status="ok",
            created_at=recent,
        )
    )
    db_session.commit()

    monkeypatch.setenv("RETENTION_SENT_OUTBOX_DAYS", "30")
    monkeypatch.setenv("RETENTION_PROCESSED_WEBHOOK_DAYS", "30")
    monkeypatch.setenv("RETENTION_SYNC_LOG_DAYS", "30")
    client, headers = _client_with_db(db_session, monkeypatch)

    r = client.post("/admin/cleanup", json={"dry_run": True}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["sent_outbox_eligible"] == 1
    assert body["processed_webhooks_eligible"] == 1
    assert body["sync_logs_eligible"] == 1
    assert body["sent_outbox_deleted"] == 0
    # nothing deleted
    assert db_session.query(OutboxMessage).count() == 3

    r = client.post("/admin/cleanup", json={"dry_run": False}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is False
    assert body["sent_outbox_deleted"] == 1
    assert body["processed_webhooks_deleted"] == 1
    assert body["sync_logs_deleted"] == 1

    statuses = {m.status for m in db_session.query(OutboxMessage).all()}
    assert "dead" in statuses
    assert len([m for m in db_session.query(OutboxMessage).all() if m.status == "sent"]) == 1
    assert db_session.query(WebhookEvent).filter_by(event_key="old-processed").first() is None
    assert (
        db_session.query(WebhookEvent).filter_by(event_key="recent-processed").first()
        is not None
    )
    assert db_session.query(WebhookEvent).filter_by(event_key="failed-old").first() is not None
    assert db_session.query(SyncLog).count() == 1

    get_settings.cache_clear()


def test_admin_stats_include_sync_and_dead_outbox_age(db_session, monkeypatch):
    tenant = Tenant(slug="stats-a", display_name="Stats A", status="active")
    db_session.add(tenant)
    db_session.flush()
    old = datetime.now(UTC) - timedelta(days=2)
    db_session.add(
        OutboxMessage(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            chat_id=1,
            payload={"text": "x"},
            status="dead",
            attempts=5,
            next_attempt_at=old,
            scheduled_at=old,
        )
    )
    db_session.add(
        SyncLog(tenant_id=tenant.id, started_at=old, finished_at=old, status="ok", created_at=old)
    )
    db_session.add(
        SyncLog(
            tenant_id=tenant.id,
            started_at=old,
            finished_at=old,
            status="failed",
            created_at=old,
        )
    )
    db_session.commit()

    client, headers = _client_with_db(db_session, monkeypatch)
    r = client.get("/admin/stats?tenant_slug=stats-a", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["outbox"]["dead"] == 1
    assert body["outbox"]["oldest_dead_at"] is not None
    assert body["sync_logs"]["ok"] == 1
    assert body["sync_logs"]["failed"] == 1
    get_settings.cache_clear()
