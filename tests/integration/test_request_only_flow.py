import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.models.booking import Booking
from app.models.catalog import Master, Service, ServiceMaster
from app.models.outbox import OutboxMessage
from app.models.tenant import Tenant
from app.models.tenant_link import TenantLink
from app.models.tenant_member import TenantMember
from app.repositories.tenant_link_repository import hash_token
from app.workers.event_worker import process_pending_events

pytestmark = pytest.mark.integration


def _client_with_db(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed(db):
    t1 = Tenant(
        slug="salon-a",
        display_name="Salon A",
        status="active",
        timezone="Europe/Moscow",
        booking_mode="request_only",
    )
    t2 = Tenant(
        slug="salon-b",
        display_name="Salon B",
        status="active",
        timezone="Europe/Moscow",
        booking_mode="request_only",
    )
    db.add_all([t1, t2])
    db.flush()

    s1 = Service(
        tenant_id=t1.id,
        external_key="svc1",
        name="Manicure",
        price=1500,
        price_type="fixed",
        duration_minutes=60,
        buffer_minutes=0,
        is_active=True,
    )
    s2 = Service(
        tenant_id=t2.id,
        external_key="svc2",
        name="Massage",
        price=3000,
        price_type="fixed",
        duration_minutes=90,
        buffer_minutes=0,
        is_active=True,
    )
    m1 = Master(tenant_id=t1.id, external_key="m1", display_name="Anna", is_active=True)
    m2 = Master(tenant_id=t2.id, external_key="m2", display_name="Boris", is_active=True)
    db.add_all([s1, s2, m1, m2])
    db.flush()
    db.add_all(
        [
            ServiceMaster(tenant_id=t1.id, service_id=s1.id, master_id=m1.id, is_active=True),
            ServiceMaster(tenant_id=t2.id, service_id=s2.id, master_id=m2.id, is_active=True),
        ]
    )
    db.add_all(
        [
            TenantMember(tenant_id=t1.id, max_user_id=900001, role="owner", is_active=True),
            TenantMember(tenant_id=t2.id, max_user_id=900002, role="owner", is_active=True),
            TenantLink(
                tenant_id=t1.id,
                token_hash=hash_token("tenant-a-client-token"),
                link_type="client",
            ),
            TenantLink(
                tenant_id=t2.id,
                token_hash=hash_token("tenant-b-client-token"),
                link_type="client",
            ),
        ]
    )
    db.commit()
    return t1, t2


def _msg(chat_id: int, user_id: int, text: str, mid: str):
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


def test_request_only_happy_path_creates_booking_and_notifies_owner(db_session):
    t1, _ = _seed(db_session)
    client = _client_with_db(db_session)

    steps = [
        _msg(100, 200, "/start tenant-a-client-token", "m1"),
        _msg(100, 200, "1", "m2"),  # book
        _msg(100, 200, "1", "m3"),  # service
        _msg(100, 200, "1", "m4"),  # master
        _msg(100, 200, "2026-12-01", "m5"),
        _msg(100, 200, "15:00-17:00", "m6"),
        _msg(100, 200, "Иван", "m7"),
        _msg(100, 200, "+79990000000", "m8"),
        _msg(100, 200, "1", "m9"),  # confirm
    ]
    for p in steps:
        r = client.post("/webhook/max", json=p)
        assert r.status_code == 200

    # process webhook events
    processed = process_pending_events(batch_size=50, db=db_session)
    assert processed >= 1

    bookings = db_session.query(Booking).filter_by(tenant_id=t1.id).all()
    assert len(bookings) == 1
    booking = bookings[0]
    assert booking.status == "awaiting_salon"
    assert booking.booking_mode == "request_only"
    assert booking.max_user_id == 200
    assert booking.chat_id == 100
    assert booking.customer_name_snapshot == "Иван"

    outbox = db_session.query(OutboxMessage).filter_by(tenant_id=t1.id, chat_id=900001).all()
    assert len(outbox) >= 1
    assert f"#{booking.id}" in outbox[0].payload["text"]
    assert "/confirm" in outbox[0].payload["text"]
    assert "+79990000000" not in outbox[0].payload["text"]
    assert "0000" in outbox[0].payload["text"]


def test_owner_confirm_updates_booking_and_notifies_client(db_session):
    t1, _ = _seed(db_session)
    client = _client_with_db(db_session)

    # create booking via flow
    for text, mid in [
        ("/start tenant-a-client-token", "c1"),
        ("1", "c2"),
        ("1", "c3"),
        ("1", "c4"),
        ("2026-12-01", "c5"),
        ("15:00-17:00", "c6"),
        ("Иван", "c7"),
        ("+79990000000", "c8"),
        ("1", "c9"),
    ]:
        client.post("/webhook/max", json=_msg(100, 200, text, mid))
    process_pending_events(batch_size=50, db=db_session)

    booking = db_session.query(Booking).filter_by(tenant_id=t1.id).one()

    # owner confirms
    r = client.post("/webhook/max", json=_msg(900001, 900001, f"/confirm {booking.id}", "o1"))
    assert r.status_code == 200
    process_pending_events(batch_size=50, db=db_session)

    db_session.refresh(booking)
    assert booking.status == "confirmed"

    client_outbox = (
        db_session.query(OutboxMessage)
        .filter_by(tenant_id=t1.id, chat_id=100)
        .order_by(OutboxMessage.scheduled_at.desc())
        .all()
    )
    assert any("подтверждена" in m.payload.get("text", "").lower() for m in client_outbox)


def test_owner_cannot_manage_other_tenant_booking(db_session):
    t1, t2 = _seed(db_session)
    client = _client_with_db(db_session)

    # create booking in tenant A
    for text, mid in [
        ("/start tenant-a-client-token", "x1"),
        ("1", "x2"),
        ("1", "x3"),
        ("1", "x4"),
        ("2026-12-01", "x5"),
        ("15:00-17:00", "x6"),
        ("Иван", "x7"),
        ("+79990000000", "x8"),
        ("1", "x9"),
    ]:
        client.post("/webhook/max", json=_msg(100, 200, text, mid))
    process_pending_events(batch_size=50, db=db_session)
    booking = db_session.query(Booking).filter_by(tenant_id=t1.id).one()

    # owner of tenant B tries to confirm tenant A booking
    r = client.post("/webhook/max", json=_msg(900002, 900002, f"/confirm {booking.id}", "xb1"))
    assert r.status_code == 200
    process_pending_events(batch_size=50, db=db_session)

    db_session.refresh(booking)
    assert booking.status == "awaiting_salon"
