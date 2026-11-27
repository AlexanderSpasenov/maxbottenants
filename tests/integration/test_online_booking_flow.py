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
from app.workers.event_worker import process_pending_events

pytestmark = pytest.mark.integration


def _client_with_db(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed(db):
    t = Tenant(
        slug="salon-ob",
        display_name="Salon OB",
        status="active",
        timezone="Europe/Moscow",
        booking_mode="online_booking",
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
    db.add(TenantLink(tenant_id=t.id, token_hash=hash_token("ob-client"), link_type="client"))
    db.commit()
    return t


def _msg(chat_id, user_id, text, mid):
    return {
        "update_type": "message_created",
        "timestamp": 1764028800000,
        "message": {
            "mid": mid,
            "chat_id": chat_id,
            "sender": {"user_id": user_id, "name": "Test"},
            "body": {"text": text},
        },
    }


def test_online_booking_creates_confirmed_booking_with_slot(db_session, monkeypatch):
    t = _seed(db_session)
    client = _client_with_db(db_session)
    slot_start = datetime(2026, 12, 2, 9, 0, tzinfo=UTC)
    slot_end = slot_start + timedelta(minutes=60)
    monkeypatch.setattr(
        "app.services.scheduling.slots.get_available_slots",
        lambda **kwargs: [Slot(start=slot_start, end=slot_end)],
    )
    steps = [
        _msg(100, 200, "/start ob-client", "m1"),
        _msg(100, 200, "1", "m2"),
        _msg(100, 200, "1", "m3"),
        _msg(100, 200, "1", "m4"),
        _msg(100, 200, "2026-12-02", "m5"),
        _msg(100, 200, "1", "m6"),
        _msg(100, 200, "Ivan", "m7"),
        _msg(100, 200, "+79990000001", "m8"),
        _msg(100, 200, "1", "m9"),
    ]
    for p in steps:
        r = client.post("/webhook/max", json=p)
        assert r.status_code == 200
    process_pending_events(batch_size=50, db=db_session)
    bookings = db_session.query(Booking).filter_by(tenant_id=t.id).all()
    assert len(bookings) == 1
    b = bookings[0]
    assert b.booking_mode == "online_booking"
    assert b.status == "confirmed"
    assert b.slot_start is not None
    assert b.slot_end is not None
