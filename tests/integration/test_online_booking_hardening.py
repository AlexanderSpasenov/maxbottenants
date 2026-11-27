from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.models.booking import Booking
from app.models.catalog import Master, Service, ServiceMaster
from app.models.tenant import Tenant
from app.models.tenant_link import TenantLink
from app.models.tenant_member import TenantMember
from app.repositories.tenant_link_repository import hash_token
from app.services.scheduling.slots import Slot
from app.workers.event_worker import expire_pending_bookings, process_pending_events

pytestmark = pytest.mark.integration


def _client_with_db(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed(db, *, auto_confirm=True):
    t = Tenant(
        slug="salon-oh",
        display_name="Salon OH",
        status="active",
        timezone="Europe/Moscow",
        booking_mode="online_booking",
        online_booking_auto_confirm=auto_confirm,
        online_booking_hold_minutes=15,
    )
    db.add(t)
    db.flush()
    s = Service(
        tenant_id=t.id, external_key="svc1", name="Haircut", price=2000,
        price_type="fixed", duration_minutes=60, buffer_minutes=0, is_active=True,
    )
    m = Master(tenant_id=t.id, external_key="m1", display_name="Olga", is_active=True)
    db.add_all([s, m])
    db.flush()
    db.add(ServiceMaster(tenant_id=t.id, service_id=s.id, master_id=m.id, is_active=True))
    db.add(TenantMember(tenant_id=t.id, max_user_id=900010, role="owner", is_active=True))
    db.add(TenantLink(tenant_id=t.id, token_hash=hash_token("oh-client"), link_type="client"))
    db.commit()
    return t, s, m


def _msg(chat_id, user_id, text, mid):
    return {
        "update_type": "message_created",
        "timestamp": 1764028800000,
        "message": {
            "mid": mid, "chat_id": chat_id,
            "sender": {"user_id": user_id, "name": "Test"},
            "body": {"text": text},
        },
    }


def _flow_steps(date_str="2026-12-02"):
    return [
        _msg(100, 200, "/start oh-client", "m1"),
        _msg(100, 200, "1", "m2"),
        _msg(100, 200, "1", "m3"),
        _msg(100, 200, "1", "m4"),
        _msg(100, 200, date_str, "m5"),
        _msg(100, 200, "1", "m6"),
        _msg(100, 200, "Ivan", "m7"),
        _msg(100, 200, "+79990000001", "m8"),
        _msg(100, 200, "1", "m9"),
    ]


def test_online_booking_conflict_rejected(db_session, monkeypatch):
    t, s, m = _seed(db_session, auto_confirm=True)
    slot_start = datetime(2026, 12, 2, 9, 0, tzinfo=UTC)
    slot_end = slot_start + timedelta(minutes=60)
    db_session.add(Booking(
        tenant_id=t.id, max_user_id=1, chat_id=1, service_id=s.id, master_id=m.id,
        slot_start=slot_start, slot_end=slot_end, status="confirmed",
        booking_mode="online_booking",
    ))
    db_session.commit()

    monkeypatch.setattr(
        "app.services.scheduling.slots.get_available_slots",
        lambda **kwargs: [Slot(start=slot_start, end=slot_end)],
    )
    client = _client_with_db(db_session)
    for p in _flow_steps():
        r = client.post("/webhook/max", json=p)
        assert r.status_code == 200
    process_pending_events(batch_size=50, db=db_session)
    bookings = db_session.query(Booking).filter_by(tenant_id=t.id).all()
    assert len(bookings) == 1  # only pre-existing


def test_online_booking_pending_confirmation_expires(db_session, monkeypatch):
    t, _, _ = _seed(db_session, auto_confirm=False)
    slot_start = datetime(2026, 12, 2, 9, 0, tzinfo=UTC)
    slot_end = slot_start + timedelta(minutes=60)
    monkeypatch.setattr(
        "app.services.scheduling.slots.get_available_slots",
        lambda **kwargs: [Slot(start=slot_start, end=slot_end)],
    )
    client = _client_with_db(db_session)
    for p in _flow_steps():
        r = client.post("/webhook/max", json=p)
        assert r.status_code == 200
    process_pending_events(batch_size=50, db=db_session)
    b = db_session.query(Booking).filter_by(tenant_id=t.id).one()
    assert b.status == "pending_confirmation"
    assert b.expires_at is not None

    b.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.add(b)
    db_session.commit()
    expired = expire_pending_bookings(db=db_session)
    assert expired == 1
    db_session.refresh(b)
    assert b.status == "expired"
    from app.models.outbox import OutboxMessage

    msgs = db_session.query(OutboxMessage).filter_by(tenant_id=t.id, chat_id=100).all()
    assert any("истекла" in (m.payload or {}).get("text", "") for m in msgs)
